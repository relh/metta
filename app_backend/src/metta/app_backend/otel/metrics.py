"""OTel configuration"""

from functools import lru_cache
from typing import Optional

from opentelemetry import metrics as otel_metrics
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.metrics import Counter, Histogram, MeterProvider
from opentelemetry.sdk.metrics.export import (
    AggregationTemporality,
    ConsoleMetricExporter,
    PeriodicExportingMetricReader,
)
from opentelemetry.sdk.metrics.view import ExplicitBucketHistogramAggregation, View
from opentelemetry.sdk.resources import Resource
from pydantic_settings import BaseSettings

METRICS_SERVICE_NAME = "observatory-backend"


class MetricsSettings(BaseSettings):
    OTEL_EXPORTER_OTLP_ENDPOINT: Optional[str] = None
    OTEL_METRICS_CONSOLE: bool = False


@lru_cache
def init_meter_provider() -> None:
    """Set the global OTel MeterProvider if any metric export is configured. Idempotent."""
    settings = MetricsSettings()
    readers: list[PeriodicExportingMetricReader] = []

    if settings.OTEL_EXPORTER_OTLP_ENDPOINT:
        otlp_exporter = OTLPMetricExporter(
            preferred_temporality={
                Counter: AggregationTemporality.DELTA,
                Histogram: AggregationTemporality.DELTA,
            },
        )
        readers.append(PeriodicExportingMetricReader(otlp_exporter))

    if settings.OTEL_METRICS_CONSOLE:
        readers.append(PeriodicExportingMetricReader(ConsoleMetricExporter(), export_interval_millis=5000))

    if not readers:
        return

    # Sub-second buckets for HTTP latency: 1ms to 30s
    http_duration_view = View(
        instrument_name="http.server.request.duration",
        aggregation=ExplicitBucketHistogramAggregation(
            boundaries=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0]
        ),
    )

    resource = Resource.create({"service.name": METRICS_SERVICE_NAME})
    provider = MeterProvider(resource=resource, metric_readers=readers, views=[http_duration_view])
    otel_metrics.set_meter_provider(provider)
