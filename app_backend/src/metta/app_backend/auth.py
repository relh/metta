"""
Observatory backend treats users as opaque user ids. The ids are managed by softmax.com login service.

There are several ways to authenticate requests:

1) `X-User-Id` and `X-Auth-Secret` header pair, where `X-Auth-Secret` is the secret static key that is shared between
the backend and softmax.com login service. This is used for requests from softmax.com.

2) `Authorization` header with Bearer token

3) `X-Auth-Token` header (legacy header)
"""

from typing import Annotated, Optional

import httpx
from fastapi import Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from metta.app_backend.config import settings
from metta.app_backend.models.service_accounts import TokenPrefixType
from metta.app_backend.queries.service_account_queries import get_service_account_user
from metta.common.otel.tracing import trace


class User(BaseModel):
    id: str
    email: str
    is_softmax_team_member: bool = Field(default=False, alias="is_softmax_team_member")
    is_service_account_user: bool = Field(default=False)
    discord_id: Optional[str] = Field(default=None)


def get_user_from_header(request: Request) -> Optional[User]:
    if not settings.OBSERVATORY_AUTH_SECRET:
        return None

    # check static secret key that allows softmax.com to bypass token validation
    auth_secret = request.headers.get("X-Auth-Secret")
    if auth_secret != settings.OBSERVATORY_AUTH_SECRET:
        return None

    user_id = request.headers.get("X-User-Id")
    user_email = request.headers.get(
        "X-User-Email",
        "",  # TODO - allowed empty value for now - current softmax.com doesn't set this header
    )
    is_softmax_team_member = request.headers.get("X-User-Is-Softmax-Team-Member", "false").lower() == "true"

    if user_id:
        return User(id=user_id, email=user_email, is_softmax_team_member=is_softmax_team_member)
    return None


async def get_user_from_token(request: Request) -> Optional[User]:
    token = request.headers.get("X-Auth-Token")  # Legacy header
    if not token:
        authorization_header = request.headers.get("Authorization", "")
        if authorization_header.lower().startswith("bearer "):
            token = authorization_header.split(" ", 1)[1]

    if token:
        return await validate_token_via_login_service(token)

    return None


async def get_user(request: Request) -> Optional[User]:
    user = get_user_from_header(request)
    if not user:
        user = await get_user_from_token(request)

    if user and user.is_softmax_team_member and request.headers.get("X-Act-As-External", "").lower() == "true":
        user = user.model_copy(update={"is_softmax_team_member": False})

    return user


async def get_user_or_raise(request: Request) -> User:
    user = await get_user(request)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Failed to authenticate",
        )
    return user


async def get_softmax_user_or_raise(request: Request) -> User:
    user = await get_user_or_raise(request)
    if not user.is_softmax_team_member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not a softmax team member",
        )
    return user


async def _no_auth() -> None:
    pass


# Dependency types for use in route decorators.
#
# These control runtime auth only. Public API visibility is separate — see docs_routes.py.
# To hide a specific endpoint from the public OpenAPI spec, use @exclude_from_public_docs.
ExternalUser = Annotated[User, Depends(get_user_or_raise)]  # 401 if not logged in
SoftmaxUser = Annotated[User, Depends(get_softmax_user_or_raise)]  # 403 if not softmax team
MaybeAuthenticatedUser = Annotated[Optional[User], Depends(get_user)]  # always succeeds, user may be None
NoAuthRequired = Annotated[None, Depends(_no_auth)]  # always succeeds, no-op


@trace("auth.validate_token")
async def validate_token_via_login_service(token: str) -> Optional[User]:
    """Validate a machine token via the login service and return the user if valid.

    Returns None if the token is definitively invalid.
    Raises HTTPException(503) if the login service is unreachable or erroring,
    so callers don't confuse infrastructure failures with bad tokens.
    """
    if settings.DEBUG_USER_EMAIL and token == settings.DEBUG_USER_EMAIL:
        return User(id=settings.DEBUG_USER_EMAIL, email=settings.DEBUG_USER_EMAIL, is_softmax_team_member=True)

    is_service_account = any([token.startswith(prefix.value) for prefix in TokenPrefixType])

    if is_service_account:
        try:
            service_account_user = await get_service_account_user(token)

            # Service account exist, but the user who created it is unknown
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
                f"{settings.LOGIN_SERVICE_URL}/api/validate",
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
                        discord_id=user_info.get("discordId", None),
                    )
                return None

            if response.status_code >= 500:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Login service unavailable",
                )

            return None  # 4xx from login service → token is bad
    except HTTPException:
        raise
    except httpx.TransportError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Login service unreachable: {type(e).__name__}",
        ) from e
