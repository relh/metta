from pathlib import Path

from metta.trainingboard.local.backend.server import FRONTEND_ROOT


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_template_defaults_to_board_mode_ui() -> None:
    template = _read(FRONTEND_ROOT / "templates" / "index.html")

    assert "Top Bets: Now / Next / Later" in template
    assert 'id="topBetsBuckets"' in template
    assert "auto-refresh every 45s" in template
    assert 'id="refreshButton"' not in template


def test_app_enables_auto_refresh_and_buckets() -> None:
    app_js = _read(FRONTEND_ROOT / "static" / "app.js")

    assert "const AUTO_REFRESH_MS = 45_000;" in app_js
    assert 'query.get("hot") === "1"' in app_js
    assert "window.setInterval" in app_js
    assert 'bucketHtml("Now", "now", nowPanels)' in app_js
    assert 'bucketHtml("Next", "next", nextPanels)' in app_js
    assert 'bucketHtml("Later", "later", laterPanels)' in app_js
