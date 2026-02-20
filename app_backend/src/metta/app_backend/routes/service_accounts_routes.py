from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from metta.app_backend.auth import SoftmaxUser
from metta.app_backend.database import db_session
from metta.app_backend.models.service_accounts import ServiceAccount
from metta.app_backend.route_logger import timed_http_handler
from metta.app_backend.service_accounts import generate_token_pair, generate_token_preview, parse_token_prefix
from metta.app_backend.user_data import Ownable


class ServiceAccountResponseBase(Ownable):
    id: UUID
    name: str
    token_preview: str
    created_at: datetime

    @classmethod
    def from_service_account(
        cls,
        service_account: ServiceAccount,
    ) -> "ServiceAccountResponseBase":
        return cls(**service_account.model_dump())


class ServiceAccountCreate(BaseModel):
    name: str


class ServiceAccountCreateResponse(ServiceAccountResponseBase):
    token: str


class ServiceAccountDeleteResponse(BaseModel):
    id: UUID


def create_service_accounts_router() -> APIRouter:
    router = APIRouter(prefix="/service-accounts", tags=["service_accounts"])

    @router.post("")
    async def create_service_account(
        service_account: ServiceAccountCreate, user: SoftmaxUser
    ) -> ServiceAccountCreateResponse:
        if user.is_service_account_user:
            raise HTTPException(
                status_code=401, detail="Service accounts are not authorized to create other service accounts"
            )

        (token, hashed_token) = generate_token_pair()
        preview = generate_token_preview(token)
        (prefix, _) = parse_token_prefix(token)

        async with db_session() as session:
            db_service_account = ServiceAccount(
                **service_account.model_dump(),
                user_id=user.id,
                token_hash=hashed_token,
                token_prefix=prefix,
                token_preview=preview,
            )
            session.add(db_service_account)
            try:
                await session.commit()
            except IntegrityError as e:
                raise HTTPException(
                    status_code=409, detail=f"Service account with name {service_account.name} already exists"
                ) from e

            await session.refresh(db_service_account)
            return ServiceAccountCreateResponse(**db_service_account.model_dump(), token=token)

    @router.get("")
    @timed_http_handler
    async def list_service_accounts(user: SoftmaxUser) -> list[ServiceAccountResponseBase]:
        async with db_session() as session:
            query = select(ServiceAccount).where(ServiceAccount.user_id == user.id)
            service_accounts = (await session.execute(query)).scalars().unique().all()
            return [ServiceAccountResponseBase.from_service_account(sa) for sa in service_accounts]

    @router.delete("/{service_account_id}")
    @timed_http_handler
    async def delete_service_account(
        service_account_id: UUID,
        user: SoftmaxUser,
    ) -> ServiceAccountDeleteResponse:
        async with db_session() as session:
            result = await session.execute(
                select(ServiceAccount)
                .where(ServiceAccount.id == service_account_id)
                .where(ServiceAccount.user_id == user.id)
            )
            service_account = result.scalar_one_or_none()
            if not service_account:
                raise HTTPException(status_code=404, detail=f"Service Account {service_account_id} not found")

            await session.delete(service_account)
            await session.commit()
            return ServiceAccountDeleteResponse(id=service_account_id)

    return router
