"""Dashboard routes for policy performance analysis."""

import ast
import logging
import time
from datetime import datetime
from typing import Any
from uuid import UUID

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from metta.app_backend.auth import CheckUser
from metta.app_backend.config import settings
from metta.app_backend.dashboard import (
    DashboardDerived,
    DashboardEpisode,
    DashboardResponse,
    DerivedMetrics,
    PolicyInfo,
    build_analysis_prompt,
    compute_derived_metrics,
    compute_opponent_metrics,
    compute_team_comp_analysis,
)
from metta.app_backend.queries import episode_queries, policy_queries
from metta.app_backend.route_logger import timed_http_handler

logger = logging.getLogger(__name__)

# Simple in-memory rate limit: user_email -> list of request timestamps
_analysis_rate_limit: dict[str, list[float]] = {}
ANALYSIS_RATE_LIMIT = 10  # requests per hour


class AnalysisRequest(BaseModel):
    summary: dict[str, Any]


class AnalysisResponse(BaseModel):
    analysis: str


def create_dashboard_router() -> APIRouter:
    router = APIRouter(prefix="/stats/policies/versions", tags=["dashboard"])

    @router.post("/{policy_version_id}/dashboard-data")
    @timed_http_handler
    async def get_dashboard_data(policy_version_id: str, user: CheckUser) -> DashboardResponse:
        """Compute dashboard data for a policy version."""
        pv_id = UUID(policy_version_id)

        # Fetch policy version info
        pv = await policy_queries.get_policy_version_by_id(pv_id)
        if not pv:
            raise HTTPException(status_code=404, detail="Policy version not found")

        policy_info = PolicyInfo(
            id=str(pv.id),
            name=pv.policy.name,
            version=pv.version,
        )

        # Fetch episodes
        raw_episodes = await episode_queries.get_episodes(
            primary_policy_version_ids=[pv_id],
            limit=100,
        )

        if not raw_episodes:
            return DashboardResponse(
                policy=policy_info,
                episodes=[],
                season="tournament",
                generated_at=datetime.now().isoformat(),
                derived=DashboardDerived(
                    kpis=DerivedMetrics(),
                    team_comp=[],
                    opponent_metrics={},
                ),
            )

        # Cache for opponent policy lookups
        opponent_cache: dict[str, dict[str, Any]] = {}

        # Convert raw episodes to DashboardEpisode
        dashboard_episodes: list[DashboardEpisode] = []

        for ep in raw_episodes:
            episode_id = str(ep.id)
            job_id = str(ep.job_id) if ep.job_id else ""

            # Get reward from avg_rewards
            avg_rewards = ep.avg_rewards
            my_reward = float(avg_rewards.get(pv_id, 0.0) or 0.0)

            # Find opponent
            opponent_id = None
            for reward_pv_id in avg_rewards:
                if reward_pv_id != pv_id:
                    opponent_id = reward_pv_id
                    break

            # Look up opponent name
            opponent_name = "unknown"
            opponent_version = 0
            if opponent_id:
                opp_key = str(opponent_id)
                if opp_key not in opponent_cache:
                    opp_pv = await policy_queries.get_policy_version_by_id(opponent_id)
                    if opp_pv:
                        opponent_cache[opp_key] = {
                            "name": opp_pv.policy.name,
                            "version": opp_pv.version,
                        }
                if opp_key in opponent_cache:
                    opponent_name = opponent_cache[opp_key]["name"]
                    opponent_version = opponent_cache[opp_key]["version"]

            # Parse team composition from tags
            tags = ep.tags
            assignments_str = tags.get("assignments", "[]")
            try:
                assignments = ast.literal_eval(assignments_str)
            except Exception:
                assignments = []

            policy_index = 0
            policy_version_ids_str = tags.get("policy_version_ids", "")
            if policy_version_ids_str and assignments:
                try:
                    pv_ids_list = ast.literal_eval(policy_version_ids_str)
                    if policy_version_id in pv_ids_list:
                        policy_index = pv_ids_list.index(policy_version_id)
                except Exception:
                    pass

            # Team comp string
            if assignments:
                my_count = sum(1 for a in assignments if a == policy_index)
                opponent_count = len(assignments) - my_count
                team_comp = f"{my_count}v{opponent_count}"
            else:
                team_comp = "?v?"

            # Aggregate agent metrics for our policy
            attributes = ep.attributes or {}
            stats = attributes.get("stats", {})
            agent_stats = stats.get("agent", [])

            metrics: dict[str, float] = {}
            if agent_stats and assignments:
                my_agent_indices = [i for i, a in enumerate(assignments) if a == policy_index]
                for idx in my_agent_indices:
                    if idx < len(agent_stats):
                        agent = agent_stats[idx]
                        for key, value in agent.items():
                            if value is not None and isinstance(value, (int, float)):
                                metrics[key] = metrics.get(key, 0) + value

            # Extract collective/game stats
            collective_stats = stats.get("collective", {})
            if isinstance(collective_stats, dict):
                for key, value in collective_stats.items():
                    if value is not None and isinstance(value, (int, float)):
                        metrics[f"collective.{key}"] = value

            game_stats = stats.get("game", {})
            if isinstance(game_stats, dict):
                for key, value in game_stats.items():
                    if value is not None and isinstance(value, (int, float)):
                        metrics[f"game.{key}"] = value

            steps = attributes.get("steps", 0)

            dashboard_ep = DashboardEpisode(
                episode_id=episode_id,
                job_id=job_id,
                opponent_name=opponent_name,
                opponent_version=opponent_version,
                team_composition=team_comp,
                reward=my_reward,
                status="completed",
                steps=steps,
                metrics=metrics,
            )
            dashboard_episodes.append(dashboard_ep)

        # Compute derived metrics
        derived = compute_derived_metrics(dashboard_episodes)
        team_comp_stats = compute_team_comp_analysis(dashboard_episodes)
        opponent_stats = compute_opponent_metrics(dashboard_episodes)

        return DashboardResponse(
            policy=policy_info,
            episodes=dashboard_episodes,
            season="tournament",
            generated_at=datetime.now().isoformat(),
            derived=DashboardDerived(
                kpis=derived,
                team_comp=team_comp_stats,
                opponent_metrics=opponent_stats,
            ),
        )

    @router.post("/{policy_version_id}/dashboard-analysis")
    @timed_http_handler
    async def get_dashboard_analysis(
        policy_version_id: str, request: AnalysisRequest, user: CheckUser
    ) -> AnalysisResponse:
        """Run Claude AI analysis on pre-computed dashboard summary."""
        if not settings.ANTHROPIC_API_KEY:
            raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not configured")

        # Rate limit
        now = time.time()
        user_key = user.email or str(user.id)
        timestamps = _analysis_rate_limit.get(user_key, [])
        # Remove entries older than 1 hour
        timestamps = [t for t in timestamps if now - t < 3600]
        if len(timestamps) >= ANALYSIS_RATE_LIMIT:
            raise HTTPException(status_code=429, detail="Rate limit exceeded (10 requests/hour)")
        timestamps.append(now)
        _analysis_rate_limit[user_key] = timestamps

        prompt = build_analysis_prompt(request.summary)

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": settings.ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                },
                json={
                    "model": "claude-sonnet-4-5-20250929",
                    "max_tokens": 2000,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=60.0,
            )
            response.raise_for_status()

        data = response.json()
        analysis_text = data["content"][0]["text"].strip()
        return AnalysisResponse(analysis=analysis_text)

    return router
