"""
K8s Event Processor - processes stored k8s events from the database.

This decouples event storage (watcher) from event processing, enabling:
- Replay of events for debugging
- Parallel processing if needed
- Cleaner separation of concerns
"""

from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from kubernetes import client
from kubernetes.client.rest import ApiException  # type: ignore[attr-defined]
from kubernetes.config.kube_config import load_kube_config
from sqlmodel import Session, create_engine, select

from metta.app_backend.clients.stats_client import StatsClient
from metta.app_backend.config import settings
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
    job_results_key,
    job_runtime_info_key,
)
from metta.app_backend.job_runner.shared import capture_pod_logs, copy_replay_to_public, get_s3_client
from metta.app_backend.job_runner.tournament_cluster import get_tournament_clients
from metta.app_backend.models.job_request import JobRequestUpdate, JobStatus
from metta.app_backend.models.k8s_events import K8sEvent
from metta.common.otel.tracing import init_otel_tracing, trace
from metta.common.util.log_config import init_logging, suppress_noisy_logs
from mettagrid.runner.types import PureSingleEpisodeResult, RuntimeInfo, SingleEpisodeJob

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 5
BATCH_SIZE = 100
RECONCILE_INTERVAL_SECONDS = 60
RECONCILE_GRACE_PERIOD_SECONDS = 300

_db_engine = None


def _get_db_engine():
    global _db_engine
    if _db_engine is None:
        if not settings.STATS_DB_URI:
            raise ValueError("STATS_DB_URI not set")
        # Normalize postgres:// to postgresql:// for SQLAlchemy compatibility
        uri = settings.STATS_DB_URI
        if uri.startswith("postgres://"):
            uri = uri.replace("postgres://", "postgresql://", 1)
        _db_engine = create_engine(uri, pool_pre_ping=True)
    return _db_engine


def _get_k8s_clients() -> tuple[client.CoreV1Api, client.BatchV1Api] | None:
    cfg = get_dispatch_config()
    if cfg.LOCAL_DEV:
        if not cfg.LOCAL_DEV_K8S_CONTEXT:
            raise ValueError("LOCAL_DEV=true requires LOCAL_DEV_K8S_CONTEXT to be set")
        load_kube_config(context=cfg.LOCAL_DEV_K8S_CONTEXT)
        return client.CoreV1Api(), client.BatchV1Api()
    return get_tournament_clients()


def _fetch_unprocessed_events(session: Session, limit: int = BATCH_SIZE) -> list[K8sEvent]:
    """Fetch unprocessed events ordered by event_time."""
    stmt = (
        select(K8sEvent)
        .where(K8sEvent.processed_at.is_(None))  # type: ignore[union-attr]
        .order_by(K8sEvent.event_time)  # type: ignore[arg-type]
        .limit(limit)
    )
    return list(session.exec(stmt).all())


def _mark_processed(session: Session, event: K8sEvent) -> None:
    """Mark an event as processed."""
    event.processed_at = datetime.now(UTC)
    session.add(event)
    session.commit()


def _get_job_info_from_event(event_data: dict) -> tuple[UUID, str] | None:
    """Extract job_id and pod_name from stored event data."""
    pod_data = event_data.get("object", {})
    metadata = pod_data.get("metadata", {})
    labels = metadata.get("labels", {})
    pod_name = metadata.get("name", "unknown")

    job_id_str = labels.get(LABEL_JOB_ID)
    if not job_id_str:
        return None

    try:
        return UUID(job_id_str), pod_name
    except ValueError:
        logger.warning(f"Invalid job_id label '{job_id_str}' for pod {pod_name}")
        return None


def _get_pod_phase_from_event(event_data: dict) -> str | None:
    """Extract pod phase from stored event data."""
    pod_data = event_data.get("object", {})
    status = pod_data.get("status", {})
    return status.get("phase")


def _read_results_from_s3(job_id: UUID, bucket: str, key: str) -> tuple[PureSingleEpisodeResult | None, str | None]:
    s3 = get_s3_client()
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
    delays = [1, 2, 4, 8]
    last_error: str | None = None
    for i, delay in enumerate(delays):
        results, err = _read_results_from_s3(job_id, bucket, key)
        if results is not None:
            return results, None
        last_error = err
        if i < len(delays) - 1:
            time.sleep(delay)
    return None, last_error


def _get_job_name_from_event(event_data: dict) -> str | None:
    """Get the parent Job name from pod event data."""
    pod_data = event_data.get("object", {})
    metadata = pod_data.get("metadata", {})
    owner_refs = metadata.get("ownerReferences", [])
    return next((ref["name"] for ref in owner_refs if ref.get("kind") == "Job"), None)


def _delete_k8s_job(batch_v1: client.BatchV1Api, job_name: str):
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


def _get_job_failure_reason(batch_v1: client.BatchV1Api, job_name: str) -> str | None:
    """Get failure reason from the parent Job's conditions (e.g., DeadlineExceeded, BackoffLimitExceeded)."""
    if not job_name:
        return None
    try:
        cfg = get_dispatch_config()
        job = batch_v1.read_namespaced_job(name=job_name, namespace=cfg.JOB_NAMESPACE)
        if job.status and job.status.conditions:  # type: ignore[union-attr]
            for cond in job.status.conditions:  # type: ignore[union-attr]
                if cond.type == "Failed" and cond.reason:
                    return cond.reason
    except Exception:
        pass
    return None


def _get_pod_error_from_event(event_data: dict, batch_v1: client.BatchV1Api) -> str:
    """Extract error info from stored event data and K8s Job status."""
    # First try to get failure reason from parent Job
    job_name = _get_job_name_from_event(event_data)
    if job_name:
        job_error = _get_job_failure_reason(batch_v1, job_name)
        if job_error:
            return job_error

    # Fall back to pod status
    pod_data = event_data.get("object", {})
    status = pod_data.get("status", {})

    if status.get("reason"):
        return status["reason"]

    container_statuses = status.get("containerStatuses", [])
    for cs in container_statuses:
        state = cs.get("state", {})
        terminated = state.get("terminated", {})
        if terminated.get("reason"):
            return terminated["reason"]

    return status.get("message") or "Pod failed"


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
    s3 = get_s3_client()

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

    Logs may not be immediately available in S3 after capture_pod_logs() completes
    due to S3 eventual consistency. Retry with exponential backoff similar to
    _read_results_with_retry().
    """
    delays = [0.5, 1, 2]  # Shorter delays than results (logs uploaded by event_processor)

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


def _get_runner_image_from_event(event_data: dict) -> str | None:
    """Extract runner image ID from stored event data."""
    pod_data = event_data.get("object", {})
    status = pod_data.get("status", {})
    container_statuses = status.get("containerStatuses", [])
    if not container_statuses:
        return None
    return container_statuses[0].get("imageID")


def _get_instance_type_from_event(event_data: dict, core_v1: client.CoreV1Api) -> str | None:
    pod_data = event_data.get("object", {})
    node_name = pod_data.get("spec", {}).get("nodeName")
    if not node_name:
        return None
    try:
        node = cast(client.V1Node, core_v1.read_node(node_name))
    except ApiException:
        return None
    labels = node.metadata.labels if node.metadata else None
    return (labels or {}).get("node.kubernetes.io/instance-type")


def _read_runtime_info(job_id: UUID) -> RuntimeInfo:
    """Read runtime info from S3."""
    cfg = get_dispatch_config()
    s3 = get_s3_client()
    try:
        response = s3.get_object(Bucket=cfg.EVAL_S3_BUCKET, Key=job_runtime_info_key(job_id))
        return RuntimeInfo.model_validate_json(response["Body"].read())
    except Exception:
        return RuntimeInfo()


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
            if error and not current.error:
                stats_client.update_job(job_id, JobRequestUpdate(error=error, error_type=error_type))
            return
        stats_client.update_job(
            job_id, JobRequestUpdate(status=status, error=error, error_type=error_type, worker=worker)
        )
    except Exception as e:
        logger.error(f"Failed to update job {job_id} status to {status}: {e}")


def _is_container_running_from_event(event_data: dict) -> bool:
    """Check if any container is running from stored event data."""
    pod_data = event_data.get("object", {})
    status = pod_data.get("status", {})
    container_statuses = status.get("containerStatuses", [])
    return any(cs.get("state", {}).get("running") for cs in container_statuses)


@trace("tournament.event_processor.handle_succeeded")
def _handle_pod_succeeded(
    stats_client: StatsClient, core_v1: client.CoreV1Api, job_id: UUID, pod_name: str, event_data: dict
):
    # Deduplication: check if job is already in terminal state
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
        # Capture runner_image, instance_type, and runtime_info for episode recording
        result_data: dict[str, Any] = {}
        runner_image = _get_runner_image_from_event(event_data)
        if runner_image:
            result_data["runner_image"] = runner_image
        instance_type = _get_instance_type_from_event(event_data, core_v1)
        if instance_type:
            result_data["instance_type"] = instance_type
        runtime_info = _read_runtime_info(job_id)
        result_data.update(runtime_info.model_dump(exclude_none=True))

        job = SingleEpisodeJob.model_validate(job_request.job)
        replay_uri = copy_replay_to_public(job_id) if not job.skip_replay else None
        record_job_episode(job_id, job, results, stats_client, result_data=result_data, replay_uri=replay_uri)  # pyright: ignore[reportArgumentType]
        _update_job_status(stats_client, job_id, JobStatus.completed)
        logger.info(f"Job {job_id} completed (pod {pod_name})")
    except Exception as e:
        logger.error(f"Failed to record episode for job {job_id}: {e}", exc_info=True)
        _update_job_status(stats_client, job_id, JobStatus.completed)
        logger.info(f"Job {job_id} completed (pod {pod_name}), episode recording failed")


@trace("tournament.event_processor.process_event")
def _process_event(
    stats_client: StatsClient,
    core_v1: client.CoreV1Api,
    batch_v1: client.BatchV1Api,
    event: K8sEvent,
) -> None:
    """Process a single k8s event."""
    event_data = event.event
    event_type = event_data.get("type")

    info = _get_job_info_from_event(event_data)
    if not info:
        return

    job_id, pod_name = info
    phase = _get_pod_phase_from_event(event_data)

    if event_type in ("ADDED", "MODIFIED"):
        if phase == "Succeeded":
            _handle_pod_succeeded(stats_client, core_v1, job_id, pod_name, event_data)
            capture_pod_logs(core_v1, pod_name, job_id)
            job_name = _get_job_name_from_event(event_data)
            if job_name:
                _delete_k8s_job(batch_v1, job_name)
        elif phase == "Failed":
            # Capture logs first so they're available for extraction
            capture_pod_logs(core_v1, pod_name, job_id)

            # Try to extract meaningful error from logs first
            k8s_error = _get_pod_error_from_event(event_data, batch_v1)
            log_error = _extract_error_from_logs_with_retry(job_id)

            # Prefer log error if available, otherwise fall back to K8s error
            error = log_error if log_error else k8s_error
            error_type = _classify_error(error)

            _update_job_status(stats_client, job_id, JobStatus.failed, error=error, error_type=error_type)

            # Log which error source was used for debugging
            error_source = "logs" if log_error else "k8s"
            logger.info(f"Job {job_id} failed (pod {pod_name}, error_source={error_source}): {error}")

            job_name = _get_job_name_from_event(event_data)
            if job_name:
                _delete_k8s_job(batch_v1, job_name)
        elif phase == "Running" and _is_container_running_from_event(event_data):
            _update_job_status(stats_client, job_id, JobStatus.running, worker=pod_name)
            logger.debug(f"Job {job_id} running (pod {pod_name})")

    elif event_type == "DELETED":
        if phase not in ("Succeeded", "Failed"):
            _update_job_status(
                stats_client, job_id, JobStatus.failed, error="Pod deleted unexpectedly", error_type="pod_deleted"
            )
            logger.warning(f"Job {job_id} failed: pod {pod_name} deleted unexpectedly (phase={phase})")


def _process_batch(
    stats_client: StatsClient,
    core_v1: client.CoreV1Api,
    batch_v1: client.BatchV1Api,
) -> int:
    """Process a batch of events. Returns the number of events processed."""
    engine = _get_db_engine()
    with Session(engine, expire_on_commit=False) as session:
        events = _fetch_unprocessed_events(session)
        if not events:
            return 0

        processed_count = 0
        for event in events:
            try:
                _process_event(stats_client, core_v1, batch_v1, event)
                _mark_processed(session, event)
                processed_count += 1
            except Exception:
                logger.error(f"Failed to process event {event.id}", exc_info=True)
                # Don't mark as processed - will retry on next batch

        return processed_count


def _get_job_info(pod: client.V1Pod) -> tuple[UUID, str] | None:
    """Extract job ID and pod name from pod labels."""
    if not pod.metadata or not pod.metadata.labels:
        return None
    job_id_str = pod.metadata.labels.get(LABEL_JOB_ID)
    if not job_id_str:
        return None
    return UUID(job_id_str), pod.metadata.name or "unknown"


@trace("tournament.job.reconcile")
def _reconcile_stale_jobs(stats_client: StatsClient, core_v1: client.CoreV1Api):
    """
    Reconcile jobs that are marked running/dispatched but have no active pod.

    This handles cases where pod terminal events were missed by the watcher
    (e.g., watcher downtime, watch stream disconnection).
    """
    cfg = get_dispatch_config()
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

    now = datetime.now(UTC)
    stale_count = 0
    completed_count = 0
    skipped_count = 0
    for job in running_jobs:
        if job.id not in active_job_ids:
            if job.completed_at or job.result:
                logger.info(f"Reconciliation: job {job.id} has results but status={job.status}, marking completed")
                _update_job_status(stats_client, job.id, JobStatus.completed)
                completed_count += 1
            else:
                ref_time = job.dispatched_at or job.created_at
                if ref_time and (now - ref_time).total_seconds() < RECONCILE_GRACE_PERIOD_SECONDS:
                    skipped_count += 1
                    continue
                logger.warning(f"Reconciliation: job {job.id} marked {job.status} but no pod found, marking failed")
                _update_job_status(
                    stats_client,
                    job.id,
                    JobStatus.failed,
                    error="Pod not found (reconciliation)",
                    error_type="pod_not_found",
                )
                stale_count += 1

    if stale_count > 0 or completed_count > 0 or skipped_count > 0:
        logger.info(
            f"Reconciliation: {completed_count} completed, {stale_count} failed, {skipped_count} skipped (grace)"
        )


def run_event_processor():
    cfg = get_dispatch_config()
    start_health_server()

    stats_client = StatsClient(backend_url=cfg.STATS_SERVER_URI, machine_token=cfg.MACHINE_TOKEN)
    stats_client._validate_authenticated()
    logger.info(f"Event processor started: stats_server_uri={cfg.STATS_SERVER_URI}")

    last_reconcile = time.monotonic()

    try:
        while True:
            update_heartbeat()
            try:
                clients = _get_k8s_clients()
                if clients is None:
                    logger.warning("Eval cluster clients unavailable, retrying in 30s")
                    time.sleep(30)
                    continue
                core_v1, batch_v1 = clients

                # Process stored events
                processed = _process_batch(stats_client, core_v1, batch_v1)
                if processed > 0:
                    logger.info(f"Processed {processed} events")
                else:
                    time.sleep(POLL_INTERVAL_SECONDS)

                # Periodic reconciliation for missed events
                now = time.monotonic()
                if now - last_reconcile >= RECONCILE_INTERVAL_SECONDS:
                    _reconcile_stale_jobs(stats_client, core_v1)
                    last_reconcile = now

            except Exception as e:
                logger.error(f"Event processor error: {e}", exc_info=True)
                time.sleep(POLL_INTERVAL_SECONDS)
    finally:
        stats_client.close()


if __name__ == "__main__":
    init_logging()
    suppress_noisy_logs()
    init_otel_tracing(service_name="k8s-event-processor")
    run_event_processor()
