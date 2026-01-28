import functools
import json
import logging
import threading
import time
from typing import Literal, Optional, TypedDict, cast
from urllib.parse import urlparse
from uuid import UUID

import boto3
from kubernetes import (
    client,
    watch,  # type: ignore[attr-defined]
)
from kubernetes.client.rest import ApiException  # type: ignore[attr-defined]
from kubernetes.config.incluster_config import load_incluster_config
from kubernetes.config.kube_config import load_kube_config
from metta_alo.rollout import PureSingleEpisodeResult, SingleEpisodeJob
from opentelemetry import trace as otel_trace

from metta.app_backend.clients.stats_client import StatsClient
from metta.app_backend.health_server import start_health_server, update_heartbeat
from metta.app_backend.job_runner.config import (
    LABEL_APP,
    LABEL_APP_VALUE,
    LABEL_JOB_ID,
    get_dispatch_config,
)
from metta.app_backend.job_runner.episode_recording import record_job_episode
from metta.app_backend.job_runner.tournament_cluster import get_tournament_clients
from metta.app_backend.models.job_request import JobRequestUpdate, JobStatus
from metta.common.otel.tracing import init_otel_tracing, trace
from metta.common.util.log_config import init_logging, suppress_noisy_logs

logger = logging.getLogger(__name__)

WATCH_TIMEOUT_SECONDS = 30
RECONCILE_INTERVAL_SECONDS = 60


@functools.cache
def _get_k8s_clients() -> tuple[client.CoreV1Api, client.BatchV1Api]:
    cfg = get_dispatch_config()
    if cfg.LOCAL_DEV:
        if not cfg.LOCAL_DEV_K8S_CONTEXT:
            raise ValueError("LOCAL_DEV=true requires LOCAL_DEV_K8S_CONTEXT to be set")
        load_kube_config(context=cfg.LOCAL_DEV_K8S_CONTEXT)
    else:
        load_incluster_config()
    return client.CoreV1Api(), client.BatchV1Api()


def _get_eval_k8s_clients() -> tuple[client.CoreV1Api, client.BatchV1Api] | None:
    cfg = get_dispatch_config()
    if not cfg.EVAL_CLUSTER_ROLE_ARN:
        return None
    try:
        return get_tournament_clients()
    except Exception as e:
        logger.error(f"Failed to create eval cluster clients: {e}", exc_info=True)
        return None


# ADDED: Pod created (usually starts in Pending phase)
# MODIFIED: Pod state changed (phase transitions, container status updates)
# DELETED: Pod removed from cluster
# BOOKMARK: Internal watch checkpoint (no actual change, just resourceVersion update)
# ERROR: Watch stream error
K8sPodWatchEventType = Literal["ADDED", "MODIFIED", "DELETED", "BOOKMARK", "ERROR"]


class K8sPodWatchEvent(TypedDict):
    type: K8sPodWatchEventType
    object: client.V1Pod


def _watch_pods_with_client(
    stats_client: StatsClient, core_v1: client.CoreV1Api, batch_v1: client.BatchV1Api, cluster_name: str
):
    cfg = get_dispatch_config()
    label_selector = f"{LABEL_APP}={LABEL_APP_VALUE}"

    pod_list = core_v1.list_namespaced_pod(namespace=cfg.JOB_NAMESPACE, label_selector=label_selector)
    if not pod_list.metadata or not pod_list.metadata.resource_version:
        logger.error(f"Invalid pod list on cluster={cluster_name}: {pod_list}")
        return

    for pod in pod_list.items:
        _handle_pod_state(stats_client, batch_v1, pod)

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
        if event_type in ("ADDED", "MODIFIED"):
            _handle_pod_state(stats_client, batch_v1, pod)
        elif event_type == "DELETED":
            _handle_pod_deleted(stats_client, pod)


def _watch_loop(
    stats_client: StatsClient,
    cluster_name: str,
    get_clients: callable,  # type: ignore[valid-type]
):
    logger.info(f"Watch loop starting for cluster={cluster_name}")
    while True:
        try:
            clients = get_clients()
            if clients is None:
                logger.warning("Eval cluster clients unavailable, retrying in 30s")
                time.sleep(30)
                continue
            core_v1, batch_v1 = clients
            _watch_pods_with_client(stats_client, core_v1, batch_v1, cluster_name)
        except Exception as e:
            logger.error(f"Watch error on cluster={cluster_name}, restarting: {e}", exc_info=True)
            time.sleep(1)


def run_watcher():
    cfg = get_dispatch_config()
    _get_k8s_clients()

    start_health_server()

    stats_client = StatsClient(backend_url=cfg.STATS_SERVER_URI, machine_token=cfg.MACHINE_TOKEN)
    stats_client._validate_authenticated()
    logger.info(f"Watcher started: stats_server_uri={cfg.STATS_SERVER_URI}, namespace={cfg.JOB_NAMESPACE}")

    eval_clients = _get_eval_k8s_clients()
    if eval_clients is not None:
        logger.info("Eval cluster configured, starting eval watch thread")
        t = threading.Thread(
            target=_watch_loop,
            args=(stats_client, "eval", _get_eval_k8s_clients),
            daemon=True,
        )
        t.start()
    else:
        logger.info("Eval cluster not configured, watching main cluster only")

    # TODO: Reconciliation disabled — tournament jobs run on the eval cluster,
    # so the main-cluster-only pod check would incorrectly mark them as failed.
    # Re-enable once we consolidate back to a single cluster.

    try:
        _watch_loop(stats_client, "main", _get_k8s_clients)
    finally:
        stats_client.close()


@trace("tournament.job.reconcile")
def _reconcile_stale_jobs(stats_client: StatsClient):
    """Check for jobs marked running/dispatched that have no corresponding pod."""
    cfg = get_dispatch_config()
    core_v1, _ = _get_k8s_clients()
    label_selector = f"{LABEL_APP}={LABEL_APP_VALUE}"

    try:
        pods = core_v1.list_namespaced_pod(namespace=cfg.JOB_NAMESPACE, label_selector=label_selector)
    except Exception as e:
        logger.error(f"Failed to list pods for reconciliation: {e}")
        return

    active_job_ids: set[UUID] = set()
    for pod in pods.items:
        info = _get_job_info(pod)
        if info:
            active_job_ids.add(info[0])

    try:
        running_jobs = stats_client.list_jobs(statuses=[JobStatus.running, JobStatus.dispatched])
    except Exception as e:
        logger.error(f"Failed to list running jobs for reconciliation: {e}")
        return

    stale_count = 0
    completed_count = 0
    for job in running_jobs:
        if job.id not in active_job_ids:
            if job.completed_at or job.result:
                logger.info(f"Reconciliation: job {job.id} has results but status={job.status}, marking completed")
                _update_job_status(stats_client, job.id, JobStatus.completed)
                completed_count += 1
            else:
                logger.warning(f"Reconciliation: job {job.id} marked {job.status} but no pod found, marking failed")
                _update_job_status(
                    stats_client, job.id, JobStatus.failed, error="Pod not found (reconciliation)", error_type="unknown"
                )
                stale_count += 1

    span = otel_trace.get_current_span()
    if span.is_recording():
        span.set_attribute("reconcile.jobs_checked", len(running_jobs))
        span.set_attribute("reconcile.pods_found", len(active_job_ids))
        span.set_attribute("reconcile.completed_count", completed_count)
        span.set_attribute("reconcile.failed_count", stale_count)

    if stale_count > 0 or completed_count > 0:
        logger.info(f"Reconciliation complete: {completed_count} completed, {stale_count} failed")


def _get_job_info(pod: client.V1Pod) -> tuple[UUID, str] | None:
    if not pod.metadata or not pod.metadata.labels:
        return None
    job_id_str = pod.metadata.labels.get(LABEL_JOB_ID)
    if not job_id_str:
        return None
    return UUID(job_id_str), pod.metadata.name or "unknown"


def _get_pod_env_var(pod: client.V1Pod, name: str) -> str | None:
    if not pod.spec or not pod.spec.containers:
        return None
    for container in pod.spec.containers:
        if not container.env:
            continue
        for env_var in container.env:
            if env_var.name == name:
                return env_var.value
    return None


def _parse_results_s3_location(
    results_uri: str,
    fallback_bucket: Optional[str],
    job_id: UUID,
) -> Optional[tuple[str, str]]:
    parsed = urlparse(results_uri)
    if parsed.scheme == "s3":
        bucket = parsed.netloc
        key = parsed.path.lstrip("/")
        if bucket and key:
            return bucket, key
    if parsed.scheme in ("http", "https"):
        host = parsed.netloc
        path = parsed.path.lstrip("/")
        if host.startswith("s3.") or host.startswith("s3-") or host == "s3.amazonaws.com":
            if "/" in path:
                bucket, key = path.split("/", 1)
                if bucket and key:
                    return bucket, key
        if ".s3" in host:
            bucket = host.split(".s3")[0]
            if bucket and path:
                return bucket, path
    if fallback_bucket:
        return fallback_bucket, f"jobs/{job_id}/results.json"
    return None


def read_results_from_s3(job_id: UUID, bucket: str, key: str) -> PureSingleEpisodeResult | None:
    s3_client = boto3.client("s3")

    try:
        response = s3_client.get_object(Bucket=bucket, Key=key)
        data = json.loads(response["Body"].read().decode("utf-8"))
        return PureSingleEpisodeResult.model_validate(data)
    except s3_client.exceptions.NoSuchKey:
        logger.warning(f"No results found in S3 for job {job_id}")
        return None
    except Exception as e:
        logger.error(f"Failed to read results from S3 for job {job_id}: {e}")
        return None


def _read_results_with_retry(job_id: UUID, bucket: str, key: str) -> PureSingleEpisodeResult | None:
    for attempt in range(1, 4):
        results = read_results_from_s3(job_id, bucket, key)
        if results is not None:
            return results
        if attempt < 3:
            time.sleep(attempt)
    return None


def _handle_pod_succeeded(stats_client: StatsClient, job_id: UUID, pod_name: str, pod: client.V1Pod):
    cfg = get_dispatch_config()
    results_uri = _get_pod_env_var(pod, "RESULTS_URI")

    if not results_uri:
        _update_job_status(stats_client, job_id, JobStatus.completed)
        logger.info(f"Job {job_id} completed (pod {pod_name}), no S3 pathway configured")
        return

    location = _parse_results_s3_location(results_uri, cfg.EVAL_S3_BUCKET, job_id)
    if location is None:
        _update_job_status(
            stats_client,
            job_id,
            JobStatus.failed,
            error="Failed to parse results URI for S3 download",
            error_type="result_missing",
        )
        logger.warning(f"Job {job_id} completed (pod {pod_name}), invalid results URI")
        return

    bucket, key = location
    results = _read_results_with_retry(job_id, bucket, key)
    if not results:
        _update_job_status(
            stats_client,
            job_id,
            JobStatus.failed,
            error="Results missing in S3 after retries",
            error_type="result_missing",
        )
        logger.warning(f"Job {job_id} completed (pod {pod_name}), no results in S3")
        return

    try:
        job_request = stats_client.get_job(job_id)
        job = SingleEpisodeJob.model_validate(job_request.job)
        record_job_episode(job_id, job, results, stats_client)
        _update_job_status(stats_client, job_id, JobStatus.completed)
        logger.info(f"Job {job_id} completed (pod {pod_name})")
    except Exception as e:
        logger.error(f"Failed to record episode for job {job_id}: {e}", exc_info=True)
        _update_job_status(stats_client, job_id, JobStatus.completed)
        logger.info(f"Job {job_id} completed (pod {pod_name}), episode recording failed")


@trace("tournament.job.status_update")
def _handle_pod_state(stats_client: StatsClient, batch_v1: client.BatchV1Api, pod: client.V1Pod):
    info = _get_job_info(pod)
    if not info or not pod.status:
        return

    job_id, pod_name = info
    phase = pod.status.phase

    span = otel_trace.get_current_span()
    if span.is_recording():
        span.set_attribute("job.id", str(job_id))
        span.set_attribute("pod.name", pod_name)
        if phase:
            span.set_attribute("pod.phase", phase)

    if phase == "Succeeded":
        _handle_pod_succeeded(stats_client, job_id, pod_name, pod)
        _delete_k8s_job_for_pod(batch_v1, pod)
    elif phase == "Failed":
        error = _get_pod_error(batch_v1, pod)
        error_type = _classify_error(error)
        _update_job_status(stats_client, job_id, JobStatus.failed, error=error, error_type=error_type)
        _delete_k8s_job_for_pod(batch_v1, pod)
        logger.info(f"Job {job_id} failed (pod {pod_name}): {error}")
    elif phase == "Running" and _is_container_running(pod):
        _update_job_status(stats_client, job_id, JobStatus.running, worker=pod_name)
        logger.debug(f"Job {job_id} running (pod {pod_name})")


def _handle_pod_deleted(stats_client: StatsClient, pod: client.V1Pod):
    info = _get_job_info(pod)
    if not info:
        return

    phase = pod.status.phase if pod.status else None
    if phase in ("Succeeded", "Failed"):
        return

    job_id, pod_name = info
    _update_job_status(stats_client, job_id, JobStatus.failed, error="Pod deleted unexpectedly", error_type="unknown")
    logger.warning(f"Job {job_id} failed: pod {pod_name} deleted unexpectedly (phase={phase})")


def _is_container_running(pod: client.V1Pod) -> bool:
    if not pod.status or not pod.status.container_statuses:
        return False
    return any(cs.state and cs.state.running for cs in pod.status.container_statuses)


def _get_pod_error(batch_v1: client.BatchV1Api, pod: client.V1Pod) -> str:
    job_error = _get_job_failure_reason(batch_v1, pod)
    if job_error:
        return job_error
    if pod.status:
        if pod.status.reason:
            return pod.status.reason
        if pod.status.container_statuses:
            for cs in pod.status.container_statuses:
                if cs.state and cs.state.terminated and cs.state.terminated.reason:
                    return cs.state.terminated.reason
    return (pod.status.message if pod.status else None) or "Pod failed"


def _classify_error(error: str) -> str:
    """Classify error into a low-cardinality bucket for metrics."""
    error_lower = error.lower()
    if "timeout" in error_lower or "deadline" in error_lower:
        return "timeout"
    if "oom" in error_lower or "out of memory" in error_lower or "oomkilled" in error_lower:
        return "oom"
    if any(
        marker in error_lower
        for marker in (
            "policy",
            "policy_uri",
            "policy_uris",
            "file not found",
            "no such file",
            "does_not_exist",
            "zipfile",
        )
    ):
        return "policy_error"
    return "unknown"


def _get_job_failure_reason(batch_v1: client.BatchV1Api, pod: client.V1Pod) -> str | None:
    """Get failure reason from the parent Job's conditions (e.g., DeadlineExceeded, BackoffLimitExceeded)."""
    job_name = _get_job_name_for_pod(pod)
    if not job_name:
        return None
    try:
        cfg = get_dispatch_config()
        job = cast(client.V1Job, batch_v1.read_namespaced_job(name=job_name, namespace=cfg.JOB_NAMESPACE))
        if job.status and job.status.conditions:
            for cond in job.status.conditions:
                if cond.type == "Failed" and cond.reason:
                    return cond.reason
    except Exception:
        pass
    return None


def _get_job_name_for_pod(pod: client.V1Pod) -> str | None:
    if not pod.metadata or not pod.metadata.owner_references:
        return None
    return next((ref.name for ref in pod.metadata.owner_references if ref.kind == "Job"), None)


def _delete_k8s_job_for_pod(batch_v1: client.BatchV1Api, pod: client.V1Pod):
    job_name = _get_job_name_for_pod(pod)
    if not job_name:
        return
    try:
        cfg = get_dispatch_config()
        batch_v1.delete_namespaced_job(name=job_name, namespace=cfg.JOB_NAMESPACE, propagation_policy="Background")
    except ApiException as e:
        if e.status == 404:
            logger.debug(f"K8s job {job_name} already deleted")
        else:
            logger.error(f"Failed to delete k8s job {job_name}: {e}")
    except Exception as e:
        logger.error(f"Failed to delete k8s job {job_name}: {e}")


def _update_job_status(
    stats_client: StatsClient,
    job_id: UUID,
    status: JobStatus,
    error: str | None = None,
    error_type: str | None = None,
    worker: str | None = None,
):
    try:
        current = stats_client.get_job(job_id)
        if current.status == status:
            return
        if current.status in (JobStatus.completed, JobStatus.failed):
            # Job already in terminal state, but still update error if we have one (e.g., OOMKilled)
            if error and not current.error:
                stats_client.update_job(job_id, JobRequestUpdate(error=error, error_type=error_type))
            return
        stats_client.update_job(
            job_id, JobRequestUpdate(status=status, error=error, error_type=error_type, worker=worker)
        )
    except Exception as e:
        logger.error(f"Failed to update job {job_id} status to {status}: {e}")


if __name__ == "__main__":
    init_logging()
    suppress_noisy_logs()
    init_otel_tracing(service_name="job-watcher")
    run_watcher()
