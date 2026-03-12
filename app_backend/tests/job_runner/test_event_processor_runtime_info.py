from datetime import UTC, datetime
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

from metta.app_backend.job_runner.event_processor import _process_event
from metta.app_backend.models.job_request import JobRequest, JobStatus, JobType
from metta.app_backend.models.k8s_events import K8sEvent
from mettagrid.runner.types import PureSingleEpisodeResult, RuntimeInfo

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


def _succeeded_event(job_id: UUID) -> K8sEvent:
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
                    "phase": "Succeeded",
                    "containerStatuses": [{"image": RUNNER_IMAGE, "imageID": RUNNER_IMAGE_ID}],
                },
            },
        },
    )


def test_failed_event_updates_job_with_runtime_info() -> None:
    job_id = uuid4()
    job = JobRequest(
        id=job_id,
        job={"policy_uris": ["mock://random"], "assignments": [0], "env": {"game": {"num_agents": 1}}},
        status=JobStatus.running,
        job_type=JobType.episode,
        user_id="test-user",
    )

    result_capture: dict = {}

    def _mock_update_job_status(jid, status, error=None, error_type=None, worker=None, result=None):
        if jid == job_id:
            job.status = status
            if error is not None:
                job.error = error
            if result is not None:
                result_capture.update(result)

    core_v1 = MagicMock()
    batch_v1 = MagicMock()

    with (
        patch("metta.app_backend.job_runner.event_processor._fetch_job_if_actionable", return_value=job),
        patch("metta.app_backend.job_runner.event_processor._update_job_status", side_effect=_mock_update_job_status),
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
        _process_event(core_v1, batch_v1, _failed_event(job_id))

    assert job.status == JobStatus.failed
    assert result_capture["runner_image"] == RUNNER_IMAGE
    assert result_capture["runner_image_id"] == RUNNER_IMAGE_ID
    assert result_capture["instance_type"] == "m5.xlarge"
    assert result_capture["git_commit"] == "abc123"
    assert result_capture["cogames_version"] == "0.5.0"


def test_succeeded_event_marks_failed_when_episode_recording_fails() -> None:
    job_id = uuid4()
    job = JobRequest(
        id=job_id,
        job={"policy_uris": ["metta://policy/a"], "assignments": [0], "env": {"game": {"num_agents": 1}}},
        status=JobStatus.running,
        job_type=JobType.episode,
        user_id="test-user",
    )

    updates: list[dict] = []

    def _mock_update_job_status(jid, status, error=None, error_type=None, worker=None, result=None):
        if jid == job_id:
            updates.append(
                {
                    "status": status,
                    "error": error,
                    "error_type": error_type,
                    "worker": worker,
                    "result": result,
                }
            )
            job.status = status
            job.error = error
            job.error_type = error_type
            if result is not None:
                job.result = result

    core_v1 = MagicMock()
    batch_v1 = MagicMock()
    results = PureSingleEpisodeResult(
        rewards=[1.0],
        action_timeouts=[0],
        stats={"game": {}, "agent": [{}]},
        steps=3,
    )

    with (
        patch("metta.app_backend.job_runner.event_processor._fetch_job_if_actionable", return_value=job),
        patch("metta.app_backend.job_runner.event_processor._update_job_status", side_effect=_mock_update_job_status),
        patch("metta.app_backend.job_runner.event_processor._read_results_with_retry", return_value=(results, None)),
        patch(
            "metta.app_backend.job_runner.event_processor._build_result_metadata",
            return_value={"runner_image": RUNNER_IMAGE},
        ),
        patch("metta.app_backend.job_runner.event_processor.record_job_episode", side_effect=ValueError("boom")),
        patch("metta.app_backend.job_runner.event_processor.copy_replay_to_public"),
        patch("metta.app_backend.job_runner.event_processor.capture_pod_logs"),
        patch("metta.app_backend.job_runner.event_processor._delete_k8s_job"),
    ):
        _process_event(core_v1, batch_v1, _succeeded_event(job_id))

    assert len(updates) == 1
    assert updates[0]["status"] == JobStatus.failed
    assert updates[0]["error_type"] == "result_error"
    assert updates[0]["error"] == "Episode recording failed: boom"
    assert updates[0]["result"] == {"runner_image": RUNNER_IMAGE}
