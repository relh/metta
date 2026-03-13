"""OTel metrics for k8s event processor backlog health."""

from collections.abc import Iterable
from functools import lru_cache

from opentelemetry import metrics as otel_metrics
from opentelemetry.metrics import CallbackOptions, Observation

from metta.app_backend.otel.metrics import init_meter_provider


class EventProcessorMetrics:
    def __init__(self) -> None:
        init_meter_provider()
        meter = otel_metrics.get_meter(__name__)
        self._unprocessed_count = 0
        self._oldest_unprocessed_age_seconds = 0.0
        meter.create_observable_gauge(
            "k8s_event.unprocessed_count",
            callbacks=[self._observe_unprocessed_count],
            description="Number of unprocessed k8s events in the backlog",
            unit="1",
        )
        meter.create_observable_gauge(
            "k8s_event.unprocessed_oldest_age_seconds",
            callbacks=[self._observe_oldest_unprocessed_age_seconds],
            description="Age in seconds of the oldest unprocessed k8s event",
            unit="s",
        )

    def _observe_unprocessed_count(self, _options: CallbackOptions) -> Iterable[Observation]:
        return [Observation(self._unprocessed_count)]

    def _observe_oldest_unprocessed_age_seconds(self, _options: CallbackOptions) -> Iterable[Observation]:
        return [Observation(self._oldest_unprocessed_age_seconds)]

    def update_backlog(self, unprocessed_count: int, oldest_unprocessed_age_seconds: float) -> None:
        self._unprocessed_count = max(unprocessed_count, 0)
        self._oldest_unprocessed_age_seconds = max(oldest_unprocessed_age_seconds, 0.0)


@lru_cache
def get_event_processor_metrics() -> EventProcessorMetrics:
    return EventProcessorMetrics()
