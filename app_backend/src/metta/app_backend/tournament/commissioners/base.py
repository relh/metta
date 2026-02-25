import asyncio
import hashlib
import inspect
import json
import logging
import os
import time
from abc import ABC, abstractmethod
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from metta_alo.scoring import compute_average_scores_per_agent
from opentelemetry import trace as otel_trace
from opentelemetry.trace import SpanKind
from opentelemetry.trace.status import Status, StatusCode
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import selectinload
from sqlmodel import col, select

# pyright: reportArgumentType=false, reportCallIssue=false
# SQLModel Relationship() type annotations cause false positives on join()/selectinload()
from metta.app_backend.clients.stats_client import StatsClient
from metta.app_backend.database import db_session, get_db, with_db
from metta.app_backend.models.episodes import Episode, EpisodePolicy, EpisodePolicyMetric
from metta.app_backend.models.job_request import JobRequest, JobRequestCreate, JobStatus, JobType
from metta.app_backend.models.policies import PolicyVersion
from metta.app_backend.models.tournament import (
    Match,
    MatchPlayer,
    MatchStatus,
    MembershipAction,
    MembershipChange,
    MettagridEnvConfig,
    Pool,
    PoolPlayer,
    Season,
)
from metta.app_backend.tournament.referees.base import (
    LeaderboardStatsRow,
    MatchCountEntry,
    MatchCounts,
    MatchRequest,
    RefereeBase,
)
from metta.app_backend.tournament.settings import (
    MAX_OUTSTANDING_MATCHES,
    POLL_INTERVAL_FAST_SECONDS,
    POLL_INTERVAL_SECONDS,
    settings,
)
from metta.common.compat_version import get_compat_version
from metta.common.otel.tracing import trace
from mettagrid.runner.types import SingleEpisodeJob

logger = logging.getLogger(__name__)
tracer = otel_trace.get_tracer(__name__)


def _rss_mb() -> str:
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return f"{int(line.split()[1]) // 1024}Mi"
    except OSError:
        pass
    return "?"


class MembershipChangeRequest(BaseModel):
    pool_name: str
    policy_version_id: UUID
    action: MembershipAction
    notes: str | None = None


class PoolDescription(BaseModel):
    name: str
    description: str


class SeasonDescription(BaseModel):
    summary: str
    pools: list[PoolDescription]


class CommissionerBase(ABC):
    season_name: str
    display_name: str
    referees: dict[str, RefereeBase]
    leaderboard_pool: str
    entry_pool: str
    # If False, season roll creates only the entry pool in the new version.
    roll_copy_existing_pools: bool = True
    summary: str = ""
    # Used only when creating the season. After creation, the DB value is
    # authoritative and must be bumped manually (e.g. via admin API or SQL).
    initial_compat_version: str | None = None

    def __init__(self, season_id: UUID) -> None:
        self.season_id: UUID = season_id

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if inspect.isabstract(cls):
            return
        season_name = getattr(cls, "season_name", None)
        display_name = getattr(cls, "display_name", None)
        if season_name is None and display_name is None:
            return
        if not isinstance(season_name, str) or not season_name:
            raise ValueError(f"{cls.__name__}.season_name must be a non-empty string")
        if not isinstance(display_name, str) or not display_name:
            raise ValueError(f"{cls.__name__}.display_name must be a non-empty string")
        referees = getattr(cls, "referees", None)
        if referees is None:
            return
        pool_names = set(referees.keys())
        for attr in ("leaderboard_pool", "entry_pool"):
            value = getattr(cls, attr, None)
            if value is not None and value not in pool_names:
                raise ValueError(f"{cls.__name__}.{attr}={value!r} is not in referees {pool_names}")

    def description_for_version(self, season_version: int = 1) -> SeasonDescription:
        referees = self.get_referees(season_version)
        return SeasonDescription(
            summary=self.summary,
            pools=[PoolDescription(name=name, description=ref.description) for name, ref in referees.items()],
        )

    @property
    def description(self) -> SeasonDescription:
        return self.description_for_version()

    def get_referees(self, season_version: int) -> dict[str, RefereeBase]:  # type: ignore[unused-parameter]
        return self.referees

    @classmethod
    def get_initial_season_fields(cls) -> dict[str, Any]:
        return {}

    async def _resolve_target_season(self) -> Season | None:
        db = get_db()
        return (await db.execute(select(Season).where(Season.id == self.season_id))).scalar_one_or_none()

    @abstractmethod
    def get_new_submission_membership_changes(self, policy_version_id: UUID) -> list[MembershipChangeRequest]:
        pass

    @abstractmethod
    async def get_membership_changes(self, pools: dict[str, Pool]) -> list[MembershipChangeRequest]:
        pass

    async def run(self) -> None:
        await self._ensure_season_exists()
        logger.info(
            f"Starting commissioner for season '{self.season_name}' "
            f"(initial_compat={self.initial_compat_version}, rss={_rss_mb()})"
        )
        while True:
            async with db_session(read_only=True):
                season = await self._resolve_target_season()
                if not season:
                    raise ValueError(f"Bound season '{self.season_id}' no longer exists")
                if season.disabled_at is not None:
                    logger.info(f"Season '{self.season_name}' is disabled, exiting commissioner")
                    return
                season_compat_version = season.compat_version
                server_compat_version = get_compat_version()
                if season_compat_version is not None and season_compat_version != server_compat_version:
                    logger.warning(
                        f"[{self.season_name}] season compat {season_compat_version} != "
                        f"server compat {server_compat_version} — game envs would be "
                        f"incompatible with episode-runner:compat-v{season_compat_version}, exiting commissioner"
                    )
                    return

            had_activity = False
            start = time.monotonic()
            try:
                had_activity = await self._run_cycle()
            except Exception as e:
                logger.error(f"Commissioner cycle error: {e}", exc_info=True)
            interval = POLL_INTERVAL_FAST_SECONDS if had_activity else POLL_INTERVAL_SECONDS
            elapsed = time.monotonic() - start
            await asyncio.sleep(max(0, interval - elapsed))

    @with_db
    async def _ensure_season_exists(self) -> None:
        season = await self._resolve_target_season()
        if not season:
            raise ValueError(f"Bound season '{self.season_id}' not found")

    @trace("commissioner.run_cycle")
    @with_db
    async def _run_cycle(self) -> bool:
        """Run one cycle of the commissioner. Returns True if there was activity."""
        span = otel_trace.get_current_span()
        if span.is_recording():
            span.set_attribute("tournament.season", self.season_name)

        logger.info(f"[{self.season_name}] cycle start (rss={_rss_mb()})")

        season = await self._resolve_target_season()
        if not season:
            raise ValueError(f"Bound season '{self.season_id}' not found - is the tournament running?")
        referees = self.get_referees(season.version)

        pools = await self._ensure_pools_exist(season, referees)
        logger.info(f"[{self.season_name}] pools loaded: {list(pools.keys())} (rss={_rss_mb()})")

        status_changed = await self._sync_match_statuses()
        logger.info(f"[{self.season_name}] match statuses synced, changed={status_changed} (rss={_rss_mb()})")

        outstanding = await self._count_outstanding_matches()
        slots_available = max(0, MAX_OUTSTANDING_MATCHES - outstanding)
        logger.info(f"[{self.season_name}] outstanding={outstanding} slots={slots_available} (rss={_rss_mb()})")

        total_scheduled = 0
        for pool_name, pool in pools.items():
            if pool_name not in referees:
                continue
            if slots_available <= 0:
                logger.info(f"[{self.season_name}] no slots left, skipping remaining pools")
                break
            referee = referees[pool_name]
            players = await self._get_pool_players(pool.id)
            active_ids = {p.id for p in players}
            match_counts = await self._get_match_counts(pool.id, active_ids)
            logger.info(
                f"[{self.season_name}] pool={pool_name} players={len(players)}"
                f" match_combos={len(match_counts)} (rss={_rss_mb()})"
            )

            requests = referee.get_matches_to_schedule(players, match_counts, limit=slots_available)
            logger.info(f"[{self.season_name}] pool={pool_name} matches_to_schedule={len(requests)}")
            for req in requests:
                success = await self._create_and_dispatch_match(pool.id, req, season.compat_version)
                if success:
                    total_scheduled += 1
                    slots_available -= 1

        if total_scheduled > 0:
            logger.info(f"Scheduled {total_scheduled} new matches")

        logger.info(f"[{self.season_name}] scheduling done, getting membership changes (rss={_rss_mb()})")
        changes = await self.get_membership_changes(pools)
        logger.info(f"[{self.season_name}] membership changes={len(changes)} (rss={_rss_mb()})")
        await self._apply_membership_changes(changes)

        logger.info(f"[{self.season_name}] cycle complete (rss={_rss_mb()})")
        return status_changed or total_scheduled > 0 or len(changes) > 0

    async def _get_pools(self, season_id: UUID) -> dict[str, Pool]:
        session = get_db()
        pools = (
            (await session.execute(select(Pool).where(Pool.season_id == season_id).options(selectinload(Pool.players))))
            .scalars()
            .all()
        )
        return {p.name: p for p in pools if p.name}

    async def _get_season_matches(self) -> list[Match]:
        season = await self._resolve_target_season()
        if not season:
            raise ValueError(f"Bound season '{self.season_id}' not found")
        session = get_db()
        matches = (
            (
                await session.execute(
                    select(Match)
                    .join(Match.pool)
                    .where(Pool.season_id == season.id)
                    .options(selectinload(Match.players))
                    .order_by(col(Match.created_at).desc())
                )
            )
            .scalars()
            .all()
        )
        return list(matches)

    async def _ensure_pools_exist(self, season: Season, referees: dict[str, RefereeBase]) -> dict[str, Pool]:
        session = get_db()
        logger.info(f"[{self.season_name}] _ensure_pools_exist: loading pools (rss={_rss_mb()})")

        existing = list((await session.execute(select(Pool).filter_by(season_id=season.id))).scalars().all())
        existing_names = {p.name for p in existing if p.name}

        for name in referees:
            if name not in existing_names:
                session.add(Pool(season_id=season.id, name=name))
                logger.info(f"Created pool '{name}' for season '{self.season_name}'")

        await session.commit()

        pools_by_name = await self._get_pools(season.id)

        for pool_name, referee in referees.items():
            pool = pools_by_name.get(pool_name)
            if not pool:
                continue
            config_data = referee.make_env(seed=0).model_dump(mode="json")
            config_hash = hashlib.sha256(json.dumps(config_data, sort_keys=True).encode()).hexdigest()
            stmt = (
                pg_insert(MettagridEnvConfig)
                .values(config_hash=config_hash, config=config_data)
                .on_conflict_do_nothing(index_elements=["config_hash"])
                .returning(MettagridEnvConfig)
            )
            result = (await session.execute(stmt)).scalar_one_or_none()
            if result:
                env_config = result
            else:
                env_config = (
                    await session.execute(select(MettagridEnvConfig).filter_by(config_hash=config_hash))
                ).scalar_one()
            if pool.env_config_id != env_config.id:
                pool.env_config_id = env_config.id

        await session.commit()
        return pools_by_name

    @trace("commissioner.sync_match_statuses")
    async def _sync_match_statuses(self) -> bool:
        """Sync match statuses from job statuses. Returns True if any changed."""
        session = get_db()

        logger.info(f"[{self.season_name}] _sync_match_statuses: querying (rss={_rss_mb()})")
        pending = list(
            (
                await session.execute(
                    select(Match)
                    .join(Match.pool)
                    .join(Pool.season)
                    .where(Season.id == self.season_id)
                    .where(col(Match.status).in_([MatchStatus.scheduled, MatchStatus.running]))
                    .options(selectinload(Match.job))
                )
            )
            .scalars()
            .all()
        )
        logger.info(f"[{self.season_name}] _sync_match_statuses: loaded {len(pending)} pending (rss={_rss_mb()})")

        updated = 0
        for match in pending:
            job = match.job
            if not job:
                continue
            if job.status == JobStatus.running and match.status != MatchStatus.running:
                match.status = MatchStatus.running
                updated += 1
            elif job.status == JobStatus.completed:
                match.status = MatchStatus.completed
                match.completed_at = datetime.now(UTC)
                updated += 1
            elif job.status == JobStatus.failed:
                match.status = MatchStatus.failed
                updated += 1

        if updated > 0:
            logger.info(f"Updated {updated} match statuses")
            await session.commit()

        scores_updated = await self._sync_match_scores()
        return updated > 0 or scores_updated

    async def _sync_match_scores(self) -> bool:
        """Sync match scores from episode metrics. Returns True if any updated."""
        session = get_db()

        logger.info(f"[{self.season_name}] _sync_match_scores: querying unscored (rss={_rss_mb()})")
        matches_with_episodes = (
            await session.execute(
                select(Match, JobRequest.episode_id)
                .join(Match.pool)
                .join(Pool.season)
                .join(Match.job)
                .join(Match.players)
                .where(Season.id == self.season_id)
                .where(Match.status == MatchStatus.completed)
                .where(JobRequest.episode_id.is_not(None))
                .where(col(MatchPlayer.score).is_(None))
                .options(selectinload(Match.players).selectinload(MatchPlayer.pool_player))
                .distinct()
            )
        ).all()
        logger.info(
            f"[{self.season_name}] _sync_match_scores: loaded {len(matches_with_episodes)} unscored (rss={_rss_mb()})"
        )

        # Filter to only matches with unscored players
        matches_needing_scores: list[tuple[Match, str]] = []
        for match, episode_id in matches_with_episodes:
            if episode_id and any(mp.score is None for mp in match.players):
                matches_needing_scores.append((match, episode_id))

        if not matches_needing_scores:
            return False

        episode_ids = [ep_id for _, ep_id in matches_needing_scores]

        # Get scores from episode metrics
        scores_result = await session.execute(
            select(
                col(Episode.id).label("episode_id"),
                col(PolicyVersion.id).label("policy_version_id"),
                col(EpisodePolicyMetric.value).label("reward"),
                col(EpisodePolicy.num_agents).label("num_agents"),
            )
            .join(EpisodePolicy, EpisodePolicy.episode_id == Episode.id)
            .join(PolicyVersion, PolicyVersion.id == EpisodePolicy.policy_version_id)
            .join(
                EpisodePolicyMetric,
                (EpisodePolicyMetric.episode_internal_id == Episode.internal_id)
                & (EpisodePolicyMetric.pv_internal_id == PolicyVersion.internal_id),
            )
            .where(EpisodePolicyMetric.metric_name == "reward")
            .where(col(Episode.id).in_(episode_ids))
        )

        scores_by_episode: dict[str, dict[UUID, float]] = defaultdict(dict)
        agent_counts_by_episode: dict[str, dict[UUID, int]] = defaultdict(dict)
        for row in scores_result.all():
            ep_id = str(row.episode_id) if row.episode_id else None
            pv_id = row.policy_version_id
            num_agents = row.num_agents
            if ep_id and pv_id:
                scores_by_episode[ep_id][pv_id] = row.reward
                if num_agents is not None:
                    agent_counts_by_episode[ep_id][pv_id] = num_agents

        if not scores_by_episode:
            return False

        updated = 0
        for match, episode_id in matches_needing_scores:
            episode_scores = scores_by_episode.get(episode_id, {})
            episode_agent_counts = agent_counts_by_episode.get(episode_id, {})
            per_agent_scores = compute_average_scores_per_agent(
                episode_scores,
                agent_counts=episode_agent_counts,
            )
            for mp in match.players:
                if mp.score is not None:
                    continue
                pv_id = mp.pool_player.policy_version_id
                if pv_id in per_agent_scores:
                    total_reward = episode_scores.get(pv_id, 0.0)
                    mp.score = per_agent_scores[pv_id]
                    logger.info(
                        f"Score calc: match={match.id}, pv={pv_id}, total_reward={total_reward}, score={mp.score}"
                    )
                    updated += 1

        if updated > 0:
            logger.info(f"Updated {updated} match player scores")
        await session.commit()
        return updated > 0

    async def _get_pool_players(self, pool_id: UUID) -> list[PoolPlayer]:
        session = get_db()
        return list(
            (await session.execute(select(PoolPlayer).filter_by(pool_id=pool_id, retired=False))).scalars().all()
        )

    async def _count_outstanding_matches(self) -> int:
        session = get_db()
        result = await session.execute(
            select(func.count())
            .select_from(Match)
            .join(Match.pool)
            .join(Pool.season)
            .where(Season.id == self.season_id)
            .where(col(Match.status).in_([MatchStatus.pending, MatchStatus.scheduled, MatchStatus.running]))
        )
        return result.scalar_one()

    async def _get_match_counts(self, pool_id: UUID, active_player_ids: set[UUID]) -> MatchCounts:
        if not active_player_ids:
            return {}
        session = get_db()

        result = await session.execute(
            select(Match.id, Match.assignments, Match.status, MatchPlayer.pool_player_id)
            .join(MatchPlayer, MatchPlayer.match_id == Match.id)
            .where(Match.pool_id == pool_id)
            .where(col(MatchPlayer.pool_player_id).in_(active_player_ids))
        )

        matches: dict[UUID, tuple[list[UUID], list[int], MatchStatus]] = {}
        for row in result.all():
            match_id, assignments, status, pp_id = row.id, row.assignments, row.status, row.pool_player_id
            if match_id not in matches:
                matches[match_id] = ([], assignments, status)
            matches[match_id][0].append(pp_id)

        counts: MatchCounts = {}
        zero_counts = MatchCountEntry.zero()
        for players, assignments, status in matches.values():
            if not all(p in active_player_ids for p in players):
                continue
            combo = tuple(sorted(players))
            key = (combo, tuple(assignments))
            prev = counts.get(key, zero_counts)
            if status == MatchStatus.completed:
                counts[key] = MatchCountEntry(prev.completed + 1, prev.failed, prev.in_progress)
            elif status == MatchStatus.failed:
                counts[key] = MatchCountEntry(prev.completed, prev.failed + 1, prev.in_progress)
            else:
                counts[key] = MatchCountEntry(prev.completed, prev.failed, prev.in_progress + 1)
        return counts

    @with_db
    async def submit(self, policy_version_id: UUID) -> list[str]:
        changes = self.get_new_submission_membership_changes(policy_version_id)
        await self._apply_membership_changes(changes)
        return [c.pool_name for c in changes if c.action == MembershipAction.add]

    async def _resolve_leaderboard_pool_and_referee(self, target_pool: str) -> tuple[Pool, RefereeBase] | None:
        session = get_db()
        row = (
            await session.execute(
                select(Pool, Season).join(Pool.season).where(Pool.season_id == self.season_id, Pool.name == target_pool)
            )
        ).one_or_none()
        if not row:
            return None

        pool, season = row
        referee = self.get_referees(season.version).get(target_pool)
        if not referee:
            return None
        return pool, referee

    @with_db
    async def get_leaderboard(self, pool_name: str | None = None) -> list[tuple[UUID, float, int]]:
        return [
            (row.policy_version_id, row.score, row.match_count)
            for row in await self.get_leaderboard_with_stats(pool_name=pool_name)
        ]

    @with_db
    async def get_leaderboard_with_stats(self, pool_name: str | None = None) -> list[LeaderboardStatsRow]:
        target_pool = pool_name or self.leaderboard_pool
        pool_and_referee = await self._resolve_leaderboard_pool_and_referee(target_pool)
        if not pool_and_referee:
            return []
        pool, referee = pool_and_referee
        return await referee.get_leaderboard_with_stats(pool.id)

    @with_db
    async def get_matches(self, pool_name: str, limit: int = 50, offset: int = 0) -> list[Match]:
        session = get_db()
        pool = (
            await session.execute(
                select(Pool).join(Pool.season).where(Season.id == self.season_id).where(Pool.name == pool_name)
            )
        ).scalar_one_or_none()
        if not pool:
            raise ValueError(f"Pool '{pool_name}' not found")

        matches = (
            (
                await session.execute(
                    select(Match)
                    .filter_by(pool_id=pool.id)
                    .options(selectinload(Match.players))
                    .order_by(col(Match.created_at).desc())
                    .offset(offset)
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        return list(matches)

    async def _apply_membership_changes(self, changes: list[MembershipChangeRequest]) -> None:
        if not changes:
            return
        session = get_db()

        pool_names = {c.pool_name for c in changes}
        pools_result = await session.execute(
            select(Pool).join(Pool.season).where(Season.id == self.season_id).where(col(Pool.name).in_(pool_names))
        )
        pools = {p.name: p for p in pools_result.scalars().all() if p.name}

        all_pool_ids = {p.id for p in pools.values()}
        all_pv_ids = {c.policy_version_id for c in changes}

        existing_players: dict[tuple[UUID, UUID], PoolPlayer] = {}
        if all_pool_ids and all_pv_ids:
            result = await session.execute(
                select(PoolPlayer)
                .where(col(PoolPlayer.pool_id).in_(all_pool_ids))
                .where(col(PoolPlayer.policy_version_id).in_(all_pv_ids))
            )
            for player in result.scalars().all():
                existing_players[(player.pool_id, player.policy_version_id)] = player

        sorted_changes = sorted(changes, key=lambda c: (c.policy_version_id, c.action))
        ts = datetime.now(UTC)

        for change in sorted_changes:
            pool = pools.get(change.pool_name)
            if not pool:
                continue
            key = (pool.id, change.policy_version_id)

            if change.action == MembershipAction.add:
                if key in existing_players:
                    continue
                player = PoolPlayer(pool_id=pool.id, policy_version_id=change.policy_version_id)
                session.add(player)
                session.add(
                    MembershipChange(
                        pool_player=player,
                        action=MembershipAction.add,
                        notes=change.notes,
                        created_at=ts,
                    )
                )
                existing_players[key] = player
                logger.info(f"Added {change.policy_version_id} to pool '{change.pool_name}'")

            elif change.action == MembershipAction.remove:
                player = existing_players.get(key)
                if player and not player.retired:
                    player.retired = True
                    session.add(
                        MembershipChange(
                            pool_player_id=player.id,
                            action=MembershipAction.remove,
                            notes=change.notes,
                            created_at=ts,
                        )
                    )
                    logger.info(f"Retired {change.policy_version_id} from pool '{change.pool_name}'")

        await session.commit()

    async def _create_and_dispatch_match(
        self, pool_id: UUID, request: MatchRequest, compat_version: str | None = None
    ) -> bool:
        with tracer.start_as_current_span("tournament.job.enqueue", kind=SpanKind.PRODUCER) as span:
            span.set_attribute("tournament.season", self.season_name)
            span.set_attribute("tournament.pool_id", str(pool_id))
            span.set_attribute("job.type", JobType.episode.value)
            span.set_attribute("job.queue", "episode-runner")

            session = get_db()

            pv_result = await session.execute(
                select(PoolPlayer.id, PoolPlayer.policy_version_id).where(
                    col(PoolPlayer.id).in_(request.pool_player_ids)
                )
            )
            pv_ids = {row[0]: row[1] for row in pv_result.all()}

            missing = set(request.pool_player_ids) - set(pv_ids.keys())
            if missing:
                logger.error(f"PoolPlayers not found when creating match: {missing}")
                span.set_attribute("job.enqueue.outcome", "failure")
                span.set_status(Status(StatusCode.ERROR, "pool_players_missing"))
                return False

            # Commit to release transaction before HTTP call
            await session.commit()

            match = Match(pool_id=pool_id, assignments=request.assignments, team_id=request.team_id)  # type: ignore[call-arg]
            match_id = match.id
            span.set_attribute("match.id", str(match_id))

            tags = {k: str(v) for k, v in request.episode_tags.model_dump(exclude_none=True).items()}
            if git_ref := os.environ.get("GIT_COMMIT"):
                tags["scheduler_git_ref"] = git_ref
            job_spec = SingleEpisodeJob(
                policy_uris=[f"metta://policy/{pv_ids[pp_id]}" for pp_id in request.pool_player_ids],
                assignments=request.assignments,
                env=request.env,
                seed=request.seed,
                episode_tags=tags,
            ).model_dump()

            if compat_version is not None:
                registry = os.environ.get("EPISODE_RUNNER_REGISTRY", "ghcr.io/metta-ai/episode-runner")
                job_spec["episode_runner_image"] = f"{registry}:compat-v{compat_version}"

            stats_client = StatsClient(settings.STATS_SERVER_URI, machine_token=settings.MACHINE_TOKEN)
            try:
                job_ids = await asyncio.to_thread(
                    stats_client.create_jobs, [JobRequestCreate(job_type=JobType.episode, job=job_spec)]
                )
                job_id = job_ids[0] if job_ids else None
            except Exception as e:
                span.record_exception(e)
                span.set_attribute("job.enqueue.outcome", "failure")
                span.set_status(Status(StatusCode.ERROR, "job_create_failed"))
                logger.error(f"Failed to create job for match {match_id}: {e}")
                return False
            finally:
                stats_client.close()

            if not job_id:
                span.set_attribute("job.enqueue.outcome", "failure")
                span.set_status(Status(StatusCode.ERROR, "job_id_missing"))
                logger.error(f"Failed to create job for match {match_id}")
                return False

            span.set_attribute("job.id", str(job_id))
            span.set_attribute("job.enqueue.outcome", "success")

            match.job_id = job_id
            match.status = MatchStatus.scheduled
            session.add(match)
            session.add_all(
                [
                    MatchPlayer(match_id=match.id, pool_player_id=pp_id, policy_index=idx)
                    for idx, pp_id in enumerate(request.pool_player_ids)
                ]
            )
            await session.commit()

            logger.debug(f"Match {match_id} -> job {job_id}")
            return True
