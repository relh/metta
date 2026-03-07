from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from metta.app_backend.job_runner.event_processor import _reconcile_stale_jobs
from metta.app_backend.models.job_request import JobStatus


def test_reconcile_handles_naive_job_timestamps():
    core_v1 = MagicMock()
    core_v1.list_namespaced_pod.return_value = SimpleNamespace(items=[])

    job = SimpleNamespace(
        id=uuid4(),
        status=JobStatus.dispatched,
        completed_at=None,
        result=None,
        dispatched_at=None,
        created_at=datetime.now(UTC).replace(tzinfo=None),
    )

    with (
        patch("metta.app_backend.job_runner.event_processor.list_jobs_by_status", return_value=[job]),
        patch("metta.app_backend.job_runner.event_processor._update_job_status") as mock_update,
    ):
        _reconcile_stale_jobs(core_v1)

    mock_update.assert_not_called()
