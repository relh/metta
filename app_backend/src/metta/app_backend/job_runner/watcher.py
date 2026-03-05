"""
K8s Pod Watcher - stores pod events to database.

This watcher only stores events; processing is done by the event_processor.

Uses resourceVersion tracking to resume watches without missing events:
- On stream timeout, resumes from last seen resourceVersion (no re-list)
- On 410 Gone (resourceVersion expired), does a full re-list to re-sync
- BOOKMARK events update the tracked resourceVersion without generating stored events
"""

import logging
import time
from typing import Any, Literal, cast

from kubernetes import (
    client,
    watch,  # type: ignore[attr-defined]
)
from kubernetes.client import ApiClient  # type: ignore[attr-defined]
from kubernetes.client.rest import ApiException  # type: ignore[attr-defined]
from kubernetes.config.kube_config import load_kube_config

from metta.app_backend.health_server import start_health_server, update_heartbeat
from metta.app_backend.job_runner.config import (
    LABEL_APP,
    LABEL_APP_VALUE,
    get_dispatch_config,
)
from metta.app_backend.job_runner.k8s_event_store import store_k8s_event
from metta.app_backend.job_runner.tournament_cluster import get_tournament_clients
from metta.common.otel.tracing import init_otel_tracing
from metta.common.util.log_config import init_logging, suppress_noisy_logs

logger = logging.getLogger(__name__)

WATCH_TIMEOUT_SECONDS = 90

K8sPodWatchEventType = Literal["ADDED", "MODIFIED", "DELETED", "BOOKMARK", "ERROR"]

_api_client = ApiClient()


def _pod_to_dict(pod: client.V1Pod) -> dict[str, Any]:
    return cast(dict[str, Any], _api_client.sanitize_for_serialization(pod))


def _get_k8s_client() -> client.CoreV1Api | None:
    cfg = get_dispatch_config()
    if cfg.LOCAL_DEV:
        if not cfg.LOCAL_DEV_K8S_CONTEXT:
            raise ValueError("LOCAL_DEV=true requires LOCAL_DEV_K8S_CONTEXT to be set")
        load_kube_config(context=cfg.LOCAL_DEV_K8S_CONTEXT)
        return client.CoreV1Api()
    clients = get_tournament_clients()
    if clients is None:
        return None
    core_v1, _ = clients
    return core_v1


def _get_cached_node_labels(
    node_name: str,
    node_label_cache: dict[str, dict[str, str]],
    core_v1: client.CoreV1Api,
) -> dict[str, str]:
    if node_name not in node_label_cache:
        try:
            node = cast(client.V1Node, core_v1.read_node(node_name))
            node_label_cache[node_name] = (node.metadata.labels or {}) if node.metadata else {}
        except Exception:
            node_label_cache[node_name] = {}
    return node_label_cache[node_name]


def _maybe_store_event(
    cluster: str,
    event_type: str,
    pod: dict[str, Any],
    node_label_cache: dict[str, dict[str, str]],
    core_v1: client.CoreV1Api,
) -> None:
    try:
        node_name = (pod.get("spec") or {}).get("nodeName")
        node_labels = _get_cached_node_labels(node_name, node_label_cache, core_v1) if node_name else None
        store_k8s_event(cluster, event_type, pod, node_labels=node_labels)
    except Exception:
        logger.error("Failed to persist k8s watch event", exc_info=True)


def _list_and_sync(
    core_v1: client.CoreV1Api,
    cluster_name: str,
    node_label_cache: dict[str, dict[str, str]],
) -> str | None:
    cfg = get_dispatch_config()
    label_selector = f"{LABEL_APP}={LABEL_APP_VALUE}"

    pod_list = core_v1.list_namespaced_pod(namespace=cfg.JOB_NAMESPACE, label_selector=label_selector)
    if not pod_list.metadata or not pod_list.metadata.resource_version:
        logger.error(f"Invalid pod list on cluster={cluster_name}")
        return None

    for pod in pod_list.items:
        _maybe_store_event(cluster_name, "ADDED", _pod_to_dict(pod), node_label_cache, core_v1)

    rv = pod_list.metadata.resource_version
    logger.info(f"Full re-list on cluster={cluster_name}: {len(pod_list.items)} pods, resourceVersion={rv}")
    return rv


def _watch_stream(
    core_v1: client.CoreV1Api,
    cluster_name: str,
    resource_version: str,
    node_label_cache: dict[str, dict[str, str]],
) -> str:
    cfg = get_dispatch_config()
    label_selector = f"{LABEL_APP}={LABEL_APP_VALUE}"
    last_rv = resource_version

    update_heartbeat()
    w = watch.Watch()
    for raw_event in w.stream(
        core_v1.list_namespaced_pod,
        namespace=cfg.JOB_NAMESPACE,
        label_selector=label_selector,
        resource_version=resource_version,
        allow_watch_bookmarks=True,
        timeout_seconds=WATCH_TIMEOUT_SECONDS,
    ):
        update_heartbeat()
        event = cast(dict[str, Any], raw_event)
        event_type: str = event["type"]
        pod: dict[str, Any] = event["raw_object"]

        if event_type == "ERROR":
            code = pod.get("code", 0)
            if code == 410:
                raise ApiException(status=410, reason="Gone")
            logger.warning(f"Watch ERROR event on cluster={cluster_name}: {pod}")
            continue

        rv = pod.get("metadata", {}).get("resourceVersion")
        if rv:
            last_rv = rv

        if event_type in ("ADDED", "MODIFIED", "DELETED"):
            _maybe_store_event(cluster_name, event_type, pod, node_label_cache, core_v1)

    return last_rv


def _watch_loop(cluster_name: str):
    logger.info(f"Watch loop starting for cluster={cluster_name}")
    resource_version: str | None = None
    node_label_cache: dict[str, dict[str, str]] = {}

    while True:
        try:
            core_v1 = _get_k8s_client()
            if core_v1 is None:
                logger.warning("Eval cluster client unavailable, retrying in 30s")
                time.sleep(30)
                continue

            if resource_version is None:
                resource_version = _list_and_sync(core_v1, cluster_name, node_label_cache)
                if resource_version is None:
                    time.sleep(5)
                    continue

            resource_version = _watch_stream(core_v1, cluster_name, resource_version, node_label_cache)

        except ApiException as e:
            if e.status == 410:
                logger.info(f"resourceVersion expired on cluster={cluster_name}, doing full re-list")
                resource_version = None
            else:
                logger.error(f"Watch API error on cluster={cluster_name}: {e}", exc_info=True)
                resource_version = None
                time.sleep(1)
        except Exception as e:
            logger.error(f"Watch error on cluster={cluster_name}, restarting: {e}", exc_info=True)
            resource_version = None
            time.sleep(1)


def run_watcher():
    cfg = get_dispatch_config()
    start_health_server()
    logger.info(f"Watcher started: namespace={cfg.JOB_NAMESPACE}")

    _watch_loop("eval")


if __name__ == "__main__":
    init_logging()
    suppress_noisy_logs()
    init_otel_tracing(service_name="job-watcher")
    run_watcher()
