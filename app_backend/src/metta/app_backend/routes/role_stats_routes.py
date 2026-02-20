from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from metta.app_backend.auth import NoAuthRequired
from metta.app_backend.queries.role_percentile_queries import (
    ROLE_METRICS,
    compute_policy_role_percentiles,
    compute_role_leaderboard,
)
from metta.app_backend.route_logger import timed_http_handler


class RoleMetricDef(BaseModel):
    key: str
    source_names: list[str]
    higher_is_better: bool


class RolePercentileRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    role: str
    percentile: float
    details: dict[str, Any]
    updated_at: datetime


class RoleDefsResponse(BaseModel):
    roles: dict[str, list[RoleMetricDef]]


class RoleLeaderboardRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rank: int
    policy_version_id: UUID
    policy_name: str
    policy_version: int
    percentile: float
    details: dict[str, Any]
    updated_at: datetime


def create_role_stats_router() -> APIRouter:
    router = APIRouter(prefix="/stats/roles", tags=["roles"])

    def _clamp_limit(limit: int) -> int:
        return max(1, min(limit, 500))

    @router.get("/definitions")
    @timed_http_handler
    async def get_role_definitions(_user: NoAuthRequired) -> RoleDefsResponse:
        return RoleDefsResponse(
            roles={
                role: [
                    RoleMetricDef(
                        key=m.key,
                        source_names=list(m.source_names),
                        higher_is_better=m.higher_is_better,
                    )
                    for m in metrics
                ]
                for role, metrics in ROLE_METRICS.items()
            }
        )

    @router.get("/pools/{pool_id}/policy-versions/{policy_version_id}")
    @timed_http_handler
    async def get_policy_percentiles(
        pool_id: UUID,
        policy_version_id: UUID,
        _user: NoAuthRequired,
    ) -> list[RolePercentileRow]:
        rows = await compute_policy_role_percentiles(pool_id, policy_version_id)
        if rows:
            return [RolePercentileRow.model_validate(row) for row in rows]

        raise HTTPException(status_code=404, detail="No role metrics found for this policy in this pool")

    @router.get("/pools/{pool_id}/roles/{role}/leaderboard")
    @timed_http_handler
    async def get_leaderboard(
        pool_id: UUID,
        role: str,
        _user: NoAuthRequired,
        limit: int = 100,
    ) -> list[RoleLeaderboardRow]:
        if role not in ROLE_METRICS:
            raise HTTPException(status_code=404, detail=f"Unknown role '{role}'")

        clamped_limit = _clamp_limit(limit)
        rows = await compute_role_leaderboard(pool_id, role, limit=clamped_limit)
        if rows:
            return [RoleLeaderboardRow.model_validate(row) for row in rows]

        raise HTTPException(status_code=404, detail="No role metrics found for this pool")

    return router
