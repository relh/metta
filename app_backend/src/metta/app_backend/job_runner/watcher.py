import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Literal, TypedDict, cast
from uuid import UUID

import boto3
from botocore.client import BaseClient
from kubernetes import (
    client,
    watch,  # type: ignore[attr-defined]
)
from kubernetes.client.rest import ApiException  # type: ignore[attr-defined]
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
from metta.app_backend.job_runner.job_artifacts import job_logs_key, job_replay_key, job_results_key
from metta.app_backend.job_runner.k8s_event_store import store_k8s_event
from metta.app_backend.job_runner.tournament_cluster import get_tournament_clients
from metta.app_backend.models.job_request import JobRequestUpdate, JobStatus
from metta.common.otel.tracing import init_otel_tracing, trace
from metta.common.util.log_config import init_logging, suppress_noisy_logs

logger = logging.getLogger(__name__)

WATCH_TIMEOUT_SECONDS = 30
RECONCILE_INTERVAL_SECONDS = 60
_terminal_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="pod-terminal")

_s3_client: BaseClient | None = None
_s3_client_lock = threading.Lock()


def _get_s3_client() -> BaseClient:
    global _s3_client
    if _s3_client is None:
        with _s3_client_lock:
            if _s3_client is None:
                _s3_client = boto3.client("s3")
    return _s3_client


def _get_k8s_clients() -> tuple[client.CoreV1Api, client.BatchV1Api]:
    cfg = get_dispatch_config()
    if cfg.LOCAL_DEV:
        if not cfg.LOCAL_DEV_K8S_CONTEXT:
            raise ValueError("LOCAL_DEV=true requires LOCAL_DEV_K8S_CONTEXT to be set")
        load_kube_config(context=cfg.LOCAL_DEV_K8S_CONTEXT)
        return client.CoreV1Api(), client.BatchV1Api()
    return get_tournament_clients()


# ADDED: Pod created (usually starts in Pending phase)
# MODIFIED: Pod state changed (phase transitions, container status updates)
# DELETED: Pod removed from cluster
# BOOKMARK: Internal watch checkpoint (no actual change, just resourceVersion update)
# ERROR: Watch stream error
K8sPodWatchEventType = Literal["ADDED", "MODIFIED", "DELETED", "BOOKMARK", "ERROR"]


class K8sPodWatchEvent(TypedDict):
    type: K8sPodWatchEventType
    object: client.V1Pod


def _capture_pod_logs(core_v1: client.CoreV1Api, pod: client.V1Pod, job_id: UUID):
    cfg = get_dispatch_config()
    pod_name = pod.metadata.name if pod.metadata else None
    if not pod_name:
        return
    try:
        logs = core_v1.read_namespaced_pod_log(
            name=pod_name,
            namespace=cfg.JOB_NAMESPACE,
            container="worker",
            tail_lines=10000,
        )
    except Exception as e:
        logger.warning(f"Failed to read logs for job {job_id} pod {pod_name}: {e}")
        return
    if not logs:
        return
    try:
        _get_s3_client().put_object(
            Bucket=cfg.EVAL_S3_BUCKET,
            Key=job_logs_key(job_id),
            Body=logs.encode("utf-8"),
            ContentType="text/plain",
        )
        logger.info(f"Captured logs for job {job_id} ({len(logs)} bytes)")
    except Exception as e:
        logger.error(f"Failed to upload logs for job {job_id}: {e}")


def _cleanup_terminated_pod(core_v1: client.CoreV1Api, batch_v1: client.BatchV1Api, pod: client.V1Pod, job_id: UUID):
    _capture_pod_logs(core_v1, pod, job_id)
    _delete_k8s_job_for_pod(batch_v1, pod)


def _watch_pods_with_client(
    stats_client: StatsClient,
    core_v1: client.CoreV1Api,
    batch_v1: client.BatchV1Api,
    cluster_name: str,
):
    cfg = get_dispatch_config()
    label_selector = f"{LABEL_APP}={LABEL_APP_VALUE}"

    pod_list = core_v1.list_namespaced_pod(namespace=cfg.JOB_NAMESPACE, label_selector=label_selector)
    if not pod_list.metadata or not pod_list.metadata.resource_version:
        logger.error(f"Invalid pod list on cluster={cluster_name}: {pod_list}")
        return

    for pod in pod_list.items:
        _maybe_store_event(cluster_name, "ADDED", pod)
        _handle_pod_state(stats_client, core_v1, batch_v1, pod)

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
            _maybe_store_event(cluster_name, event_type, pod)
            _handle_pod_state(stats_client, core_v1, batch_v1, pod)
        elif event_type == "DELETED":
            _maybe_store_event(cluster_name, event_type, pod)
            _handle_pod_deleted(stats_client, pod)


def _watch_loop(
    stats_client: StatsClient,
    cluster_name: str,
    get_clients: callable,  # type: ignore[valid-type]
):
    logger.info(f"Watch loop starting for cluster={cluster_name}")
    last_reconcile = 0.0
    while True:
        try:
            clients = get_clients()
            if clients is None:
                logger.warning("Eval cluster clients unavailable, retrying in 30s")
                time.sleep(30)
                continue
            core_v1, batch_v1 = clients
            _watch_pods_with_client(stats_client, core_v1, batch_v1, cluster_name)

            now = time.monotonic()
            if now - last_reconcile >= RECONCILE_INTERVAL_SECONDS:
                _reconcile_stale_jobs(stats_client)
                last_reconcile = now
        except Exception as e:
            logger.error(f"Watch error on cluster={cluster_name}, restarting: {e}", exc_info=True)
            time.sleep(1)


def run_watcher():
    cfg = get_dispatch_config()
    start_health_server()

    stats_client = StatsClient(backend_url=cfg.STATS_SERVER_URI, machine_token=cfg.MACHINE_TOKEN)
    stats_client._validate_authenticated()
    logger.info(f"Watcher started: stats_server_uri={cfg.STATS_SERVER_URI}, namespace={cfg.JOB_NAMESPACE}")

    try:
        _watch_loop(stats_client, "eval", _get_k8s_clients)
    finally:
        stats_client.close()


def _maybe_store_event(cluster: str, event_type: str, pod: client.V1Pod) -> None:
    try:
        store_k8s_event(cluster, event_type, pod)
    except Exception:
        logger.error("Failed to persist k8s watch event", exc_info=True)


@trace("tournament.job.reconcile")
def _reconcile_stale_jobs(stats_client: StatsClient):
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


def read_results_from_s3(job_id: UUID, bucket: str, key: str) -> tuple[PureSingleEpisodeResult | None, str | None]:
    s3 = _get_s3_client()
    try:
        response = s3.get_object(Bucket=bucket, Key=key)
        data = json.loads(response["Body"].read().decode("utf-8"))
        return PureSingleEpisodeResult.model_validate(data), None
    except s3.exceptions.NoSuchKey:
        msg = f"NoSuchKey s3://{bucket}/{key}"
        logger.warning(f"No results found in S3 for job {job_id}: {msg}")
        return None, msg
    except Exception as e:
        msg = f"{type(e).__name__}: {e}"
        logger.error(f"Failed to read results from S3 for job {job_id}: {msg}")
        return None, msg


def _read_results_with_retry(job_id: UUID, bucket: str, key: str) -> tuple[PureSingleEpisodeResult | None, str | None]:
    # The episode runner uploads results via a presigned PUT from inside the pod.
    # The k8s Succeeded event can arrive before the PUT is visible in S3, so we
    # retry with exponential backoff (~15s window) to avoid false "results missing" failures.
    delays = [1, 2, 4, 8]
    last_error: str | None = None
    for i, delay in enumerate(delays):
        results, err = read_results_from_s3(job_id, bucket, key)
        if results is not None:
            return results, None
        last_error = err
        if i < len(delays) - 1:
            time.sleep(delay)
    return None, last_error


def _copy_replay_to_public(job_id: UUID, replay_uri: str | None) -> bool:
    if not replay_uri or not replay_uri.startswith("s3://"):
        return True

    cfg = get_dispatch_config()
    if not cfg.EVAL_S3_BUCKET:
        return False

    source_key = job_replay_key(job_id)
    s3 = _get_s3_client()

    # Retry with backoff similar to _read_results_with_retry - the replay upload
    # may complete slightly after the results upload
    delays = [1, 2, 4, 8]
    replay_exists = False
    for i, delay in enumerate(delays):
        try:
            s3.head_object(Bucket=cfg.EVAL_S3_BUCKET, Key=source_key)
            replay_exists = True
            break
        except s3.exceptions.ClientError:
            if i < len(delays) - 1:
                time.sleep(delay)

    if not replay_exists:
        logger.warning(f"Replay not found in EVAL bucket for job {job_id}, skipping copy")
        return True

    parts = replay_uri.removeprefix("s3://").split("/", 1)
    if len(parts) != 2:
        logger.warning(f"Invalid replay_uri format: {replay_uri}")
        return False
    dest_bucket, dest_key = parts

    try:
        s3.copy_object(
            Bucket=dest_bucket,
            Key=dest_key,
            CopySource={"Bucket": cfg.EVAL_S3_BUCKET, "Key": source_key},
            MetadataDirective="COPY",
        )
        logger.info(f"Copied replay to s3://{dest_bucket}/{dest_key} for job {job_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to copy replay for job {job_id}: {e}")
        return False


def _handle_pod_succeeded(stats_client: StatsClient, job_id: UUID, pod_name: str):
    cfg = get_dispatch_config()
    results, read_error = _read_results_with_retry(job_id, cfg.EVAL_S3_BUCKET, job_results_key(job_id))
    if not results:
        detail = f" (last error: {read_error})" if read_error else ""
        error_type = "result_missing" if not read_error or "NoSuchKey" in read_error else "result_error"
        _update_job_status(
            stats_client,
            job_id,
            JobStatus.failed,
            error=f"Pod exited with code 0 but results not found in S3{detail}",
            error_type=error_type,
        )
        logger.warning(f"Job {job_id} completed (pod {pod_name}), no results in S3{detail}")
        return

    try:
        job_request = stats_client.get_job(job_id)
        job = SingleEpisodeJob.model_validate(job_request.job)
        _copy_replay_to_public(job_id, job.replay_uri)
        record_job_episode(job_id, job, results, stats_client)  # pyright: ignore[reportArgumentType]
        _update_job_status(stats_client, job_id, JobStatus.completed)
        logger.info(f"Job {job_id} completed (pod {pod_name})")
    except Exception as e:
        logger.error(f"Failed to record episode for job {job_id}: {e}", exc_info=True)
        _update_job_status(stats_client, job_id, JobStatus.completed)
        logger.info(f"Job {job_id} completed (pod {pod_name}), episode recording failed")


def _handle_pod_terminal(
    stats_client: StatsClient,
    core_v1: client.CoreV1Api,
    batch_v1: client.BatchV1Api,
    pod: client.V1Pod,
    job_id: UUID,
    pod_name: str,
):
    try:
        phase = pod.status.phase if pod.status else None
        if phase == "Succeeded":
            _handle_pod_succeeded(stats_client, job_id, pod_name)
        elif phase == "Failed":
            error = _get_pod_error(batch_v1, pod)
            error_type = _classify_error(error)
            _update_job_status(stats_client, job_id, JobStatus.failed, error=error, error_type=error_type)
            logger.info(f"Job {job_id} failed (pod {pod_name}): {error}")
        _cleanup_terminated_pod(core_v1, batch_v1, pod, job_id)
    except Exception:
        logger.error(f"Unhandled error processing terminal pod {pod_name} for job {job_id}", exc_info=True)


@trace("tournament.job.status_update")
def _handle_pod_state(
    stats_client: StatsClient, core_v1: client.CoreV1Api, batch_v1: client.BatchV1Api, pod: client.V1Pod
):
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
        _terminal_executor.submit(_handle_pod_terminal, stats_client, core_v1, batch_v1, pod, job_id, pod_name)
    elif phase == "Failed":
        _terminal_executor.submit(_handle_pod_terminal, stats_client, core_v1, batch_v1, pod, job_id, pod_name)
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
