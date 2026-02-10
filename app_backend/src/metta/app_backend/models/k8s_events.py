from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import BIGINT, TIMESTAMP, Column, Index, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


class K8sEvent(SQLModel, table=True):
    __tablename__ = "k8s_events"  # type: ignore[assignment]
    __table_args__ = (
        Index("idx_k8s_events_cluster_event_time", "cluster", text("event_time DESC")),
        Index("idx_k8s_events_unprocessed", "event_time", postgresql_where=text("processed_at IS NULL")),
    )

    id: int | None = Field(default=None, primary_key=True, sa_type=BIGINT)
    cluster: str
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column_kwargs={"server_default": text("CURRENT_TIMESTAMP")},
        sa_type=TIMESTAMP(timezone=True),
    )
    event_time: datetime = Field(sa_type=TIMESTAMP(timezone=True))
    event: dict[str, Any] = Field(sa_column=Column(JSONB, nullable=False))
    processed_at: datetime | None = Field(default=None, sa_type=TIMESTAMP(timezone=True))
