from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

import vibeservatory.backend.dashboard_backend.database as dashboard_db

EXPECTED_SURFACES = {
    "bardo",
    "pantheon",
    "policy-dashboard",
    "chatprop",
    "trainboard",
    "diagnose",
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _load_contract() -> list[dict[str, str]]:
    contract_path = _repo_root() / "vibeservatory" / "iframe_surfaces.json"
    payload = json.loads(contract_path.read_text(encoding="utf-8"))
    assert isinstance(payload, list)
    return payload


def test_iframe_surface_contract_has_all_six_and_top_level_folders() -> None:
    contract = _load_contract()
    assert {entry["name"] for entry in contract} == EXPECTED_SURFACES
    for entry in contract:
        surface_dir = _repo_root() / entry["top_level_folder"]
        assert surface_dir.is_dir(), f"Missing top-level surface folder: {surface_dir}"


def test_iframe_surface_contract_routes_exist_in_vibeservatory_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract = _load_contract()
    required_routes = {entry["backend_required_route"] for entry in contract}

    monkeypatch.setattr(dashboard_db, "configure_dashboard_db", lambda: None)
    sys.modules.pop("vibeservatory.backend.dashboard_backend.app", None)
    dashboard_app = importlib.import_module("vibeservatory.backend.dashboard_backend.app")

    route_paths = {route.path for route in dashboard_app.app.routes}
    assert required_routes.issubset(route_paths)
    assert dashboard_app.REQUIRED_ROUTE_PATHS == required_routes
