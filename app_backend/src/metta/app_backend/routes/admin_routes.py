from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import col, select

from metta.app_backend.auth import SoftmaxAdmin
from metta.app_backend.database import ReadDbSession
from metta.app_backend.models.policies import Policy, PolicyVersion
from metta.app_backend.user_data import UserRow, load_all_users


class AdminUserReportRow(UserRow):
    first_policy_upload_at: datetime | None = None
    last_policy_upload_at: datetime | None = None


class AdminUsersReportResponse(BaseModel):
    users: list[AdminUserReportRow]


def create_admin_router() -> APIRouter:
    router = APIRouter(prefix="/admin", tags=["admin"])

    @router.get("/users")
    async def admin_users_report(_user: SoftmaxAdmin, session: ReadDbSession) -> AdminUsersReportResponse:
        try:
            users = await load_all_users(include_sensitive=True)
        except RuntimeError as e:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e)) from e

        policy_uploads = {
            user_id: (first_policy_upload_at, last_policy_upload_at)
            for user_id, first_policy_upload_at, last_policy_upload_at in (
                await session.execute(
                    select(
                        Policy.user_id,
                        func.min(PolicyVersion.created_at),
                        func.max(PolicyVersion.created_at),
                    )
                    .select_from(PolicyVersion)
                    .join(Policy, col(PolicyVersion.policy_id) == col(Policy.id))
                    .group_by(Policy.user_id)
                )
            ).all()
        }
        rows = [
            AdminUserReportRow(
                **user.model_dump(),
                first_policy_upload_at=policy_uploads.get(user.id, (None, None))[0],
                last_policy_upload_at=policy_uploads.get(user.id, (None, None))[1],
            )
            for user in users
        ]
        rows.sort(key=lambda row: ((row.name or row.email or row.id).lower(), row.id))
        return AdminUsersReportResponse(users=rows)

    return router
