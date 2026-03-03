"""Unit tests for EventCtx parsing, phase dispatch, and individual handlers."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

from metta.app_backend.job_runner.event_processor import (
    EventCtx,
    _fetch_job_if_actionable,
    _handle_pod_deleted,
    _handle_pod_running,
    _process_event,
)
from metta.app_backend.models.job_request import JobRequest, JobStatus, JobType
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
    extra_labels: dict | None = None,
) -> dict:
    """Build a minimal K8s watch-event dict with overridable fields."""
    labels = {"job-id": job_id}
    if extra_labels:
        labels.update(extra_labels)

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
            "metadata": {
                "name": pod_name,
                "labels": labels,
                "ownerReferences": owner_refs,
            },
            "status": status,
        },
    }


# ---------------------------------------------------------------------------
# EventCtx.parse
# ---------------------------------------------------------------------------


class TestEventCtxParse:
    def test_parse_valid_event(self):
        ev = _make_event(phase="Succeeded", container_running=True)
        ctx = EventCtx.parse(ev)
        assert ctx is not None
        assert ctx.event_type == "MODIFIED"
        assert ctx.phase == "Succeeded"
        assert ctx.job_id == UUID(_JOB_ID)
        assert ctx.pod_name == "test-pod-0"
        assert ctx.job_name == "job-test-pod-0"
        assert ctx.container_running is True

    def test_parse_missing_job_id_returns_none(self):
        ev = _make_event()
        ev["object"]["metadata"]["labels"] = {}
        assert EventCtx.parse(ev) is None

    def test_parse_invalid_uuid_returns_none(self):
        ev = _make_event(job_id="not-a-uuid")
        assert EventCtx.parse(ev) is None

    def test_parse_missing_status_yields_none_phase(self):
        ev = _make_event()
        del ev["object"]["status"]
        ctx = EventCtx.parse(ev)
        assert ctx is not None
        assert ctx.phase is None

    def test_parse_no_owner_references_yields_none_job_name(self):
        ev = _make_event(job_name=None)
        ctx = EventCtx.parse(ev)
        assert ctx is not None
        assert ctx.job_name is None

    def test_parse_container_running_true(self):
        ev = _make_event(container_running=True)
        ctx = EventCtx.parse(ev)
        assert ctx is not None
        assert ctx.container_running is True

    def test_parse_container_not_running(self):
        ev = _make_event(container_running=False)
        ctx = EventCtx.parse(ev)
        assert ctx is not None
        assert ctx.container_running is False


# ---------------------------------------------------------------------------
# _process_event dispatch
# ---------------------------------------------------------------------------


def _make_k8s_event(event_dict: dict) -> K8sEvent:
    return K8sEvent(cluster="test", event_time=datetime.now(UTC), event=event_dict)


def _stub_clients():
    stats = MagicMock()
    core_v1 = MagicMock()
    batch_v1 = MagicMock()
    return stats, core_v1, batch_v1


class TestProcessEventDispatch:
    def test_dispatch_added_succeeded(self):
        sentinel = MagicMock()
        with patch.dict(
            "metta.app_backend.job_runner.event_processor._PHASE_HANDLERS",
            {"Succeeded": sentinel},
        ):
            ev = _make_event(event_type="ADDED", phase="Succeeded")
            stats, core_v1, batch_v1 = _stub_clients()
            _process_event(stats, core_v1, batch_v1, _make_k8s_event(ev))
            sentinel.assert_called_once()

    def test_dispatch_modified_running(self):
        sentinel = MagicMock()
        with patch.dict(
            "metta.app_backend.job_runner.event_processor._PHASE_HANDLERS",
            {"Running": sentinel},
        ):
            ev = _make_event(event_type="MODIFIED", phase="Running")
            stats, core_v1, batch_v1 = _stub_clients()
            _process_event(stats, core_v1, batch_v1, _make_k8s_event(ev))
            sentinel.assert_called_once()

    def test_dispatch_deleted(self):
        with patch("metta.app_backend.job_runner.event_processor._handle_pod_deleted") as mock_del:
            ev = _make_event(event_type="DELETED", phase="Running")
            stats, core_v1, batch_v1 = _stub_clients()
            _process_event(stats, core_v1, batch_v1, _make_k8s_event(ev))
            mock_del.assert_called_once()

    def test_dispatch_unknown_phase_noop(self):
        """Phase='Pending' has no handler — should be a no-op."""
        with (
            patch.dict(
                "metta.app_backend.job_runner.event_processor._PHASE_HANDLERS",
                {"Succeeded": MagicMock(), "Failed": MagicMock(), "Running": MagicMock()},
                clear=True,
            ),
            patch("metta.app_backend.job_runner.event_processor._handle_pod_deleted") as mock_del,
        ):
            ev = _make_event(event_type="MODIFIED", phase="Pending")
            stats, core_v1, batch_v1 = _stub_clients()
            _process_event(stats, core_v1, batch_v1, _make_k8s_event(ev))
            mock_del.assert_not_called()


# ---------------------------------------------------------------------------
# _fetch_job_if_actionable
# ---------------------------------------------------------------------------


class TestFetchJobIfActionable:
    def _make_job_request(self, status: JobStatus) -> JobRequest:
        return JobRequest(
            id=uuid4(),
            job={"type": "single_episode", "policy_uris": ["s3://b/p"], "assignments": [0], "env": {"name": "t"}},
            status=status,
            job_type=JobType.episode,
            user_id="u",
        )

    def test_terminal_completed_returns_none(self):
        stats = MagicMock()
        stats.get_job.return_value = self._make_job_request(JobStatus.completed)
        ctx = EventCtx.parse(_make_event(phase="Succeeded"))
        assert ctx is not None

        result = _fetch_job_if_actionable(stats, ctx)
        assert result is None

    def test_terminal_failed_returns_none(self):
        stats = MagicMock()
        stats.get_job.return_value = self._make_job_request(JobStatus.failed)
        ctx = EventCtx.parse(_make_event(phase="Failed"))
        assert ctx is not None

        result = _fetch_job_if_actionable(stats, ctx)
        assert result is None

    def test_non_terminal_returns_job_request(self):
        stats = MagicMock()
        job_req = self._make_job_request(JobStatus.running)
        stats.get_job.return_value = job_req
        ctx = EventCtx.parse(_make_event(phase="Running"))
        assert ctx is not None

        result = _fetch_job_if_actionable(stats, ctx)
        assert result is job_req


# ---------------------------------------------------------------------------
# _handle_pod_running
# ---------------------------------------------------------------------------


class TestHandlePodRunning:
    def test_running_updates_when_container_running(self):
        stats, core_v1, batch_v1 = _stub_clients()
        ev = _make_event(container_running=True, phase="Running")
        ctx = EventCtx.parse(ev)
        assert ctx is not None

        with patch("metta.app_backend.job_runner.event_processor._update_job_status") as mock_update:
            _handle_pod_running(stats, core_v1, batch_v1, ctx, ev)
            mock_update.assert_called_once_with(stats, ctx.job_id, JobStatus.running, worker=ctx.pod_name)

    def test_running_skips_when_not_running(self):
        stats, core_v1, batch_v1 = _stub_clients()
        ev = _make_event(container_running=False, phase="Running")
        ctx = EventCtx.parse(ev)
        assert ctx is not None

        with patch("metta.app_backend.job_runner.event_processor._update_job_status") as mock_update:
            _handle_pod_running(stats, core_v1, batch_v1, ctx, ev)
            mock_update.assert_not_called()


# ---------------------------------------------------------------------------
# _handle_pod_deleted
# ---------------------------------------------------------------------------


class TestHandlePodDeleted:
    def test_deleted_marks_failed_non_terminal_phase(self):
        stats, core_v1, batch_v1 = _stub_clients()
        ev = _make_event(event_type="DELETED", phase="Running")
        ctx = EventCtx.parse(ev)
        assert ctx is not None

        with patch("metta.app_backend.job_runner.event_processor._update_job_status") as mock_update:
            _handle_pod_deleted(stats, core_v1, batch_v1, ctx, ev)
            mock_update.assert_called_once()
            assert mock_update.call_args[0][2] == JobStatus.failed

    def test_deleted_skips_terminal_phase(self):
        stats, core_v1, batch_v1 = _stub_clients()
        ev = _make_event(event_type="DELETED", phase="Succeeded")
        ctx = EventCtx.parse(ev)
        assert ctx is not None

        with patch("metta.app_backend.job_runner.event_processor._update_job_status") as mock_update:
            _handle_pod_deleted(stats, core_v1, batch_v1, ctx, ev)
            mock_update.assert_not_called()
