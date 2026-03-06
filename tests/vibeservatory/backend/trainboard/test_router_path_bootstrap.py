from __future__ import annotations

import importlib
import sys
from pathlib import Path


def test_trainboard_router_adds_trainboard_src_to_pythonpath() -> None:
    module_name = "vibeservatory.backend.dashboard_backend.trainboard.router"
    expected_path = str(Path(__file__).resolve().parents[4] / "trainboard" / "src")
    original_sys_path = list(sys.path)

    try:
        sys.modules.pop(module_name, None)
        sys.path[:] = [entry for entry in sys.path if entry != expected_path]

        router_module = importlib.import_module(module_name)

        assert str(router_module.TRAINBOARD_SRC_ROOT) == expected_path
        assert expected_path in sys.path
    finally:
        sys.modules.pop(module_name, None)
        sys.path[:] = original_sys_path
