from datetime import UTC, datetime
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

from metta.app_backend.job_runner.event_processor import _process_event
from metta.app_backend.models.job_request import JobRequest, JobStatus, JobType
from metta.app_backend.models.k8s_events import K8sEvent
from mettagrid.runner.types import RuntimeInfo

RUNNER_IMAGE = "ghcr.io/metta-ai/episode-runner:compat-v0.5"
RUNNER_IMAGE_ID = "ghcr.io/metta-ai/episode-runner@sha256:abc123"


def _failed_event(job_id: UUID) -> K8sEvent:
    return K8sEvent(
        cluster="test",
        event_time=datetime.now(UTC),
        event={
            "type": "MODIFIED",
            "object": {
                "metadata": {
                    "name": f"pod-{job_id.hex[:8]}",
                    "labels": {"app": "episode-runner", "job-id": str(job_id)},
                    "ownerReferences": [{"kind": "Job", "name": f"job-{job_id.hex[:8]}"}],
                },
                "status": {
                    "phase": "Failed",
                    "containerStatuses": [{"image": RUNNER_IMAGE, "imageID": RUNNER_IMAGE_ID}],
                },
            },
        },
    )


def test_failed_event_updates_job_with_runtime_info() -> None:
    job_id = uuid4()
    stats_client = MagicMock()
    job = JobRequest(
        id=job_id,
        job={"policy_uris": ["mock://random"], "assignments": [0], "env": {"game": {"num_agents": 1}}},
        status=JobStatus.running,
        job_type=JobType.episode,
        user_id="test-user",
    )
    stats_client.get_job.return_value = job

    def _apply_update(update_job_id: UUID, update) -> None:
        assert update_job_id == job_id
        if update.status is not None:
            job.status = update.status
        if update.error is not None:
            job.error = update.error
        if update.result is not None:
            job.result = update.result

    stats_client.update_job.side_effect = _apply_update

    core_v1 = MagicMock()
    batch_v1 = MagicMock()

    with (
        patch("metta.app_backend.job_runner.event_processor.capture_pod_logs"),
        patch("metta.app_backend.job_runner.event_processor._read_runner_error", return_value=None),
        patch("metta.app_backend.job_runner.event_processor._extract_error_from_logs_with_retry", return_value="boom"),
        patch("metta.app_backend.job_runner.event_processor._get_pod_error_from_event", return_value="Pod failed"),
        patch(
            "metta.app_backend.job_runner.event_processor._get_node_pricing_info",
            return_value={"instance_type": "m5.xlarge"},
        ),
        patch(
            "metta.app_backend.job_runner.event_processor._read_runtime_info",
            return_value=RuntimeInfo(git_commit="abc123", cogames_version="0.5.0"),
        ),
        patch("metta.app_backend.job_runner.event_processor._delete_k8s_job"),
    ):
        _process_event(stats_client, core_v1, batch_v1, _failed_event(job_id))

    assert job.status == JobStatus.failed
    assert isinstance(job.result, dict)
    assert job.result["runner_image"] == RUNNER_IMAGE
    assert job.result["runner_image_id"] == RUNNER_IMAGE_ID
    assert job.result["instance_type"] == "m5.xlarge"
    assert job.result["git_commit"] == "abc123"
    assert job.result["cogames_version"] == "0.5.0"
