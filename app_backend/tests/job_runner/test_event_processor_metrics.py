from unittest.mock import MagicMock

from metta.app_backend.otel.event_processor_metrics import EventProcessorMetrics


def test_update_backlog_clamps_negative_values() -> None:
    metrics = EventProcessorMetrics()

    metrics.update_backlog(-3, -7.5)

    assert metrics._unprocessed_count == 0
    assert metrics._oldest_unprocessed_age_seconds == 0.0


def test_observers_return_updated_snapshot_values() -> None:
    metrics = EventProcessorMetrics()
    metrics.update_backlog(12, 34.5)

    count_observations = list(metrics._observe_unprocessed_count(MagicMock()))
    age_observations = list(metrics._observe_oldest_unprocessed_age_seconds(MagicMock()))

    assert len(count_observations) == 1
    assert len(age_observations) == 1
    assert count_observations[0].value == 12
    assert age_observations[0].value == 34.5
