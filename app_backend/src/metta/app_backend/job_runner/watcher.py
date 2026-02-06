import json
import logging
import threading
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from typing import Any, Literal, TypedDict, cast
from uuid import UUID

import boto3
from botocore.client import BaseClient
from kubernetes import (
    client,
    watch,  # type: ignore[attr-defined]
)
from kubernetes.client.rest import ApiException  # type: ignore[attr-defined]
from kubernetes.config.kube_config import load_kube_config
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
from metta.app_backend.job_runner.job_artifacts import (
    job_logs_key,
    job_replay_key,
    job_results_key,
    job_runtime_info_key,
)
from metta.app_backend.job_runner.k8s_event_store import store_k8s_event
from metta.app_backend.job_runner.tournament_cluster import get_tournament_clients
from metta.app_backend.models.job_request import JobRequestUpdate, JobStatus
from metta.common.otel.tracing import init_otel_tracing, trace
from metta.common.util.log_config import init_logging, suppress_noisy_logs
from mettagrid.runner.types import PureSingleEpisodeResult, RuntimeInfo, SingleEpisodeJob

logger = logging.getLogger(__name__)

WATCH_TIMEOUT_SECONDS = 30
RECONCILE_INTERVAL_SECONDS = 60
_terminal_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="pod-terminal")
_job_locks: dict[UUID, threading.Lock] = {}
_job_lock_refs: dict[UUID, int] = {}
_job_locks_lock = threading.Lock()

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
                    stats_client,
                    job.id,
                    JobStatus.failed,
                    error="Pod not found (reconciliation)",
                    error_type="pod_not_found",
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


def _get_runner_image(pod: client.V1Pod) -> str | None:
    if not pod.status or not pod.status.container_statuses:
        return None
    return pod.status.container_statuses[0].image_id or None


def _read_runtime_info(job_id: UUID) -> RuntimeInfo:
    cfg = get_dispatch_config()
    s3 = _get_s3_client()
    try:
        response = s3.get_object(Bucket=cfg.EVAL_S3_BUCKET, Key=job_runtime_info_key(job_id))
        return RuntimeInfo.model_validate_json(response["Body"].read())
    except Exception:
        return RuntimeInfo()


def _handle_pod_succeeded(
    stats_client: StatsClient, job_id: UUID, pod_name: str, result_data: dict[str, Any] | None = None
):
    job_request = stats_client.get_job(job_id)
    if job_request.status in (JobStatus.completed, JobStatus.failed):
        logger.info(f"Job {job_id} already {job_request.status.value}, skipping (pod {pod_name})")
        return

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
        job = SingleEpisodeJob.model_validate(job_request.job)
        _copy_replay_to_public(job_id, job.replay_uri)
        record_job_episode(job_id, job, results, stats_client, result_data=result_data)  # pyright: ignore[reportArgumentType]
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
        runner_image = _get_runner_image(pod)
        result_data: dict[str, Any] = {}
        if runner_image:
            result_data["runner_image"] = runner_image
        runtime_info = _read_runtime_info(job_id)
        result_data.update(runtime_info.model_dump(exclude_none=True))
        with _job_lock(job_id):
            phase = pod.status.phase if pod.status else None
            if phase == "Succeeded":
                _handle_pod_succeeded(stats_client, job_id, pod_name, result_data=result_data)
            elif phase == "Failed":
                # Try to extract meaningful error from logs first
                k8s_error = _get_pod_error(batch_v1, pod)
                log_error = _extract_error_from_logs_with_retry(job_id)

                # Prefer log error if available, otherwise fall back to K8s error
                error = log_error if log_error else k8s_error
                error_type = _classify_error(error)

                _update_job_status(stats_client, job_id, JobStatus.failed, error=error, error_type=error_type)
                if result_data:
                    stats_client.update_job(job_id, JobRequestUpdate(result=result_data))

                # Log which error source was used for debugging
                error_source = "logs" if log_error else "k8s"
                logger.info(f"Job {job_id} failed (pod {pod_name}, error_source={error_source}): {error}")
        _cleanup_terminated_pod(core_v1, batch_v1, pod, job_id)
    except Exception:
        logger.error(f"Unhandled error processing terminal pod {pod_name} for job {job_id}", exc_info=True)


@contextmanager
def _job_lock(job_id: UUID) -> Iterator[None]:
    with _job_locks_lock:
        if job_id not in _job_locks:
            _job_locks[job_id] = threading.Lock()
            _job_lock_refs[job_id] = 0
        _job_lock_refs[job_id] += 1
        lock = _job_locks[job_id]
    with lock:
        try:
            yield
        finally:
            with _job_locks_lock:
                _job_lock_refs[job_id] -= 1
                if _job_lock_refs[job_id] == 0:
                    _job_locks.pop(job_id, None)
                    _job_lock_refs.pop(job_id, None)


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

    if phase in ("Succeeded", "Failed"):
        _terminal_executor.submit(_handle_pod_terminal, stats_client, core_v1, batch_v1, pod, job_id, pod_name)
    elif phase == "Running" and _is_container_running(pod):
        with _job_lock(job_id):
            job_request = stats_client.get_job(job_id)
            if job_request.status in (JobStatus.completed, JobStatus.failed):
                return
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
    _update_job_status(
        stats_client,
        job_id,
        JobStatus.failed,
        error="Pod deleted unexpectedly",
        error_type="pod_deleted",
    )
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


def _extract_python_traceback(lines: list[str]) -> str | None:
    """Extract the final exception from a Python traceback.

    Looks for:
    - "Traceback (most recent call last):"
    - Exception line (e.g., "ValueError: invalid value")
    - Extracts exception with 2-3 lines of context
    """
    # Scan backwards for traceback marker
    traceback_start = -1
    for i in range(len(lines) - 1, -1, -1):
        if "Traceback (most recent call last):" in lines[i]:
            traceback_start = i
            break

    if traceback_start == -1:
        return None

    # Look for the final exception (last line that matches exception pattern)
    exception_keywords = [
        "Error:",
        "Exception:",
        "Error",
        "Exception",
        "AssertionError",
        "ValueError",
        "RuntimeError",
        "TypeError",
        "AttributeError",
        "KeyError",
        "IndexError",
        "ModuleNotFoundError",
        "ImportError",
        "PolicyStepError",
        "TimeoutError",
        "ConnectionError",
    ]

    exception_line = -1
    for i in range(len(lines) - 1, traceback_start, -1):
        line = lines[i].strip()
        if any(keyword in line for keyword in exception_keywords):
            exception_line = i
            break

    if exception_line == -1:
        # No clear exception found, return traceback header with some context
        end_idx = min(traceback_start + 10, len(lines))
        return "\n".join(lines[traceback_start:end_idx])

    # Extract exception with context (2 lines before, exception line, 2 lines after)
    start_idx = max(traceback_start, exception_line - 2)
    end_idx = min(exception_line + 3, len(lines))
    context_lines = [line for line in lines[start_idx:end_idx] if line.strip()]

    # Limit total length to ~500 chars
    result = "\n".join(context_lines)
    if len(result) > 500:
        result = result[:500] + "..."

    return result


def _extract_policy_server_error(lines: list[str]) -> str | None:
    """Extract policy server-specific errors.

    Looks for:
    - "Policy server failed during episode execution"
    - "Policy server returned {status_code}"
    - "Policy server request failed"
    - RuntimeError from manager.py with log tails
    """
    policy_error_markers = [
        "Policy server failed",
        "Policy server returned",
        "Policy server request failed",
        "Policy server exited",
        "PolicyStepError",
        "failed to connect",
        "connection refused",
        "grpc",
    ]

    # Scan backwards for policy-related errors (case-insensitive to match varied log output)
    for i in range(len(lines) - 1, max(0, len(lines) - 100), -1):
        line = lines[i]
        line_lower = line.lower()
        if any(marker.lower() in line_lower for marker in policy_error_markers):
            # Extract this line and next 3-5 lines of context
            start_idx = max(0, i - 2)
            end_idx = min(i + 5, len(lines))
            context_lines = [ln for ln in lines[start_idx:end_idx] if ln.strip()]

            result = "\n".join(context_lines)
            if len(result) > 500:
                result = result[:500] + "..."
            return result

    return None


def _extract_generic_error(lines: list[str]) -> str | None:
    """Extract any error-like message from logs.

    Fallback strategy that looks for:
    - Lines containing ERROR, CRITICAL, FAILED
    - Lines with "error:", "failed:", "exception:"
    """
    error_patterns = [
        "ERROR",
        "CRITICAL",
        "FAILED",
        "FATAL",
        "error:",
        "Error:",
        "failed:",
        "Failed:",
        "exception:",
        "Exception:",
        "abort",
        "crash",
    ]

    # Scan backwards for any error-like content (case-insensitive)
    for i in range(len(lines) - 1, max(0, len(lines) - 100), -1):
        line = lines[i]
        line_lower = line.lower()
        if any(pattern.lower() in line_lower for pattern in error_patterns):
            # Extract with minimal context
            start_idx = max(0, i - 1)
            end_idx = min(i + 3, len(lines))
            context_lines = [ln for ln in lines[start_idx:end_idx] if ln.strip()]

            result = "\n".join(context_lines)
            if len(result) > 500:
                result = result[:500] + "..."
            return result

    return None


def _extract_error_from_logs(job_id: UUID, max_lines: int = 200) -> str | None:
    """Extract meaningful error message from pod logs stored in S3.

    Args:
        job_id: The job ID to extract logs for
        max_lines: Maximum number of lines from end of log to scan (default: 200)

    Returns:
        Extracted error message or None if extraction failed
    """
    cfg = get_dispatch_config()
    s3 = _get_s3_client()

    # Read logs from S3
    try:
        response = s3.get_object(Bucket=cfg.EVAL_S3_BUCKET, Key=job_logs_key(job_id))
        logs = response["Body"].read().decode("utf-8", errors="replace")
    except s3.exceptions.NoSuchKey:
        logger.debug(f"No logs found in S3 for job {job_id}")
        return None
    except Exception as e:
        logger.warning(f"Failed to read logs from S3 for job {job_id}: {e}")
        return None

    if not logs:
        return None

    # Get last N lines efficiently
    lines = logs.split("\n")
    tail_lines = lines[-max_lines:] if len(lines) > max_lines else lines

    # Try multiple extraction strategies in order of specificity
    error = _extract_python_traceback(tail_lines)
    if error:
        logger.debug(f"Extracted Python traceback error for job {job_id}")
        return error

    error = _extract_policy_server_error(tail_lines)
    if error:
        logger.debug(f"Extracted policy server error for job {job_id}")
        return error

    error = _extract_generic_error(tail_lines)
    if error:
        logger.debug(f"Extracted generic error for job {job_id}")
        return error

    return None


def _extract_error_from_logs_with_retry(job_id: UUID) -> str | None:
    """Extract error from logs with retry logic.

    Logs may not be immediately available in S3 after _capture_pod_logs() completes
    due to S3 eventual consistency. Retry with exponential backoff similar to
    _read_results_with_retry().
    """
    delays = [0.5, 1, 2]  # Shorter delays than results (logs uploaded by watcher, not pod)

    for i, delay in enumerate(delays):
        error = _extract_error_from_logs(job_id)
        if error:
            return error
        if i < len(delays) - 1:
            time.sleep(delay)

    return None


def _classify_error(error: str) -> str:
    """Classify error into a low-cardinality bucket for metrics.

    Errors from spawning policy servers or policy server failures are classified as policy_error.
    """
    error_lower = error.lower()

    # Infrastructure errors take precedence
    if "timeout" in error_lower or "deadline" in error_lower:
        return "timeout"
    if "oom" in error_lower or "out of memory" in error_lower or "oomkilled" in error_lower:
        return "oom"

    # Exclude known infrastructure errors (image pull, container runtime) from policy classification
    infra_markers = (
        "image pull",
        "imagepullbackoff",
        "errimagepull",
        "pull access denied",
        "manifest not found",
        "container runtime",
        "failed to pull image",
    )
    if any(marker in error_lower for marker in infra_markers):
        return "unknown"

    # Policy-related errors: includes spawning failures and server errors
    policy_markers = (
        # Explicit policy references
        "policy",
        "policy_uri",
        "policy_uris",
        "policy server",
        "policy-server",
        # File/loading errors (often policy artifacts)
        "file not found",
        "no such file",
        "does_not_exist",
        "zipfile",
        # gRPC and server connectivity (policy server communication)
        "grpc",
        "rpc error",
        "connection refused",
        "connection error",
        "connection failed",
        "failed to connect",
        "cannot connect",
        # Server-side errors from policy execution
        "server error",
        "server failed",
        "server crashed",
    )

    if any(marker in error_lower for marker in policy_markers):
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
