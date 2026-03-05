"""Dashboard routes for policy performance analysis."""

import ast
import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Sequence
from uuid import UUID

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import selectinload
from sqlmodel import col, select

from metta.app_backend.models.job_request import JobPolicyVersion, JobRequest, JobType
from metta.app_backend.models.policies import PolicyVersion
from metta.app_backend.models.tournament import Pool, PoolPlayer, Season
from metta.app_backend.queries import episode_queries, policy_queries
from metta.app_backend.queries.role_percentile_queries import ROLE_METRICS, compute_policy_role_percentiles
from metta.app_backend.replay.summarizer import parse_replay, select_replay_episodes, summarize_replay
from metta.app_backend.route_logger import timed_http_handler
from metta.app_backend.tournament.commissioners.factory import build_commissioner
from metta.app_backend.tournament.registry import SEASONS
from metta.app_backend.tournament.settings import DEFAULT_SEASON as TOURNAMENT_DEFAULT_SEASON
from vibeservatory.backend.dashboard_backend.anthropic_client import (
    AnthropicConnectionError,
    AnthropicHTTPError,
    AnthropicResponseFormatError,
    AnthropicTimeoutError,
    request_anthropic_message,
    request_bedrock_message,
)
from vibeservatory.backend.dashboard_backend.auth import SoftmaxUser
from vibeservatory.backend.dashboard_backend.cogames_diagnose.router import list_run_summaries
from vibeservatory.backend.dashboard_backend.database import db_session
from vibeservatory.backend.dashboard_backend.state_page import diagnostics as claude_dashboard
from vibeservatory.backend.dashboard_backend.state_page.capability_audit import build_capability_code_audit
from vibeservatory.backend.dashboard_backend.state_page.diagnostics import (
    DashboardDerived,
    DashboardDiagnoseRunSummary,
    DashboardEpisode,
    DashboardResponse,
    DashboardRolePercentilesResponse,
    DerivedMetrics,
    EpisodeSelectionMetadata,
    FailureSummary,
    PolicyInfo,
    RoleMetricDef,
    RolePercentileRow,
    compute_action_summary,
    compute_confidence_summary,
    compute_crash_dump_summary,
    compute_derived_metrics,
    compute_failure_summary,
    compute_instrumentation_validation,
    compute_matchup_summary,
    compute_opponent_metrics,
    compute_orchestration_hooks,
    compute_outcome_summary,
    compute_pattern_extraction_summary,
    compute_stats_inventory_summary,
    compute_team_comp_analysis,
    compute_trend_explorer_summary,
    compute_unsupported_state,
    compute_version_trend_summary,
)
from vibeservatory.backend.dashboard_backend.state_page.episode_builder import build_dashboard_episodes

logger = logging.getLogger(__name__)

DASHBOARD_LIMIT = 100

# TODO: persistent rate limiter for multi-instance deployments
_analysis_rate_limit: dict[str, list[float]] = {}
ANALYSIS_RATE_LIMIT = 10  # requests per hour
INCLUDE_ROLE_PERCENTILES = "role_percentiles"
INCLUDE_DIAGNOSE_RUNS = "diagnose_runs"


class DashboardAnalysisResponse(BaseModel):
    analysis: str
    data_sources: list[str]


class RouterRolePercentileRow(RolePercentileRow):
    model_config = ConfigDict(from_attributes=True)


async def _latest_default_season(session: Any) -> Season | None:
    season_query = (
        select(Season)
        .where(col(Season.name) == TOURNAMENT_DEFAULT_SEASON)
        .order_by(
            col(Season.canonical).desc(),
            col(Season.version).desc(),
            col(Season.created_at).desc(),
        )
        .limit(1)
    )
    return (await session.execute(season_query)).scalar_one_or_none()


async def _latest_freeplay_seasons(session: Any, *, limit: int = 10) -> list[Season]:
    season_query = (
        select(Season)
        .where(col(Season.team_tournament_config).is_(None))
        .order_by(
            col(Season.canonical).desc(),
            col(Season.version).desc(),
            col(Season.created_at).desc(),
        )
        .limit(limit)
    )
    return list((await session.execute(season_query)).scalars().all())


def _season_display_name(season: Season) -> str:
    return season.name if season.canonical else f"{season.name}:v{season.version}"


async def _season_leaderboard_winner_policy_version_id(season: Season) -> str | None:
    if season.name not in SEASONS:
        return None
    commissioner = await build_commissioner(season.name, season_id=season.id)
    leaderboard = await commissioner.get_leaderboard()
    if not leaderboard:
        return None
    return str(leaderboard[0][0])


async def _default_winner_policy_version_id(session: Any) -> tuple[str | None, str | None]:
    default_season = await _latest_default_season(session)
    if default_season is not None:
        winner_policy_id = await _season_leaderboard_winner_policy_version_id(default_season)
        if winner_policy_id is not None:
            return winner_policy_id, _season_display_name(default_season)

    freeplay_seasons = await _latest_freeplay_seasons(session)
    for season in freeplay_seasons:
        if default_season is not None and season.id == default_season.id:
            continue
        winner_policy_id = await _season_leaderboard_winner_policy_version_id(season)
        if winner_policy_id is not None:
            return winner_policy_id, _season_display_name(season)

    if default_season is None:
        return None, None
    return None, _season_display_name(default_season)


async def _require_policy_version(policy_version_id: str) -> tuple[UUID, Any]:
    try:
        pv_id = UUID(policy_version_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid policy version id format") from exc
    pv = await policy_queries.get_policy_version_with_name(pv_id)
    if not pv:
        raise HTTPException(status_code=404, detail="Policy version not found")
    return pv_id, pv


async def _fetch_policy_episode_jobs(session: Any, policy_version_id: UUID, limit: int) -> list[Any]:
    jobs_query = (
        select(JobRequest)
        .join(JobPolicyVersion, JobPolicyVersion.job_id == JobRequest.id)  # pyright: ignore[reportArgumentType]
        .where(
            JobPolicyVersion.policy_version_id == policy_version_id,
            col(JobRequest.job_type) == JobType.episode,
        )
        .order_by(col(JobRequest.created_at).desc())
        .limit(limit)
    )
    jobs_result = await session.execute(jobs_query)
    return jobs_result.scalars().all()


async def _fetch_policy_dashboard_sources(
    policy_version_id: UUID,
    limit: int,
) -> tuple[list[Any], list[Any]]:
    raw_episodes = await episode_queries.get_episodes(primary_policy_version_ids=[policy_version_id], limit=limit)
    async with db_session(read_only=True) as session:
        policy_jobs = await _fetch_policy_episode_jobs(session, policy_version_id, limit)
    return raw_episodes, policy_jobs


def _role_metric_definitions() -> dict[str, list[RoleMetricDef]]:
    return {
        role: [
            RoleMetricDef(
                key=metric.key,
                source_names=list(metric.source_names),
                higher_is_better=metric.higher_is_better,
                include_in_overall=metric.include_in_overall,
                overall_weight=metric.overall_weight,
            )
            for metric in metrics
        ]
        for role, metrics in ROLE_METRICS.items()
    }


def _parse_include_flags(include: str | None) -> set[str]:
    if not include:
        return set()
    return {token.strip().lower() for token in include.split(",") if token.strip()}


def _preferred_pool_names_for_season(season_name: str) -> list[str]:
    if season_name not in SEASONS:
        return []
    commissioner_cls = SEASONS[season_name]
    preferred_names = [commissioner_cls.leaderboard_pool, commissioner_cls.entry_pool]
    return list(dict.fromkeys([name for name in preferred_names if name]))


def _append_unique_pool(pool: Pool, *, deduped: list[Pool], seen_pool_ids: set[UUID]) -> None:
    if pool.id in seen_pool_ids:
        return
    seen_pool_ids.add(pool.id)
    deduped.append(pool)


def _apply_leaderboard_entry(policy: PolicyInfo, leaderboard_entry: tuple[int, float, int] | None) -> None:
    if leaderboard_entry is None:
        return
    policy.rank, policy.score, policy.matches = leaderboard_entry


async def _select_role_pool_for_policy(session: Any, policy_version_id: UUID) -> Pool | None:
    pool_query = (
        select(Pool, Season)
        .join(Season, Pool.season_id == Season.id)  # pyright: ignore[reportArgumentType]
        .join(PoolPlayer, PoolPlayer.pool_id == Pool.id)  # pyright: ignore[reportArgumentType]
        .where(PoolPlayer.policy_version_id == policy_version_id)
        .order_by(
            col(Season.canonical).desc(),
            col(Season.version).desc(),
            col(Season.created_at).desc(),
            col(PoolPlayer.retired).asc(),
            col(Pool.created_at).desc(),
        )
    )
    pool_rows = (await session.execute(pool_query)).all()
    if not pool_rows:
        return None

    newest_season = pool_rows[0][1]
    newest_season_pools = [pool for pool, season in pool_rows if season.id == newest_season.id]
    preferred_names = _preferred_pool_names_for_season(newest_season.name)
    for preferred_name in preferred_names:
        for pool in newest_season_pools:
            if pool.name == preferred_name:
                return pool
    return newest_season_pools[0]


async def _candidate_role_pools_for_policy(session: Any, policy_version_id: UUID) -> list[Pool]:
    season_query = (
        select(Season)
        .where(col(Season.name) == TOURNAMENT_DEFAULT_SEASON)
        .order_by(
            col(Season.canonical).desc(),
            col(Season.version).desc(),
            col(Season.created_at).desc(),
        )
        .limit(1)
    )
    default_season = (await session.execute(season_query)).scalars().first()
    default_season_pools: list[Pool] = []
    if default_season is not None:
        default_pool_query = (
            select(Pool).where(Pool.season_id == default_season.id).order_by(col(Pool.created_at).desc())
        )
        default_season_pools = list((await session.execute(default_pool_query)).scalars().all())

    preferred_names = _preferred_pool_names_for_season(TOURNAMENT_DEFAULT_SEASON)
    ordered_default_pools: list[Pool] = []
    if default_season_pools:
        for preferred_name in preferred_names:
            ordered_default_pools.extend(pool for pool in default_season_pools if pool.name == preferred_name)
        ordered_default_pools.extend(pool for pool in default_season_pools if pool not in ordered_default_pools)

    selected = await _select_role_pool_for_policy(session, policy_version_id)

    pool_query = (
        select(Pool)
        .join(PoolPlayer, PoolPlayer.pool_id == Pool.id)  # pyright: ignore[reportArgumentType]
        .where(PoolPlayer.policy_version_id == policy_version_id)
        .order_by(col(Pool.created_at).desc())
    )
    pools = (await session.execute(pool_query)).scalars().all()

    deduped: list[Pool] = []
    seen_pool_ids: set[UUID] = set()

    for pool in ordered_default_pools:
        _append_unique_pool(pool, deduped=deduped, seen_pool_ids=seen_pool_ids)

    if selected is not None:
        _append_unique_pool(selected, deduped=deduped, seen_pool_ids=seen_pool_ids)

    for pool in pools:
        _append_unique_pool(pool, deduped=deduped, seen_pool_ids=seen_pool_ids)
    return deduped


async def _select_role_pool_and_rows(
    session: Any,
    policy_version_id: UUID,
) -> tuple[Pool | None, list[Any]]:
    candidate_pools = await _candidate_role_pools_for_policy(session, policy_version_id)
    if not candidate_pools:
        return None, []

    for pool in candidate_pools:
        rows = await compute_policy_role_percentiles(pool.id, policy_version_id)
        if rows:
            return pool, rows

    return candidate_pools[0], []


async def _build_role_percentiles_response(policy_version_id: UUID) -> DashboardRolePercentilesResponse:
    roles = _role_metric_definitions()
    async with db_session(read_only=True) as session:
        preferred_pool, rows = await _select_role_pool_and_rows(session, policy_version_id)

    if preferred_pool is None:
        return DashboardRolePercentilesResponse(
            pool_id=None,
            pool_name=None,
            roles=roles,
            rows=[],
        )

    return DashboardRolePercentilesResponse(
        pool_id=str(preferred_pool.id),
        pool_name=preferred_pool.name,
        roles=roles,
        rows=[RouterRolePercentileRow.model_validate(row) for row in rows],
    )


def _build_diagnose_run_summaries() -> list[DashboardDiagnoseRunSummary]:
    return [
        DashboardDiagnoseRunSummary(run_id=summary.run_id, manifest=summary.manifest)
        for summary in list_run_summaries()
    ]


async def _build_sorted_dashboard_episodes(
    raw_episodes: list[Any],
    policy_version_id: UUID,
    policy_version_id_str: str,
    policy_jobs: Sequence[Any],
    opponent_cache: dict[str, dict[str, Any]],
) -> list[DashboardEpisode]:
    dashboard_episodes = await build_dashboard_episodes(
        raw_episodes=raw_episodes,
        policy_version_id=policy_version_id,
        policy_version_id_str=policy_version_id_str,
        policy_jobs=policy_jobs,
        opponent_cache=opponent_cache,
    )
    dashboard_episodes.sort(key=lambda episode: episode.created_at or "", reverse=True)
    return dashboard_episodes


def _agent_indices_from_tags(tags: dict[str, str], policy_version_id: str, num_agents: int) -> list[int]:
    """Determine which agent indices belong to the target policy using episode tags.

    Falls back to half-split heuristic only if no assignment data exists.
    """
    assignments_str = tags.get("assignments", "")
    pv_ids_str = tags.get("policy_version_ids", "")
    if assignments_str and pv_ids_str:
        try:
            assignments = ast.literal_eval(assignments_str)
            pv_ids_list = ast.literal_eval(pv_ids_str)
            if policy_version_id in pv_ids_list:
                policy_index = pv_ids_list.index(policy_version_id)
                return [i for i, a in enumerate(assignments) if a == policy_index]
        except (SyntaxError, TypeError, ValueError, AttributeError):
            logger.debug("Failed to parse assignment tags for agent index resolution")

    return list(range(num_agents // 2)) if num_agents > 0 else []


async def _fetch_and_summarize_replays(episode_ids: list[str], policy_version_id: str) -> list[dict[str, Any]]:
    """Fetch replay files for episodes (by ID from DB) and summarize them.

    Resolves replay URLs from the database — never from user input — to prevent SSRF.
    Uses episode tag data (assignments, policy_version_ids) to determine correct agent indices.
    """
    uuid_ids: list[UUID] = []
    for eid in episode_ids:
        try:
            uuid_ids.append(UUID(eid))
        except ValueError:
            logger.debug("Skipping invalid episode ID: %s", eid)
    if not uuid_ids:
        return []

    db_episodes = await episode_queries.get_episodes(episode_ids=uuid_ids, limit=len(uuid_ids))
    if not db_episodes:
        return []

    fetch_list: list[tuple[str, str, dict[str, str]]] = []  # (replay_url, episode_id, tags)
    for ep in db_episodes:
        replay_url = ep.replay_url or ep.tags.get("replay_url")
        if replay_url:
            fetch_list.append((replay_url, str(ep.id), ep.tags))

    if not fetch_list:
        return []

    pv_uuid = UUID(policy_version_id)
    reward_lookup: dict[str, float] = {}
    for ep in db_episodes:
        avg_rewards = ep.avg_rewards
        reward_lookup[str(ep.id)] = float(avg_rewards.get(pv_uuid, 0.0) or 0.0)

    async def _fetch_one(client: httpx.AsyncClient, url: str) -> bytes | None:
        resp = await client.get(url, timeout=5.0)
        resp.raise_for_status()
        return resp.content

    async with httpx.AsyncClient() as client:
        tasks = [_fetch_one(client, url) for url, _, _ in fetch_list]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    summaries: list[dict[str, Any]] = []
    for (_replay_url, episode_id, tags), result in zip(fetch_list, results, strict=True):
        if isinstance(result, BaseException) or result is None:
            logger.debug("Failed to fetch replay for episode %s: %s", episode_id, result)
            continue
        replay = parse_replay(result)

        num_agents = int(replay.get("num_agents", 0) or 0)
        agent_indices = _agent_indices_from_tags(tags, policy_version_id, num_agents)

        reward = reward_lookup.get(episode_id, 0.0)
        summary = summarize_replay(
            replay,
            agent_indices=agent_indices,
            episode_idx=0,
            reward=reward,
            reason="selected",
        )
        if summary:
            summaries.append(summary.model_dump())

    return summaries


def create_dashboard_router() -> APIRouter:
    router = APIRouter(prefix="/dashboard/v1/policies/versions", tags=["dashboard"])

    @router.get("/default/data")
    @timed_http_handler
    async def get_default_dashboard_data(user: SoftmaxUser, include: str | None = None) -> DashboardResponse:
        async with db_session(read_only=True) as session:
            policy_version_id, _season = await _default_winner_policy_version_id(session)
        if not policy_version_id:
            raise HTTPException(status_code=404, detail="No default policy version available")
        return await get_dashboard_data(policy_version_id, user, include=include)

    @router.get("/{policy_version_id}/data")
    @timed_http_handler
    async def get_dashboard_data(
        policy_version_id: str,
        user: SoftmaxUser,
        include: str | None = None,
    ) -> DashboardResponse:
        """Compute dashboard data for a policy version."""
        include_flags = _parse_include_flags(include)
        pv_id, pv = await _require_policy_version(policy_version_id)
        raw_episodes, policy_jobs = await _fetch_policy_dashboard_sources(pv_id, DASHBOARD_LIMIT)

        policy_info = PolicyInfo(
            id=str(pv.id),
            name=pv.policy.name,
            version=pv.version,
        )

        season_name = "tournament"
        baseline_policy: PolicyInfo | None = None
        baseline_policy_version_id: UUID | None = None
        baseline_policy_jobs: Sequence[Any] = []
        recent_policy_versions: list[PolicyInfo] = []
        population_policy_versions: list[PolicyInfo] = []

        async with db_session(read_only=True) as session:
            season_query = (
                select(Season)
                .join(Pool, Pool.season_id == Season.id)  # pyright: ignore[reportArgumentType]
                .join(PoolPlayer, PoolPlayer.pool_id == Pool.id)  # pyright: ignore[reportArgumentType]
                .where(PoolPlayer.policy_version_id == pv_id)
                .order_by(col(Season.canonical).desc(), col(Season.version).desc(), col(Season.created_at).desc())
                .limit(1)
            )
            season_result = await session.execute(season_query)
            policy_season = season_result.scalar_one_or_none()

            leaderboard_by_policy_id: dict[str, tuple[int, float, int]] = {}
            if policy_season:
                season_name = (
                    policy_season.name if policy_season.canonical else f"{policy_season.name}:v{policy_season.version}"
                )
                if policy_season.name in SEASONS:
                    commissioner = await build_commissioner(policy_season.name, season_id=policy_season.id)
                    leaderboard = await commissioner.get_leaderboard()
                    leaderboard_by_policy_id = {
                        str(lb_policy_id): (rank, score, match_count)
                        for rank, (lb_policy_id, score, match_count) in enumerate(leaderboard, start=1)
                    }
                    population_policy_versions = [
                        PolicyInfo(
                            id=str(lb_policy_id),
                            name=str(lb_policy_id),
                            version=0,
                            rank=rank,
                            score=score,
                            matches=match_count,
                        )
                        for rank, (lb_policy_id, score, match_count) in enumerate(leaderboard, start=1)
                    ]
                    _apply_leaderboard_entry(policy_info, leaderboard_by_policy_id.get(str(pv_id)))

            # Compare against immediate previous version of the same policy.
            baseline_query = (
                select(PolicyVersion)
                .where(
                    PolicyVersion.policy_id == pv.policy_id,
                    PolicyVersion.version < pv.version,
                )
                .order_by(col(PolicyVersion.version).desc())
                .options(selectinload(PolicyVersion.policy))  # pyright: ignore[reportArgumentType]
                .limit(1)
            )
            baseline_result = await session.execute(baseline_query)
            baseline_version = baseline_result.scalar_one_or_none()
            if baseline_version:
                baseline_policy_version_id = baseline_version.id
                baseline_policy = PolicyInfo(
                    id=str(baseline_version.id),
                    name=baseline_version.policy.name,
                    version=baseline_version.version,
                )
                baseline_entry = leaderboard_by_policy_id.get(str(baseline_version.id))
                _apply_leaderboard_entry(baseline_policy, baseline_entry)

                baseline_policy_jobs = await _fetch_policy_episode_jobs(
                    session,
                    baseline_policy_version_id,
                    DASHBOARD_LIMIT,
                )

            recent_versions_query = (
                select(PolicyVersion)
                .where(
                    PolicyVersion.policy_id == pv.policy_id,
                    PolicyVersion.version <= pv.version,
                )
                .order_by(col(PolicyVersion.version).desc())
                .options(selectinload(PolicyVersion.policy))  # pyright: ignore[reportArgumentType]
                .limit(8)
            )
            recent_versions_result = await session.execute(recent_versions_query)
            recent_versions = recent_versions_result.scalars().all()
            recent_policy_versions = []
            for recent in recent_versions:
                recent_point = PolicyInfo(
                    id=str(recent.id),
                    name=recent.policy.name,
                    version=recent.version,
                )
                _apply_leaderboard_entry(recent_point, leaderboard_by_policy_id.get(str(recent.id)))
                recent_policy_versions.append(recent_point)

        outcome_summary = compute_outcome_summary(policy_info, season_name, baseline_policy)
        trend_summary = compute_version_trend_summary(recent_policy_versions)
        trend_explorer_summary = compute_trend_explorer_summary(
            recent_policy_versions,
            population_policy_versions,
        )

        # Cache for opponent policy lookups
        opponent_cache: dict[str, dict[str, Any]] = {}

        dashboard_episodes = await _build_sorted_dashboard_episodes(
            raw_episodes,
            policy_version_id=pv_id,
            policy_version_id_str=policy_version_id,
            policy_jobs=policy_jobs,
            opponent_cache=opponent_cache,
        )

        baseline_dashboard_episodes: list[DashboardEpisode] = []
        if baseline_policy_version_id is not None:
            baseline_raw_episodes = await episode_queries.get_episodes(
                primary_policy_version_ids=[baseline_policy_version_id],
                limit=DASHBOARD_LIMIT,
            )
            baseline_dashboard_episodes = await _build_sorted_dashboard_episodes(
                baseline_raw_episodes,
                policy_version_id=baseline_policy_version_id,
                policy_version_id_str=str(baseline_policy_version_id),
                policy_jobs=baseline_policy_jobs,
                opponent_cache=opponent_cache,
            )

        matchup_summary = compute_matchup_summary(
            dashboard_episodes,
            baseline_dashboard_episodes or None,
        )
        unsupported_summary = compute_unsupported_state(dashboard_episodes)
        instrumentation_summary = compute_instrumentation_validation(dashboard_episodes)
        stats_inventory_summary = compute_stats_inventory_summary(dashboard_episodes)
        confidence_summary = compute_confidence_summary(
            dashboard_episodes,
            baseline_dashboard_episodes,
        )
        crash_dump_summary = compute_crash_dump_summary(dashboard_episodes)
        selection_metadata = EpisodeSelectionMetadata(
            limit=DASHBOARD_LIMIT,
            offset=0,
            ordering="created_at_desc",
            sampled_episode_count=len(dashboard_episodes),
            includes_failed_jobs_without_episode=True,
            baseline_limit=DASHBOARD_LIMIT if baseline_policy_version_id is not None else None,
        )

        # Compute derived metrics
        if dashboard_episodes:
            derived = compute_derived_metrics(dashboard_episodes)
            team_comp_stats = compute_team_comp_analysis(dashboard_episodes)
            opponent_stats = compute_opponent_metrics(dashboard_episodes)
            failure_summary = compute_failure_summary(dashboard_episodes)
        else:
            derived = DerivedMetrics()
            team_comp_stats = []
            opponent_stats = {}
            failure_summary = FailureSummary()

        pattern_summary = compute_pattern_extraction_summary(
            outcome_summary,
            failure_summary,
            matchup_summary,
            instrumentation_summary,
            trend_explorer_summary,
            unsupported_summary,
        )
        action_summary = compute_action_summary(outcome_summary, failure_summary)
        orchestration_summary = compute_orchestration_hooks(
            policy_info,
            outcome_summary,
            failure_summary,
            action_summary,
            matchup_summary,
            confidence_summary,
            pattern_summary,
        )
        capability_code_audit = build_capability_code_audit()
        role_percentiles_summary = (
            await _build_role_percentiles_response(pv_id) if INCLUDE_ROLE_PERCENTILES in include_flags else None
        )
        diagnose_runs_summary = _build_diagnose_run_summaries() if INCLUDE_DIAGNOSE_RUNS in include_flags else None

        return DashboardResponse(
            policy=policy_info,
            episodes=dashboard_episodes,
            season=season_name,
            generated_at=datetime.now().isoformat(),
            selection=selection_metadata,
            role_percentiles=role_percentiles_summary,
            diagnose_runs=diagnose_runs_summary,
            derived=DashboardDerived(
                kpis=derived,
                team_comp=team_comp_stats,
                opponent_metrics=opponent_stats,
                outcome=outcome_summary,
                failures=failure_summary,
                unsupported=unsupported_summary,
                instrumentation=instrumentation_summary,
                stats_inventory=stats_inventory_summary,
                actions=action_summary,
                crash_dump=crash_dump_summary,
                matchup=matchup_summary,
                confidence=confidence_summary,
                orchestration=orchestration_summary,
                trend=trend_summary,
                trend_explorer=trend_explorer_summary,
                patterns=pattern_summary,
                capability_code_audit=capability_code_audit,
            ),
        )

    @router.post("/{policy_version_id}/analysis")
    @timed_http_handler
    async def get_dashboard_analysis(
        policy_version_id: str,
        request: Request,
        user: SoftmaxUser,
    ) -> DashboardAnalysisResponse:
        """Run Claude AI analysis on computed dashboard data."""
        request_api_key = request.headers.get("X-Anthropic-Api-Key", "").strip()

        now = time.time()
        user_key = user.email or str(user.id)
        timestamps = _analysis_rate_limit.get(user_key, [])
        timestamps = [t for t in timestamps if now - t < 3600]
        if len(timestamps) >= ANALYSIS_RATE_LIMIT:
            raise HTTPException(status_code=429, detail="Rate limit exceeded (10 requests/hour)")
        timestamps.append(now)
        _analysis_rate_limit[user_key] = timestamps

        pv_id, pv = await _require_policy_version(policy_version_id)

        raw_episodes, policy_jobs = await _fetch_policy_dashboard_sources(pv_id, DASHBOARD_LIMIT)

        opponent_cache: dict[str, dict[str, Any]] = {}
        dashboard_episodes = await _build_sorted_dashboard_episodes(
            raw_episodes,
            policy_version_id=pv_id,
            policy_version_id_str=policy_version_id,
            policy_jobs=policy_jobs,
            opponent_cache=opponent_cache,
        )

        kpis = compute_derived_metrics(dashboard_episodes) if dashboard_episodes else DerivedMetrics()

        claude_policy = claude_dashboard.PolicyInfo(
            id=str(pv.id),
            name=pv.policy.name,
            version=pv.version,
        )
        claude_kpis = claude_dashboard.DerivedMetrics.model_validate(kpis.model_dump())
        claude_episodes = [
            claude_dashboard.DashboardEpisode(
                episode_id=ep.episode_id,
                job_id=ep.job_id,
                opponent_name=ep.opponent_name,
                opponent_version=ep.opponent_version,
                team_composition=ep.team_composition,
                reward=ep.reward,
                status=ep.status,
                error_type=ep.error_type,
                steps=ep.steps,
                metrics=ep.metrics,
                replay_url=ep.replay_url,
            )
            for ep in dashboard_episodes
        ]

        summary = claude_dashboard.build_analysis_summary(
            claude_policy,
            claude_episodes,
            claude_kpis,
            season="tournament",
        )

        data_sources = ["kpis", "opponents", "team_comp"]
        episode_logs = claude_dashboard.compute_episode_logs(claude_episodes)
        if episode_logs:
            summary["episode_logs"] = episode_logs
            data_sources.append("episode_logs")

            snapshots = episode_logs.get("episode_snapshots", [])
            candidates = []
            for snap in snapshots:
                candidates.append(
                    {
                        "reward": snap.get("r", 0),
                        "replay_url": snap.get("replay_url", "has_replay"),
                        "episode_id": snap.get("id", ""),
                    }
                )
            selected = select_replay_episodes(candidates, max_n=3)
            episode_ids = [ep["episode_id"] for ep in selected if ep.get("episode_id")]
            if episode_ids:
                replay_summaries = await _fetch_and_summarize_replays(episode_ids, policy_version_id)
                if replay_summaries:
                    summary["replay_summaries"] = replay_summaries
                    data_sources.append("replays")

        prompt = claude_dashboard.build_analysis_prompt(summary)

        try:
            if request_api_key:
                analysis_text = await request_anthropic_message(
                    api_key=request_api_key,
                    prompt=prompt,
                    model="claude-sonnet-4-5-20250929",
                    max_tokens=2500,
                    timeout=60.0,
                )
            else:
                # Bedrock uses team AWS credits. This is safe while the endpoint is
                # SoftmaxUser-gated; add an API key requirement if opened to ExternalUser.
                analysis_text = await request_bedrock_message(
                    prompt=prompt,
                    model="global.anthropic.claude-sonnet-4-5-20250929-v1:0",
                    max_tokens=2500,
                    timeout=60.0,
                )
        except AnthropicTimeoutError as e:
            raise HTTPException(status_code=504, detail="Claude API timed out (60s limit)") from e
        except AnthropicHTTPError as e:
            if e.status_code == 401:
                raise HTTPException(status_code=502, detail="Anthropic API key is invalid or expired") from e
            raise HTTPException(
                status_code=502,
                detail=f"Claude API returned {e.status_code}: {e.response_text[:200]}",
            ) from e
        except AnthropicConnectionError as e:
            raise HTTPException(status_code=502, detail="Could not connect to Claude API (api.anthropic.com)") from e
        except AnthropicResponseFormatError as e:
            raise HTTPException(status_code=502, detail="Claude API returned an unexpected response format") from e

        return DashboardAnalysisResponse(analysis=analysis_text, data_sources=data_sources)

    @router.get("/{policy_version_id}/role-percentiles")
    @timed_http_handler
    async def get_dashboard_role_percentiles(
        policy_version_id: str,
        user: SoftmaxUser,
    ) -> DashboardRolePercentilesResponse:
        pv_id, _pv = await _require_policy_version(policy_version_id)
        return await _build_role_percentiles_response(pv_id)

    return router
