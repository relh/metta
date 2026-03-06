from __future__ import annotations

import importlib
import sys

import pytest

import vibeservatory.backend.dashboard_backend.database as dashboard_db


def test_dashboard_app_registers_embedded_service_routes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(dashboard_db, "configure_dashboard_db", lambda: None)
    sys.modules.pop("vibeservatory.backend.dashboard_backend.app", None)
    dashboard_app = importlib.import_module("vibeservatory.backend.dashboard_backend.app")

    route_paths = {route.path for route in dashboard_app.app.routes}
    assert "/bardo/v1/world-state" in route_paths
    assert "/dashboard/v1/cogames-diagnose/runs" in route_paths
    assert "/dashboard/v1/pantheon/stories" in route_paths
    assert "/chatprop/api/health" in route_paths
    assert "/train-board/api/health" in route_paths
