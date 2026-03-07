from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Optional

import httpx
from cachetools import TTLCache
from pydantic import BaseModel

from metta.app_backend.auth import User
from metta.app_backend.config import settings
from metta.common.otel.tracing import trace

logger = logging.getLogger(__name__)

# Per-user cache of raw API response dicts. Sensitive-field filtering
# happens at read time so a single cache entry serves all callers.
_user_info_cache: TTLCache[str, dict] = TTLCache(maxsize=4096, ttl=300)


class UserRow(BaseModel):
    id: str
    name: Optional[str] = None
    email: Optional[str] = None
    is_softmax_team_member: Optional[bool] = None
    discord_id: Optional[str] = None


class Ownable(BaseModel):
    user_id: str
    user: UserRow | None = None


def _user_row(info: dict, user_id: str, *, include_sensitive: bool) -> UserRow:
    raw_name = info.get("name")
    raw_email = info.get("email")
    raw_discord_id = info.get("discordId")
    return UserRow(
        id=str(info.get("id", user_id)),
        name=str(raw_name) if raw_name is not None else None,
        email=str(raw_email) if include_sensitive and raw_email is not None else None,
        is_softmax_team_member=bool(info.get("isSoftmaxTeamMember", False)) if include_sensitive else None,
        discord_id=str(raw_discord_id) if include_sensitive and raw_discord_id is not None else None,
    )


@trace("user_data.load_user_ids")
async def load_user_ids(user_ids: list[str], *, include_sensitive: bool = True) -> dict[str, UserRow]:
    """Resolve user IDs to UserRow objects via the softmax.com API.

    Results are cached for 5 minutes per user. Degrades gracefully on failure.
    """
    if not user_ids or not settings.OBSERVATORY_AUTH_SECRET:
        return {}

    # Snapshot cached entries so TTL expiry between the write and read
    # phases can't silently drop users.
    resolved: dict[str, dict] = {}
    uncached_ids: list[str] = []
    for uid in user_ids:
        cached = _user_info_cache.get(uid)
        if cached is None:
            uncached_ids.append(uid)
        else:
            resolved[uid] = cached

    if uncached_ids:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{settings.LOGIN_SERVICE_URL}/api/users/resolve",
                    json={"userIds": uncached_ids},
                    headers={"X-Auth-Secret": settings.OBSERVATORY_AUTH_SECRET},
                    timeout=5.0,
                )

            if resp.status_code != 200:
                logger.warning("User resolve endpoint returned %d", resp.status_code)
            else:
                for uid, info in resp.json().get("users", {}).items():
                    _user_info_cache[uid] = info
                    resolved[uid] = info
        except Exception:
            logger.warning("Failed to resolve user data", exc_info=(not settings.LOCAL_DEV))

    return {uid: _user_row(info, uid, include_sensitive=include_sensitive) for uid, info in resolved.items()}


async def load_user_id(user_id: str, *, include_sensitive: bool = True) -> Optional[UserRow]:
    """Resolve a single user ID. Returns None if resolution fails."""
    result = await load_user_ids([user_id], include_sensitive=include_sensitive)
    return result.get(user_id)


async def fill_user_data(entities: Sequence[Ownable], *, current_user: Optional[User] = None) -> None:
    """Batch-resolve user info for entities with user_id.

    Calls the softmax.com /api/users/resolve endpoint to look up user data.
    Results are cached for 5 minutes per user to avoid repeated cross-service calls.
    Emails are only included when current_user is a softmax team member.
    Degrades gracefully on failure — leaves entity.user as None.
    """
    user_ids = list({e.user_id for e in entities})
    include_sensitive = current_user is not None and current_user.is_softmax_team_member

    resolved = await load_user_ids(user_ids, include_sensitive=include_sensitive)

    for entity in entities:
        user = resolved.get(entity.user_id)
        if user:
            entity.user = user
