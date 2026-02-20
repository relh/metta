from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from metta.app_backend.job_runner.event_processor import _reconcile_stale_jobs
from metta.app_backend.models.job_request import JobStatus


def test_reconcile_handles_naive_job_timestamps():
    stats_client = MagicMock()
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
    stats_client.list_jobs.return_value = [job]

    _reconcile_stale_jobs(stats_client, core_v1)

    stats_client.update_job.assert_not_called()
