from __future__ import annotations

from datetime import UTC, datetime

from kubernetes import client
from kubernetes.client.api_client import ApiClient
from sqlmodel import Session, create_engine

from metta.app_backend.config import settings
from metta.app_backend.models.k8s_events import K8sEvent

_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(settings.STATS_DB_URI, pool_pre_ping=True)
    return _engine


def store_k8s_event(cluster: str, event_type: str, pod: client.V1Pod) -> None:
    raw = ApiClient().sanitize_for_serialization(pod)
    event_time = pod.metadata.creation_timestamp if pod.metadata else None
    event = K8sEvent(
        cluster=cluster,
        event_time=event_time or datetime.now(UTC),
        event={"type": event_type, "object": raw},
    )
    with Session(_get_engine()) as session:
        session.add(event)
        session.commit()
