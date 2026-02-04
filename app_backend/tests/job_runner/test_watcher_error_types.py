"""Test that lifecycle error types are correctly set in watcher."""

from unittest.mock import MagicMock
from uuid import uuid4

from metta.app_backend.job_runner.watcher import _update_job_status
from metta.app_backend.models.job_request import JobStatus


def test_pod_not_found_error_type():
    """Test that reconciliation failures use pod_not_found error type."""
    stats_client = MagicMock()
    job_id = uuid4()

    _update_job_status(
        stats_client, job_id, JobStatus.failed, error="Pod not found (reconciliation)", error_type="pod_not_found"
    )

    # Verify the update_job was called with correct error_type
    stats_client.update_job.assert_called_once()
    call_args = stats_client.update_job.call_args
    assert call_args[0][0] == job_id
    update = call_args[0][1]
    assert update.status == JobStatus.failed
    assert update.error == "Pod not found (reconciliation)"
    assert update.error_type == "pod_not_found"


def test_pod_deleted_error_type():
    """Test that unexpected pod deletions use pod_deleted error type."""
    stats_client = MagicMock()
    job_id = uuid4()

    _update_job_status(
        stats_client, job_id, JobStatus.failed, error="Pod deleted unexpectedly", error_type="pod_deleted"
    )

    # Verify the update_job was called with correct error_type
    stats_client.update_job.assert_called_once()
    call_args = stats_client.update_job.call_args
    assert call_args[0][0] == job_id
    update = call_args[0][1]
    assert update.status == JobStatus.failed
    assert update.error == "Pod deleted unexpectedly"
    assert update.error_type == "pod_deleted"


def test_error_types_are_distinct():
    """Verify the new error types are distinct from 'unknown'."""
    # This test documents that we've moved away from generic 'unknown' errors
    # for specific lifecycle failures that we can now track separately
    lifecycle_error_types = ["pod_not_found", "pod_deleted", "result_missing", "result_error"]
    runtime_error_types = ["policy_error", "timeout", "oom", "unknown"]

    # Ensure no overlap
    assert set(lifecycle_error_types).isdisjoint(set(runtime_error_types))

    # Ensure we're not using 'unknown' for lifecycle errors anymore
    assert "unknown" not in lifecycle_error_types
