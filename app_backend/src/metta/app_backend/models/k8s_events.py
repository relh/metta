from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Column, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class K8sEvent(SQLModel, table=True):
    __tablename__ = "k8s_events"  # type: ignore[assignment]

    id: int | None = Field(default=None, primary_key=True)
    cluster: str
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column_kwargs={"server_default": text("now()")},
    )
    event_time: datetime
    event: dict[str, Any] = Field(sa_column=Column(JSONB))
    processed_at: datetime | None = Field(default=None)
