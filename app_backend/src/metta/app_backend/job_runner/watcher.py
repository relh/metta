"""
K8s Pod Watcher - stores pod events to database.

This watcher only stores events; processing is done by the event_processor.
"""

import logging
import time
from typing import Literal, TypedDict, cast

from kubernetes import (
    client,
    watch,  # type: ignore[attr-defined]
)
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

WATCH_TIMEOUT_SECONDS = 30


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


def _watch_pods_with_client(core_v1: client.CoreV1Api, cluster_name: str):
    """Watch pods and store events to the database."""
    cfg = get_dispatch_config()
    label_selector = f"{LABEL_APP}={LABEL_APP_VALUE}"

    pod_list = core_v1.list_namespaced_pod(namespace=cfg.JOB_NAMESPACE, label_selector=label_selector)
    if not pod_list.metadata or not pod_list.metadata.resource_version:
        logger.error(f"Invalid pod list on cluster={cluster_name}: {pod_list}")
        return

    node_label_cache: dict[str, dict[str, str]] = {}

    # Store initial state of all pods
    for pod in pod_list.items:
        _maybe_store_event(cluster_name, "ADDED", pod, node_label_cache, core_v1)

    resource_version = pod_list.metadata.resource_version
    logger.info(f"Starting pod watch on cluster={cluster_name} from resourceVersion={resource_version}")
    update_heartbeat()

    w = watch.Watch()
    event: K8sPodWatchEvent
    for event in w.stream(  # type: ignore[assignment]
        core_v1.list_namespaced_pod,
        namespace=cfg.JOB_NAMESPACE,
        label_selector=label_selector,
        resource_version=resource_version,
        timeout_seconds=WATCH_TIMEOUT_SECONDS,
    ):
        update_heartbeat()
        event_type, pod = event["type"], event["object"]
        if event_type in ("ADDED", "MODIFIED", "DELETED"):
            _maybe_store_event(cluster_name, event_type, pod, node_label_cache, core_v1)


def _watch_loop(cluster_name: str):
    """Main watch loop - watches pods and stores events."""
    logger.info(f"Watch loop starting for cluster={cluster_name}")
    while True:
        try:
            core_v1 = _get_k8s_client()
            if core_v1 is None:
                logger.warning("Eval cluster client unavailable, retrying in 30s")
                time.sleep(30)
                continue
            _watch_pods_with_client(core_v1, cluster_name)
        except Exception as e:
            logger.error(f"Watch error on cluster={cluster_name}, restarting: {e}", exc_info=True)
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
