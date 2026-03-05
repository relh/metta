"""
K8s Pod Watcher - stores pod events to database.

This watcher only stores events; processing is done by the event_processor.

Uses resourceVersion tracking to resume watches without missing events:
- On stream timeout, resumes from last seen resourceVersion (no re-list)
- On 410 Gone (resourceVersion expired), does a full re-list to re-sync
- BOOKMARK events update the tracked resourceVersion without generating stored events
"""

import json
import logging
import time
from types import SimpleNamespace
from typing import Literal, TypedDict, cast

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


# ADDED: Pod created (usually starts in Pending phase)
# MODIFIED: Pod state changed (phase transitions, container status updates)
# DELETED: Pod removed from cluster
# BOOKMARK: Internal watch checkpoint (no actual change, just resourceVersion update)
# ERROR: Watch stream error
K8sPodWatchEventType = Literal["ADDED", "MODIFIED", "DELETED", "BOOKMARK", "ERROR"]


class K8sPodWatchEvent(TypedDict):
    type: K8sPodWatchEventType
    object: client.V1Pod


def _pod_resource_version(pod: client.V1Pod) -> str | None:
    if pod.metadata and pod.metadata.resource_version:
        return pod.metadata.resource_version
    return None


def _maybe_store_event(
    cluster: str,
    event_type: str,
    pod: client.V1Pod,
    node_label_cache: dict[str, dict[str, str]],
    core_v1: client.CoreV1Api | None = None,
) -> None:
    """Store a pod event, including node labels for terminal pods.

    Node labels are fetched once per unique node and cached for the lifetime of
    the watch session. The fetch happens on the first sighting of a node (usually
    while the pod is Running), so by the time a terminal event arrives the labels
    are already in cache and no extra REST call is needed.
    """
    try:
        node_name = pod.spec.node_name if pod.spec else None
        if core_v1 and node_name and node_name not in node_label_cache:
            try:
                node = cast(client.V1Node, core_v1.read_node(node_name))
                node_label_cache[node_name] = (node.metadata.labels or {}) if node.metadata else {}
            except Exception:
                node_label_cache[node_name] = {}  # cache miss to prevent retries
        node_labels = node_label_cache.get(node_name) if node_name else None
        phase = pod.status.phase if pod.status else None
        store_k8s_event(cluster, event_type, pod, node_labels=node_labels if phase in ("Succeeded", "Failed") else None)
    except Exception:
        logger.error("Failed to persist k8s watch event", exc_info=True)


def _list_and_sync(
    core_v1: client.CoreV1Api,
    cluster_name: str,
    node_label_cache: dict[str, dict[str, str]],
) -> str | None:
    """Full list of pods, store as ADDED events, return resourceVersion."""
    cfg = get_dispatch_config()
    label_selector = f"{LABEL_APP}={LABEL_APP_VALUE}"

    pod_list = core_v1.list_namespaced_pod(namespace=cfg.JOB_NAMESPACE, label_selector=label_selector)
    if not pod_list.metadata or not pod_list.metadata.resource_version:
        logger.error(f"Invalid pod list on cluster={cluster_name}")
        return None

    for pod in pod_list.items:
        _maybe_store_event(cluster_name, "ADDED", pod, node_label_cache, core_v1)

    rv = pod_list.metadata.resource_version
    logger.info(f"Full re-list on cluster={cluster_name}: {len(pod_list.items)} pods, resourceVersion={rv}")
    return rv


def _watch_stream(
    core_v1: client.CoreV1Api,
    cluster_name: str,
    resource_version: str,
    node_label_cache: dict[str, dict[str, str]],
) -> str:
    """Run a single watch stream, return the last seen resourceVersion.

    Raises ApiException with status 410 if the resourceVersion is too old.
    """
    cfg = get_dispatch_config()
    label_selector = f"{LABEL_APP}={LABEL_APP_VALUE}"
    last_rv = resource_version

    update_heartbeat()
    w = watch.Watch()
    event: K8sPodWatchEvent
    for event in w.stream(  # type: ignore[assignment]
        core_v1.list_namespaced_pod,
        namespace=cfg.JOB_NAMESPACE,
        label_selector=label_selector,
        resource_version=resource_version,
        allow_watch_bookmarks=True,
        timeout_seconds=WATCH_TIMEOUT_SECONDS,
    ):
        update_heartbeat()
        event_type, pod = event["type"], event["object"]

        if event_type == "ERROR":
            raw = event.get("raw_object", {})  # type: ignore[union-attr]
            code = raw.get("code", 0) if isinstance(raw, dict) else 0
            if code == 410:
                raise ApiException(status=410, reason="Gone")
            logger.warning(f"Watch ERROR event on cluster={cluster_name}: {raw}")
            continue

        if isinstance(pod, dict):
            rv = pod.get("metadata", {}).get("resourceVersion")
        else:
            rv = _pod_resource_version(pod)
        if rv:
            last_rv = rv

        if event_type not in ("ADDED", "MODIFIED", "DELETED"):
            continue

        if isinstance(pod, dict):
            pod = cast(client.V1Pod, ApiClient().deserialize(SimpleNamespace(data=json.dumps(pod)), "V1Pod"))

        _maybe_store_event(cluster_name, event_type, pod, node_label_cache, core_v1)

    return last_rv


def _watch_loop(cluster_name: str):
    """Main watch loop with resourceVersion tracking across reconnects."""
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
    """Run the watcher service."""
    cfg = get_dispatch_config()
    start_health_server()
    logger.info(f"Watcher started: namespace={cfg.JOB_NAMESPACE}")

    _watch_loop("eval")


if __name__ == "__main__":
    init_logging()
    suppress_noisy_logs()
    init_otel_tracing(service_name="job-watcher")
    run_watcher()
