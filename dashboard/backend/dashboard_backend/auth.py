"""Dashboard auth, intentionally parallel to app_backend auth with local-dev bypass."""

from typing import Annotated, Optional

import httpx
from fastapi import Depends, HTTPException, Request, status
from pydantic import BaseModel

from dashboard.backend.dashboard_backend.config import settings
from metta.app_backend.models.service_accounts import TokenPrefixType
from metta.app_backend.queries.service_account_queries import get_service_account_user


class User(BaseModel):
    id: str
    email: str
    is_softmax_team_member: bool = False
    is_service_account_user: bool = False


def _is_local_request(request: Request) -> bool:
    return (request.url.hostname or "").lower() in {"localhost", "127.0.0.1", "::1"}


def _dev_user(request: Request) -> User:
    user_id = request.headers.get("X-User-Id", "dashboard-local-user")
    user_email = request.headers.get("X-User-Email", "dashboard-local@softmax.com")
    return User(id=user_id, email=user_email, is_softmax_team_member=True)


def get_user_from_header(request: Request) -> Optional[User]:
    if not settings.DASHBOARD_AUTH_SECRET:
        return None

    auth_secret = request.headers.get("X-Auth-Secret")
    if auth_secret != settings.DASHBOARD_AUTH_SECRET:
        return None

    user_id = request.headers.get("X-User-Id")
    user_email = request.headers.get("X-User-Email", "")
    is_softmax_team_member = request.headers.get("X-User-Is-Softmax-Team-Member", "false").lower() == "true"

    return User(id=user_id, email=user_email, is_softmax_team_member=is_softmax_team_member) if user_id else None


async def validate_token_via_login_service(token: str) -> Optional[User]:
    if settings.DASHBOARD_DEBUG_USER_EMAIL and token == settings.DASHBOARD_DEBUG_USER_EMAIL:
        return User(
            id=settings.DASHBOARD_DEBUG_USER_EMAIL,
            email=settings.DASHBOARD_DEBUG_USER_EMAIL,
            is_softmax_team_member=True,
        )

    if any(token.startswith(prefix.value) for prefix in TokenPrefixType):
        try:
            service_account_user = await get_service_account_user(token)
            if not service_account_user:
                return None
            return User(
                id=service_account_user.id,
                email=service_account_user.email,
                is_softmax_team_member=service_account_user.is_softmax_team_member,
                is_service_account_user=True,
            )
        except Exception:
            return None

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{settings.DASHBOARD_LOGIN_SERVICE_URL}/api/validate",
                headers={"Authorization": f"Bearer {token}"},
                timeout=5.0,
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("valid"):
                    user_info = data.get("user", {})
                    return User(
                        id=user_info.get("id"),
                        email=user_info.get("email"),
                        is_softmax_team_member=user_info.get("isSoftmaxTeamMember", False),
                    )
                return None

            if response.status_code >= 500:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Login service unavailable",
                )

            return None
    except HTTPException:
        raise
    except httpx.TransportError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Login service unreachable: {type(e).__name__}",
        ) from e


async def get_user_from_token(request: Request) -> Optional[User]:
    token = request.headers.get("X-Auth-Token")
    if not token:
        authorization_header = request.headers.get("Authorization", "")
        scheme, _separator, value = authorization_header.partition(" ")
        if scheme.lower() == "bearer":
            token = value
    return await validate_token_via_login_service(token) if token else None


async def get_user(request: Request) -> Optional[User]:
    if user := get_user_from_header(request):
        return user

    if user := await get_user_from_token(request):
        return user

    if settings.DASHBOARD_DEV_AUTH_BYPASS and _is_local_request(request):
        return _dev_user(request)

    return None


async def get_user_or_raise(request: Request) -> User:
    user = await get_user(request)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Failed to authenticate")
    return user


async def get_softmax_user_or_raise(request: Request) -> User:
    user = await get_user_or_raise(request)
    if not user.is_softmax_team_member:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is not a softmax team member")
    return user


async def _no_auth() -> None:
    pass


ExternalUser = Annotated[User, Depends(get_user_or_raise)]
SoftmaxUser = Annotated[User, Depends(get_softmax_user_or_raise)]
MaybeAuthenticatedUser = Annotated[Optional[User], Depends(get_user)]
NoAuthRequired = Annotated[None, Depends(_no_auth)]
