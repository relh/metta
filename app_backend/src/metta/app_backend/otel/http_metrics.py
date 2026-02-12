"""ASGI middleware that records per-route HTTP request metrics via OpenTelemetry."""

import time

from opentelemetry import metrics as otel_metrics
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class HttpMetricsMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        meter = otel_metrics.get_meter("http")
        self._duration = meter.create_histogram(
            "http.server.request.duration",
            description="HTTP request duration",
            unit="s",
        )
        self._count = meter.create_counter(
            "http.server.request.count",
            description="HTTP request count",
            unit="1",
        )

    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration = time.perf_counter() - start
            route = request.scope.get("route")
            route_path = route.path if route else "<unmatched>"
            attrs = {
                "http.method": request.method,
                "http.route": route_path,
                "http.status_code": status_code,
            }
            self._duration.record(duration, attributes=attrs)
            self._count.add(1, attributes=attrs)
