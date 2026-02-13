from __future__ import annotations

import logging
from datetime import UTC, datetime

from kubernetes import client
from kubernetes.client.api_client import ApiClient
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


def store_k8s_event(cluster: str, event_type: str, pod: client.V1Pod) -> None:
    engine = _get_engine()
    if engine is None:
        return
    raw = ApiClient().sanitize_for_serialization(pod)
    event_time = pod.metadata.creation_timestamp if pod.metadata else None
    event = K8sEvent(
        cluster=cluster,
        event_time=event_time or datetime.now(UTC),
        event={"type": event_type, "object": raw},
    )
    with Session(engine) as session:
        session.add(event)
        session.commit()
