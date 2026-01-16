from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from metta.app_backend.auth import CheckSoftmaxUser, User
from metta.app_backend.config import settings
from metta.app_backend.smart_plugs import SmartPlugStatus, fetch_statuses, set_power

logger = logging.getLogger(__name__)


class SmartPlugStatusResponse(BaseModel):
    refreshed_at: datetime
    items: list[SmartPlugStatus]


class SmartPlugSetRequest(BaseModel):
    key: str
    on: bool
    toggle_after: Optional[int] = Field(default=None, ge=1)


class SmartPlugSetResponse(BaseModel):
    ok: bool


def create_smart_plug_router() -> APIRouter:
    router = APIRouter(prefix="/infra/smart-plugs", tags=["infra"])

    @router.get("/status", response_model=SmartPlugStatusResponse)
    async def get_status(user: CheckSoftmaxUser) -> SmartPlugStatusResponse:
        if not settings.SMART_PLUGS_ENABLED:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Smart plugs are disabled")

        try:
            items = await fetch_statuses()
        except Exception as exc:
            logger.warning("Failed to fetch smart plug status: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to fetch smart plug status",
            ) from exc

        return SmartPlugStatusResponse(refreshed_at=datetime.now(timezone.utc), items=items)

    @router.post("/power", response_model=SmartPlugSetResponse)
    async def set_power_state(request: SmartPlugSetRequest, user: CheckSoftmaxUser) -> SmartPlugSetResponse:
        _ensure_writable(user)
        try:
            await set_power(request.key, request.on, request.toggle_after)
        except KeyError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except Exception as exc:
            logger.warning("Failed to set smart plug power: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to set smart plug power",
            ) from exc
        return SmartPlugSetResponse(ok=True)

    return router


def _ensure_writable(user: User) -> None:
    if not settings.SMART_PLUGS_ENABLED:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Smart plugs are disabled")
    if not settings.SMART_PLUGS_ALLOW_WRITE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Smart plug control is read-only")
    logger.info(
        "Smart plug action requested",
        extra={"user_email": user.email},
    )
