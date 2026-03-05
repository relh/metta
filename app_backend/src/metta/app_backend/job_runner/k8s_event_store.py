from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlmodel import Session, create_engine

from metta.app_backend.config import settings
from metta.app_backend.models.k8s_events import K8sEvent

logger = logging.getLogger(__name__)

_engine = None
_disabled = False


def _get_engine():
    global _engine, _disabled
    if _disabled:
        return None
    if _engine is None:
        if not settings.STATS_DB_URI:
            logger.warning("STATS_DB_URI not set, k8s event storage disabled")
            _disabled = True
            return None
        uri = settings.STATS_DB_URI
        if uri.startswith("postgres://"):
            uri = uri.replace("postgres://", "postgresql+psycopg://", 1)
        elif uri.startswith("postgresql://"):
            uri = uri.replace("postgresql://", "postgresql+psycopg://", 1)
        _engine = create_engine(uri, pool_pre_ping=True)
    return _engine


def store_k8s_event(
    cluster: str, event_type: str, pod: dict[str, Any], node_labels: dict[str, str] | None = None
) -> None:
    engine = _get_engine()
    if engine is None:
        return
    creation_ts: str | None = (pod.get("metadata") or {}).get("creationTimestamp")
    if creation_ts:
        event_time = datetime.fromisoformat(creation_ts.replace("Z", "+00:00"))
    else:
        event_time = None
    event_dict: dict = {"type": event_type, "object": pod}
    if node_labels:
        event_dict["node_labels"] = node_labels
    event = K8sEvent(
        cluster=cluster,
        event_time=event_time or datetime.now(UTC),
        event=event_dict,
    )
    with Session(engine) as session:
        session.add(event)
        session.commit()
