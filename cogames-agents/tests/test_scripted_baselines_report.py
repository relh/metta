from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_report_script():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_scripted_baselines_report.py"
    spec = importlib.util.spec_from_file_location("run_scripted_baselines_report", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_collect_role_conditional_reward_keys_supports_current_cvc_mission_api() -> None:
    module = _load_report_script()

    reward_keys_by_role = module._collect_role_conditional_reward_keys()

    assert set(reward_keys_by_role) == set(module.SHAPED_REWARD_ALIGNMENT_RULES)
    assert "gain_diversity" in reward_keys_by_role["miner"]
    assert "junction_aligned_by_agent" in reward_keys_by_role["aligner"]
    assert "junction_scrambled_by_agent" in reward_keys_by_role["scrambler"]
    assert "cell_visited" in reward_keys_by_role["scout"]
