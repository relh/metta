from datetime import UTC, datetime
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

from metta.app_backend.job_runner.event_processor import (
    EventCtx,
    _group_by_job,
    _handle_pod_deleted,
    _handle_pod_running,
    _pick_winner,
)
from metta.app_backend.models.job_request import JobStatus
from metta.app_backend.models.k8s_events import K8sEvent

_JOB_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def _make_event(
    *,
    event_type: str = "MODIFIED",
    phase: str | None = "Running",
    job_id: str = _JOB_ID,
    pod_name: str = "test-pod-0",
    job_name: str | None = "job-test-pod-0",
    container_running: bool = False,
) -> dict:
    labels = {"job-id": job_id}
    owner_refs = [{"kind": "Job", "name": job_name}] if job_name else []
    container_state = (
        {"running": {"startedAt": "2024-01-01T00:00:00Z"}}
        if container_running
        else {"waiting": {"reason": "ContainerCreating"}}
    )
    container_statuses = [{"state": container_state, "image": "img:latest", "imageID": "sha256:abc"}]
    status: dict = {"containerStatuses": container_statuses}
    if phase is not None:
        status["phase"] = phase
    return {
        "type": event_type,
        "object": {
            "metadata": {"name": pod_name, "labels": labels, "ownerReferences": owner_refs},
            "status": status,
        },
    }


def _make_k8s_event(event_dict: dict) -> K8sEvent:
    return K8sEvent(cluster="test", event_time=datetime.now(UTC), event=event_dict)


class TestGroupByJob:
    def test_groups_events_by_job_id(self):
        job_a, job_b = str(uuid4()), str(uuid4())
        events = [
            _make_k8s_event(_make_event(job_id=job_a, phase="Running")),
            _make_k8s_event(_make_event(job_id=job_b, phase="Failed")),
            _make_k8s_event(_make_event(job_id=job_a, phase="Succeeded")),
        ]
        groups, unparseable = _group_by_job(events)
        assert len(groups) == 2
        assert len(groups[UUID(job_a)]) == 2
        assert len(groups[UUID(job_b)]) == 1
        assert unparseable == []

    def test_unparseable_events_separated(self):
        good = _make_k8s_event(_make_event(job_id=_JOB_ID, phase="Running"))
        bad = _make_k8s_event({"type": "MODIFIED", "object": {"metadata": {"name": "x", "labels": {}}, "status": {}}})
        groups, unparseable = _group_by_job([good, bad])
        assert len(groups) == 1
        assert len(unparseable) == 1


class TestPickWinner:
    def test_picks_most_terminal_event(self):
        job_id = str(uuid4())
        running = _make_k8s_event(_make_event(job_id=job_id, phase="Running"))
        succeeded = _make_k8s_event(_make_event(job_id=job_id, phase="Succeeded"))
        failed = _make_k8s_event(_make_event(job_id=job_id, phase="Failed"))
        winner = _pick_winner([running, failed, succeeded])
        ctx = EventCtx.parse(winner.event)
        assert ctx is not None
        assert ctx.phase == "Succeeded"

    def test_single_event_returns_itself(self):
        event = _make_k8s_event(_make_event(phase="Running"))
        assert _pick_winner([event]) is event


class TestHandlePodRunning:
    @patch("metta.app_backend.job_runner.event_processor._update_job_status")
    def test_running_updates_when_container_running(self, mock_update):
        core_v1 = MagicMock()
        batch_v1 = MagicMock()

        ev = _make_event(container_running=True, phase="Running")
        ctx = EventCtx.parse(ev)
        assert ctx is not None

        _handle_pod_running(core_v1, batch_v1, ctx, ev)
        mock_update.assert_called_once()
        called_worker = mock_update.call_args[1].get("worker") == ctx.pod_name
        assert called_worker or mock_update.call_args[0][1] == JobStatus.running

    def test_running_skips_when_not_running(self):
        core_v1 = MagicMock()
        batch_v1 = MagicMock()
        ev = _make_event(container_running=False, phase="Running")
        ctx = EventCtx.parse(ev)
        assert ctx is not None

        with patch("metta.app_backend.job_runner.event_processor._update_job_status") as mock_update:
            _handle_pod_running(core_v1, batch_v1, ctx, ev)
            mock_update.assert_not_called()


class TestHandlePodDeleted:
    @patch("metta.app_backend.job_runner.event_processor._update_job_status")
    def test_deleted_marks_failed_non_terminal_phase(self, mock_update):
        core_v1 = MagicMock()
        batch_v1 = MagicMock()

        ev = _make_event(event_type="DELETED", phase="Running")
        ctx = EventCtx.parse(ev)
        assert ctx is not None

        _handle_pod_deleted(core_v1, batch_v1, ctx, ev)
        mock_update.assert_called_once()

    def test_deleted_skips_terminal_phase(self):
        core_v1 = MagicMock()
        batch_v1 = MagicMock()
        ev = _make_event(event_type="DELETED", phase="Succeeded")
        ctx = EventCtx.parse(ev)
        assert ctx is not None

        with patch("metta.app_backend.job_runner.event_processor._update_job_status") as mock_update:
            _handle_pod_deleted(core_v1, batch_v1, ctx, ev)
            mock_update.assert_not_called()
