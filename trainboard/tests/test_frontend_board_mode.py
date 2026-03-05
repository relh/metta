from pathlib import Path

from metta.trainingboard.local.backend.server import FRONTEND_ROOT


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_template_defaults_to_board_mode_ui() -> None:
    template = _read(FRONTEND_ROOT / "templates" / "index.html")

    assert "Top Bets: Now / Next / Later" in template
    assert 'class="hero-metric-legend"' in template
    assert "score = 1 exp-par + 2 exp-qual" in template
    assert 'id="topBetsBuckets"' in template
    assert 'id="scoringMode"' in template
    assert "auto-refresh every 45s" in template
    assert 'id="refreshButton"' not in template
    assert 'id="pipelineHealthCards"' in template
    assert 'id="searchCoverageList"' in template
    assert 'id="meaningfulResultsSummary"' in template
    assert 'id="researchFunnelStages"' in template


def test_app_enables_auto_refresh_and_buckets() -> None:
    app_js = _read(FRONTEND_ROOT / "static" / "app.js")

    assert "const AUTO_REFRESH_MS = 45_000" in app_js
    assert "HOT_RELOAD_MS" not in app_js
    assert "window.setInterval" in app_js
    assert "withBasePath(" in app_js
    assert "/api/v1/board" in app_js
    assert "const scoringNode = document.getElementById('scoringMode')" in app_js
    assert "scoringNode.textContent = `scoring:" in app_js
    assert "bucketHtml('Now', 'now', nowTasks, impactMetrics, executionMetrics)" in app_js
    assert "bucketHtml('Next', 'next', nextTasks, impactMetrics, executionMetrics)" in app_js
    assert "bucketHtml('Later', 'later', laterTasks, impactMetrics, executionMetrics)" in app_js
    assert "const pipeline = board.pipeline || {}" in app_js
    assert "renderPipelineSnapshot(pipeline)" in app_js
    assert "const funnel = board.research_funnel || {}" in app_js
    assert "renderResearchFunnel(funnel)" in app_js


def test_app_renders_all_twelve_task_metrics_for_top_bets() -> None:
    app_js = _read(FRONTEND_ROOT / "static" / "app.js")
    template = _read(FRONTEND_ROOT / "templates" / "index.html")

    assert "IMPACT_METRIC_META" in app_js
    assert "EXECUTION_METRIC_META" in app_js
    assert "task.axis_scores || {}" in app_js
    assert "task.execution_scores || {}" in app_js
    assert 'class="bet-metrics"' in app_js
    assert ".bet-metrics" in template
    assert ".metric-pill" in template
