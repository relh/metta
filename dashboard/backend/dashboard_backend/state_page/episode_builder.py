"""Helpers for constructing dashboard episodes from episode/job records."""

import ast
from typing import Any, Sequence
from uuid import UUID

from dashboard.backend.dashboard_backend.state_page.diagnostics import DashboardEpisode, compute_episode_diagnostic_tags
from metta.app_backend.models.job_request import JobStatus
from metta.app_backend.queries import policy_queries


def _parse_tag_list(raw_value: Any) -> list[Any]:
    if isinstance(raw_value, list):
        return raw_value
    if not isinstance(raw_value, str) or not raw_value:
        return []
    try:
        parsed = ast.literal_eval(raw_value)
    except (ValueError, SyntaxError):
        return []
    return parsed if isinstance(parsed, list) else []


def _parse_assignments(raw_value: Any) -> list[int]:
    return [assignment for assignment in _parse_tag_list(raw_value) if isinstance(assignment, int)]


def _resolve_policy_index(policy_version_id: str, raw_policy_version_ids: Any) -> int:
    policy_version_ids = [str(policy_id) for policy_id in _parse_tag_list(raw_policy_version_ids)]
    return policy_version_ids.index(policy_version_id) if policy_version_id in policy_version_ids else 0


def _compute_team_comp(assignments: list[int], policy_index: int) -> str:
    if not assignments:
        return "?v?"
    my_count = sum(1 for assignment in assignments if assignment == policy_index)
    return f"{my_count}v{len(assignments) - my_count}"


def _extract_job_error_details(job: Any | None) -> tuple[str | None, dict[str, Any]]:
    if job is None:
        return (None, {})

    error_message = job.error.strip() if isinstance(job.error, str) and job.error.strip() else None
    error_context: dict[str, Any] = {}
    if isinstance(job.result, dict):
        for key in ("error", "message", "traceback", "stderr", "exception"):
            value = job.result.get(key)
            if isinstance(value, str) and value.strip():
                if error_message is None and key in {"error", "message"}:
                    error_message = value.strip()
                error_context[key] = value.strip()
            elif isinstance(value, (int, float, bool)):
                error_context[key] = value
    return (error_message, error_context)


def _format_timestamp(value: Any) -> str | None:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if value is not None:
        return str(value)
    return None


async def build_dashboard_episodes(
    *,
    raw_episodes: list[Any],
    policy_version_id: UUID,
    policy_version_id_str: str,
    policy_jobs: Sequence[Any],
    opponent_cache: dict[str, dict[str, Any]],
) -> list[DashboardEpisode]:
    unique_policy_jobs: list[Any] = []
    seen_policy_job_ids: set[str] = set()
    for job in policy_jobs:
        job_id = str(job.id)
        if job_id in seen_policy_job_ids:
            continue
        seen_policy_job_ids.add(job_id)
        unique_policy_jobs.append(job)

    job_info_by_id = {str(job.id): job for job in unique_policy_jobs}
    dashboard_episodes: list[DashboardEpisode] = []
    seen_job_ids: set[str] = set()

    for ep in raw_episodes:
        episode_id = str(ep.id)
        job_id = str(ep.job_id) if ep.job_id else ""
        if job_id:
            seen_job_ids.add(job_id)

        avg_rewards = ep.avg_rewards
        my_reward = float(avg_rewards.get(policy_version_id, 0.0) or 0.0)

        opponent_id = next((reward_pv_id for reward_pv_id in avg_rewards if reward_pv_id != policy_version_id), None)

        opponent_name = "unknown"
        opponent_version = 0
        if opponent_id:
            opp_key = str(opponent_id)
            if opp_key not in opponent_cache:
                opp_pv = await policy_queries.get_policy_version_with_name(opponent_id)
                if opp_pv:
                    opponent_cache[opp_key] = {
                        "name": opp_pv.policy.name,
                        "version": opp_pv.version,
                    }
            if opp_key in opponent_cache:
                opponent_name = opponent_cache[opp_key]["name"]
                opponent_version = opponent_cache[opp_key]["version"]

        tags = ep.tags
        raw_tags = {key: str(value) for key, value in tags.items()}
        assignments = _parse_assignments(tags.get("assignments"))
        policy_index = (
            _resolve_policy_index(policy_version_id_str, tags.get("policy_version_ids")) if assignments else 0
        )
        team_comp = _compute_team_comp(assignments, policy_index)

        attributes = ep.attributes or {}
        stats = attributes.get("stats", {})
        agent_stats = stats.get("agent", [])

        metrics: dict[str, float] = {}
        if agent_stats and assignments:
            my_agent_indices = [i for i, assignment in enumerate(assignments) if assignment == policy_index]
            for idx in my_agent_indices:
                if idx < len(agent_stats):
                    agent = agent_stats[idx]
                    for key, value in agent.items():
                        if value is not None and isinstance(value, (int, float)):
                            metrics[key] = metrics.get(key, 0) + value

        team_stats = stats.get("team", {})
        if isinstance(team_stats, dict):
            for key, value in team_stats.items():
                if value is not None and isinstance(value, (int, float)):
                    metrics[f"team.{key}"] = value

        game_stats = stats.get("game", {})
        if isinstance(game_stats, dict):
            for key, value in game_stats.items():
                if value is not None and isinstance(value, (int, float)):
                    metrics[f"game.{key}"] = value

        steps = attributes.get("steps", 0)
        job_info = job_info_by_id.get(job_id)
        status = "failed" if job_info and job_info.status == JobStatus.failed else "completed"
        error_type = job_info.error_type if job_info else None
        error_message, error_context = _extract_job_error_details(job_info)

        dashboard_ep = DashboardEpisode(
            episode_id=episode_id,
            job_id=job_id,
            created_at=_format_timestamp(ep.created_at),
            replay_url=ep.replay_url,
            thumbnail_url=ep.thumbnail_url,
            opponent_name=opponent_name,
            opponent_version=opponent_version,
            team_composition=team_comp,
            reward=my_reward,
            status=status,
            error_type=error_type,
            error_message=error_message,
            error_context=error_context,
            steps=steps,
            raw_tags=raw_tags,
            metrics=metrics,
        )
        dashboard_ep.diagnostic_tags = compute_episode_diagnostic_tags(dashboard_ep)
        dashboard_episodes.append(dashboard_ep)

    for job in unique_policy_jobs:
        job_id = str(job.id)
        if job_id in seen_job_ids or job.status != JobStatus.failed:
            continue
        seen_job_ids.add(job_id)

        error_message, error_context = _extract_job_error_details(job)
        failed_dashboard_episode = DashboardEpisode(
            episode_id=f"failed-job-{job_id}",
            job_id=job_id,
            created_at=_format_timestamp(job.created_at),
            opponent_name="unknown",
            opponent_version=0,
            team_composition="?v?",
            reward=0.0,
            status="failed",
            error_type=job.error_type or "unknown",
            error_message=error_message,
            error_context=error_context,
            steps=0,
            raw_tags={},
            metrics={},
        )
        failed_dashboard_episode.diagnostic_tags = compute_episode_diagnostic_tags(failed_dashboard_episode)
        dashboard_episodes.append(failed_dashboard_episode)

    return dashboard_episodes
