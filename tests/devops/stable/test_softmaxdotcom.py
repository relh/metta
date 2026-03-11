from __future__ import annotations

import subprocess
import sys

import pytest

from devops.stable.function_checks import softmaxdotcom as health_recipe
from devops.stable.stable_check_context import StableCheckContext


class _FakeResponse:
    def __init__(self, *, status_code: int, body: str):
        self._status_code = status_code
        self._body = body

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        _ = (exc_type, exc, tb)

    def getcode(self) -> int:
        return self._status_code

    def read(self) -> bytes:
        return self._body.encode("utf-8")


def _mock_urlopen(monkeypatch: pytest.MonkeyPatch, responses: dict[str, tuple[int, str]]) -> None:
    def _fake_urlopen(request, timeout: float):  # noqa: ANN001
        _ = timeout
        url = request.full_url
        status_code, body = responses[url]
        return _FakeResponse(status_code=status_code, body=body)

    monkeypatch.setattr(health_recipe, "urlopen", _fake_urlopen)


def test_alignmentleague_healthcheck_passes_with_expected_responses(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_urlopen(
        monkeypatch,
        {
            health_recipe.ALIGNMENTLEAGUE_URL: (
                200,
                "<html><head><title>Softmax — Scaling Alignment</title></head><body>softmax home page</body></html>",
            ),
            health_recipe.HEALTH_URL: (
                200,
                '{"status":"healthy","database":"connected"}',
            ),
            health_recipe.SEASONS_URL: (
                200,
                '[{"name":"season-1"}]',
            ),
        },
    )

    health_recipe.healthcheck(StableCheckContext(job_name="test.job", inputs={}))


def test_alignmentleague_healthcheck_fails_when_page_body_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_urlopen(
        monkeypatch,
        {
            health_recipe.ALIGNMENTLEAGUE_URL: (
                200,
                "",
            ),
            health_recipe.HEALTH_URL: (
                200,
                '{"status":"healthy","database":"connected"}',
            ),
            health_recipe.SEASONS_URL: (
                200,
                '[{"name":"season-1"}]',
            ),
        },
    )

    with pytest.raises(AssertionError, match="returned an empty response body"):
        health_recipe.healthcheck(StableCheckContext(job_name="test.job", inputs={}))


def test_alignmentleague_healthcheck_fails_when_health_unhealthy(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_urlopen(
        monkeypatch,
        {
            health_recipe.ALIGNMENTLEAGUE_URL: (
                200,
                "<html><head><title>Softmax — Scaling Alignment</title></head><body>softmax home page</body></html>",
            ),
            health_recipe.HEALTH_URL: (
                200,
                '{"status":"unhealthy","database":"connected"}',
            ),
            health_recipe.SEASONS_URL: (
                200,
                '[{"name":"season-1"}]',
            ),
        },
    )

    with pytest.raises(AssertionError, match="status='unhealthy'"):
        health_recipe.healthcheck(StableCheckContext(job_name="test.job", inputs={}))


def test_alignmentleague_healthcheck_fails_when_seasons_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_urlopen(
        monkeypatch,
        {
            health_recipe.ALIGNMENTLEAGUE_URL: (
                200,
                "<html><head><title>Softmax — Scaling Alignment</title></head><body>softmax home page</body></html>",
            ),
            health_recipe.HEALTH_URL: (
                200,
                '{"status":"healthy","database":"connected"}',
            ),
            health_recipe.SEASONS_URL: (
                200,
                "[]",
            ),
        },
    )

    with pytest.raises(AssertionError, match="returned an empty list"):
        health_recipe.healthcheck(StableCheckContext(job_name="test.job", inputs={}))


def test_stable_discovery_includes_alignmentleague_health_check() -> None:
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from devops.stable.stable_check_registry import discover_stable_checks; "
                "print([config.name for config in discover_stable_checks()])"
            ),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "softmaxdotcom.healthcheck" in probe.stdout
