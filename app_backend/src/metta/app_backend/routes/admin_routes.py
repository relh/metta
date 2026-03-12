from fastapi import APIRouter
from pydantic import BaseModel

from metta.app_backend.auth import SoftmaxAdmin


class AdminUsersScaffoldResponse(BaseModel):
    message: str


def create_admin_router() -> APIRouter:
    router = APIRouter(prefix="/admin", tags=["admin"])

    @router.get("/users")
    async def admin_users_scaffold(_user: SoftmaxAdmin) -> AdminUsersScaffoldResponse:
        return AdminUsersScaffoldResponse(
            message="Admin user reporting scaffold is ready for the follow-up PR.",
        )

    return router
