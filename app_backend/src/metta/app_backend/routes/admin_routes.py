from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import col, select

from metta.app_backend.auth import SoftmaxAdmin
from metta.app_backend.database import ReadDbSession
from metta.app_backend.models.policies import Policy, PolicyVersion
from metta.app_backend.models.tournament import Pool, PoolPlayer, Season
from metta.app_backend.models.user_settings import UserSettings
from metta.app_backend.user_data import UserRow, load_all_users


class AdminUserReportRow(UserRow):
    is_softmax_admin: bool = False
    first_policy_upload_at: datetime | None = None
    last_policy_upload_at: datetime | None = None
    first_tournament_submission_at: datetime | None = None
    last_tournament_submission_at: datetime | None = None


class AdminUserPolicySeason(BaseModel):
    season_name: str
    season_version: int
    submitted_at: datetime


class AdminUserPolicyRow(BaseModel):
    id: UUID
    name: str
    created_at: datetime
    version_count: int
    seasons: list[AdminUserPolicySeason]


class AdminUsersReportResponse(BaseModel):
    users: list[AdminUserReportRow]


class AdminUserDetailResponse(BaseModel):
    user: AdminUserReportRow
    submitted_policies: list[AdminUserPolicyRow]


async def _load_users_or_503() -> list[UserRow]:
    try:
        return await load_all_users(include_sensitive=True)
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e)) from e


async def _load_softmax_admin_ids(session: ReadDbSession, user_ids: list[str] | None = None) -> set[str]:
    query = select(UserSettings.user_id).where(col(UserSettings.admin).is_(True))
    if user_ids:
        query = query.where(col(UserSettings.user_id).in_(user_ids))
    return set((await session.execute(query)).scalars().all())


async def _load_policy_upload_stats(
    session: ReadDbSession, user_ids: list[str] | None = None
) -> dict[str, tuple[datetime | None, datetime | None]]:
    policy_user_id = col(Policy.user_id)
    query = (
        select(
            policy_user_id,
            func.min(col(PolicyVersion.created_at)),
            func.max(col(PolicyVersion.created_at)),
        )
        .select_from(PolicyVersion)
        .join(Policy, col(PolicyVersion.policy_id) == col(Policy.id))
        .group_by(policy_user_id)
    )
    if user_ids:
        query = query.where(policy_user_id.in_(user_ids))
    return {
        user_id: (first_policy_upload_at, last_policy_upload_at)
        for user_id, first_policy_upload_at, last_policy_upload_at in (await session.execute(query)).all()
    }


async def _load_tournament_submission_stats(
    session: ReadDbSession, user_ids: list[str] | None = None
) -> dict[str, tuple[datetime | None, datetime | None]]:
    policy_user_id = col(Policy.user_id)
    policy_version_id = col(PolicyVersion.id)
    season_id = col(Season.id)
    submission_events = (
        select(
            policy_user_id.label("user_id"),
            policy_version_id.label("policy_version_id"),
            season_id.label("season_id"),
            func.min(col(PoolPlayer.created_at)).label("submitted_at"),
        )
        .select_from(PoolPlayer)
        .join(Pool, col(PoolPlayer.pool_id) == col(Pool.id))
        .join(Season, col(Pool.season_id) == season_id)
        .join(PolicyVersion, col(PoolPlayer.policy_version_id) == policy_version_id)
        .join(Policy, col(PolicyVersion.policy_id) == col(Policy.id))
        .group_by(policy_user_id, policy_version_id, season_id)
    )
    if user_ids:
        submission_events = submission_events.where(policy_user_id.in_(user_ids))
    submission_events_subquery = submission_events.subquery()

    query = select(
        submission_events_subquery.c.user_id,
        func.min(submission_events_subquery.c.submitted_at),
        func.max(submission_events_subquery.c.submitted_at),
    ).group_by(submission_events_subquery.c.user_id)

    return {
        user_id: (first_submission_at, last_submission_at)
        for user_id, first_submission_at, last_submission_at in (await session.execute(query)).all()
    }


def _build_admin_user_report_row(
    user: UserRow,
    *,
    softmax_admin_ids: set[str],
    policy_upload_stats: dict[str, tuple[datetime | None, datetime | None]],
    tournament_submission_stats: dict[str, tuple[datetime | None, datetime | None]],
) -> AdminUserReportRow:
    first_policy_upload_at, last_policy_upload_at = policy_upload_stats.get(user.id, (None, None))
    first_tournament_submission_at, last_tournament_submission_at = tournament_submission_stats.get(
        user.id, (None, None)
    )
    return AdminUserReportRow(
        **user.model_dump(),
        is_softmax_admin=user.id in softmax_admin_ids,
        first_policy_upload_at=first_policy_upload_at,
        last_policy_upload_at=last_policy_upload_at,
        first_tournament_submission_at=first_tournament_submission_at,
        last_tournament_submission_at=last_tournament_submission_at,
    )


def create_admin_router() -> APIRouter:
    router = APIRouter(prefix="/admin", tags=["admin"])

    @router.get("/users")
    async def admin_users_report(_user: SoftmaxAdmin, session: ReadDbSession) -> AdminUsersReportResponse:
        users = await _load_users_or_503()
        user_ids = [user.id for user in users]
        softmax_admin_ids = await _load_softmax_admin_ids(session, user_ids)
        policy_upload_stats = await _load_policy_upload_stats(session, user_ids)
        tournament_submission_stats = await _load_tournament_submission_stats(session, user_ids)
        rows = [
            _build_admin_user_report_row(
                user,
                softmax_admin_ids=softmax_admin_ids,
                policy_upload_stats=policy_upload_stats,
                tournament_submission_stats=tournament_submission_stats,
            )
            for user in users
        ]
        rows.sort(key=lambda row: ((row.name or row.email or row.id).lower(), row.id))
        return AdminUsersReportResponse(users=rows)

    @router.get("/users/{user_id}")
    async def admin_user_detail(user_id: str, _user: SoftmaxAdmin, session: ReadDbSession) -> AdminUserDetailResponse:
        users = await _load_users_or_503()
        user = next((candidate for candidate in users if candidate.id == user_id), None)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        softmax_admin_ids = await _load_softmax_admin_ids(session, [user_id])
        policy_upload_stats = await _load_policy_upload_stats(session, [user_id])
        tournament_submission_stats = await _load_tournament_submission_stats(session, [user_id])
        submitted_policy_ids = (
            select(col(Policy.id))
            .select_from(PoolPlayer)
            .join(PolicyVersion, col(PoolPlayer.policy_version_id) == col(PolicyVersion.id))
            .join(Policy, col(PolicyVersion.policy_id) == col(Policy.id))
            .where(col(Policy.user_id) == user_id)
            .distinct()
        )

        submitted_policy_rows = (
            await session.execute(
                select(
                    col(Policy.id),
                    col(Policy.name),
                    col(Policy.created_at),
                    func.count(col(PolicyVersion.id)).label("version_count"),
                )
                .select_from(Policy)
                .join(PolicyVersion, col(PolicyVersion.policy_id) == col(Policy.id))
                .where(col(Policy.user_id) == user_id)
                .where(col(Policy.id).in_(submitted_policy_ids))
                .group_by(col(Policy.id), col(Policy.name), col(Policy.created_at))
                .order_by(col(Policy.created_at).desc(), col(Policy.name).asc())
            )
        ).all()

        season_rows = (
            await session.execute(
                select(
                    col(Policy.id).label("policy_id"),
                    col(Season.name).label("season_name"),
                    col(Season.version).label("season_version"),
                    func.min(col(PoolPlayer.created_at)).label("submitted_at"),
                )
                .select_from(PoolPlayer)
                .join(Pool, col(PoolPlayer.pool_id) == col(Pool.id))
                .join(Season, col(Pool.season_id) == col(Season.id))
                .join(PolicyVersion, col(PoolPlayer.policy_version_id) == col(PolicyVersion.id))
                .join(Policy, col(PolicyVersion.policy_id) == col(Policy.id))
                .where(col(Policy.user_id) == user_id)
                .group_by(col(Policy.id), col(Season.id), col(Season.name), col(Season.version))
                .order_by(
                    func.min(col(PoolPlayer.created_at)).desc(),
                    col(Season.name).asc(),
                )
            )
        ).all()

        seasons_by_policy: dict[UUID, list[AdminUserPolicySeason]] = {}
        for policy_id, season_name, season_version, submitted_at in season_rows:
            seasons_by_policy.setdefault(policy_id, []).append(
                AdminUserPolicySeason(
                    season_name=season_name,
                    season_version=season_version,
                    submitted_at=submitted_at,
                )
            )

        submitted_policies = [
            AdminUserPolicyRow(
                id=policy_id,
                name=policy_name,
                created_at=created_at,
                version_count=version_count,
                seasons=seasons_by_policy.get(policy_id, []),
            )
            for policy_id, policy_name, created_at, version_count in submitted_policy_rows
        ]

        return AdminUserDetailResponse(
            user=_build_admin_user_report_row(
                user,
                softmax_admin_ids=softmax_admin_ids,
                policy_upload_stats=policy_upload_stats,
                tournament_submission_stats=tournament_submission_stats,
            ),
            submitted_policies=submitted_policies,
        )

    return router
