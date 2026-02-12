"""Tests for HttpMetricsMiddleware."""

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from metta.app_backend.otel.http_metrics import HttpMetricsMiddleware

# Captured metric recordings, filled by _InstrumentedMiddleware
_recorded: list[dict] = []


class _InstrumentedMiddleware(HttpMetricsMiddleware):
    """Subclass that captures metric recordings for testing."""

    async def dispatch(self, request, call_next):
        _recorded.clear()

        # Patch instruments to capture calls
        orig_record = self._duration.record
        orig_add = self._count.add

        def capture_record(amount, attributes=None, context=None):
            _recorded.append({"instrument": "duration", "value": amount, "attributes": attributes})
            orig_record(amount, attributes=attributes, context=context)

        def capture_add(amount, attributes=None, context=None):
            _recorded.append({"instrument": "count", "value": amount, "attributes": attributes})
            orig_add(amount, attributes=attributes, context=context)

        self._duration.record = capture_record  # type: ignore[assignment]
        self._count.add = capture_add  # type: ignore[assignment]
        try:
            return await super().dispatch(request, call_next)
        finally:
            self._duration.record = orig_record  # type: ignore[assignment]
            self._count.add = orig_add  # type: ignore[assignment]


def _make_app() -> Starlette:
    async def ok(request: Request) -> PlainTextResponse:
        return PlainTextResponse("ok")

    async def fail(request: Request) -> PlainTextResponse:
        raise RuntimeError("boom")

    app = Starlette(routes=[Route("/ok", ok), Route("/fail", fail)])
    app.add_middleware(_InstrumentedMiddleware)
    return app


def test_http_metrics_records_on_exception_regression():
    """Regression: unhandled exceptions must still record duration and count.

    If call_next raises, metrics should be recorded with status_code=500
    so error traffic shows up in dashboards.
    """
    client = TestClient(_make_app(), raise_server_exceptions=False)

    response = client.get("/fail")
    assert response.status_code == 500

    duration_recs = [r for r in _recorded if r["instrument"] == "duration"]
    count_recs = [r for r in _recorded if r["instrument"] == "count"]

    assert len(duration_recs) == 1, f"Expected 1 duration recording, got {len(duration_recs)}"
    assert duration_recs[0]["attributes"]["http.status_code"] == 500
    assert len(count_recs) == 1, f"Expected 1 count recording, got {len(count_recs)}"
    assert count_recs[0]["attributes"]["http.status_code"] == 500


def test_http_metrics_unmatched_route_uses_placeholder_regression():
    """Regression: unmatched paths must use a bounded placeholder, not the raw URL.

    Using the raw URL path for 404s causes unbounded cardinality in metrics
    from probes, scanners, and random internet traffic.
    """
    client = TestClient(_make_app(), raise_server_exceptions=False)

    response = client.get("/random/nonexistent/path")
    assert response.status_code == 404

    count_recs = [r for r in _recorded if r["instrument"] == "count"]
    assert len(count_recs) == 1
    route_value = count_recs[0]["attributes"]["http.route"]
    assert route_value != "/random/nonexistent/path", (
        f"Raw URL path used as http.route for unmatched request: {route_value}"
    )
