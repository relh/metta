from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

from metta.app_backend.job_runner.event_processor import (
    EventCtx,
    _get_unprocessed_backlog_stats,
    _group_by_job,
    _handle_pod_deleted,
    _handle_pod_running,
    _pick_winner,
    _process_batch,
    _refresh_backlog_metrics_best_effort,
    _update_backlog_metrics,
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


class TestUnprocessedBacklogStats:
    def test_backlog_stats_empty(self):
        mock_session = MagicMock()
        mock_session.exec.return_value.one.return_value = (0, None)

        with (
            patch("metta.app_backend.job_runner.event_processor._get_db_engine"),
            patch("metta.app_backend.job_runner.event_processor.Session") as mock_session_cls,
        ):
            mock_session_cls.return_value.__enter__.return_value = mock_session
            count, oldest_age_seconds = _get_unprocessed_backlog_stats()

        assert count == 0
        assert oldest_age_seconds == 0.0

    def test_backlog_stats_returns_oldest_age(self):
        now = datetime.now(UTC)
        mock_session = MagicMock()
        mock_session.exec.return_value.one.return_value = (3, now - timedelta(seconds=30))

        with (
            patch("metta.app_backend.job_runner.event_processor._get_db_engine"),
            patch("metta.app_backend.job_runner.event_processor.Session") as mock_session_cls,
        ):
            mock_session_cls.return_value.__enter__.return_value = mock_session
            count, oldest_age_seconds = _get_unprocessed_backlog_stats()

        assert count == 3
        assert oldest_age_seconds >= 25.0


class TestUpdateBacklogMetrics:
    def test_updates_metrics_from_db_snapshot(self):
        mock_metrics = MagicMock()

        with (
            patch(
                "metta.app_backend.job_runner.event_processor.get_event_processor_metrics", return_value=mock_metrics
            ),
            patch(
                "metta.app_backend.job_runner.event_processor._get_unprocessed_backlog_stats", return_value=(7, 42.0)
            ),
        ):
            _update_backlog_metrics()

            mock_metrics.update_backlog.assert_called_once_with(7, 42.0)


class TestRefreshBacklogMetricsBestEffort:
    def test_calls_update_when_successful(self):
        with patch("metta.app_backend.job_runner.event_processor._update_backlog_metrics") as mock_update:
            _refresh_backlog_metrics_best_effort()
            mock_update.assert_called_once()

    def test_logs_warning_when_update_fails(self):
        with (
            patch(
                "metta.app_backend.job_runner.event_processor._update_backlog_metrics",
                side_effect=RuntimeError("boom"),
            ),
            patch("metta.app_backend.job_runner.event_processor.logger.warning") as mock_warning,
        ):
            _refresh_backlog_metrics_best_effort()
            mock_warning.assert_called_once()


class TestProcessBatch:
    def test_refreshes_backlog_metrics_best_effort_after_marking_processed(self):
        mock_engine = object()
        mock_executor = MagicMock()
        mock_session = MagicMock()
        event = _make_k8s_event({"type": "MODIFIED", "object": {"metadata": {"name": "x", "labels": {}}, "status": {}}})
        event.id = 123

        with (
            patch("metta.app_backend.job_runner.event_processor._get_db_engine", return_value=mock_engine),
            patch("metta.app_backend.job_runner.event_processor.Session") as mock_session_cls,
            patch("metta.app_backend.job_runner.event_processor._fetch_unprocessed_events", return_value=[event]),
            patch("metta.app_backend.job_runner.event_processor._mark_processed_batch") as mock_mark_processed_batch,
            patch(
                "metta.app_backend.job_runner.event_processor._refresh_backlog_metrics_best_effort"
            ) as mock_refresh_backlog_metrics,
        ):
            mock_session_cls.return_value.__enter__.return_value = mock_session

            processed = _process_batch(mock_executor, MagicMock())

            assert processed == 1
            mock_mark_processed_batch.assert_called_once_with(mock_engine, [123])
            mock_refresh_backlog_metrics.assert_called_once_with()
