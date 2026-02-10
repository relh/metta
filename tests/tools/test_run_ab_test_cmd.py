import importlib.util
import sys
from pathlib import Path

from metta.abtest.experiment import ABRun


def _load_run_ab_test_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "tools" / "run_ab_test.py"
    spec = importlib.util.spec_from_file_location("run_ab_test", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)  # type: ignore[call-arg]
    return module


def test_skypilot_cmd_does_not_pass_confirm_false() -> None:
    mod = _load_run_ab_test_module()
    run = ABRun(experiment="exp", variant="A", index=0, run_id="r0", args=["train", "arena", "run=test"])
    cfg = mod.LaunchConfig(
        skypilot=True,
        dry_run=False,
        parallel=1,
        gpus=None,
        nodes=None,
        cpus=None,
        spot=False,
        max_runtime_hours=None,
    )

    cmd = mod._cmd_for_run(run, tool_tokens=["arena.train"], cfg=cfg)
    assert "--confirm=false" not in cmd


def test_skypilot_cmd_keeps_dry_run_flag() -> None:
    mod = _load_run_ab_test_module()
    run = ABRun(experiment="exp", variant="A", index=0, run_id="r0", args=["train", "arena", "run=test"])
    cfg = mod.LaunchConfig(
        skypilot=True,
        dry_run=True,
        parallel=1,
        gpus=None,
        nodes=None,
        cpus=None,
        spot=False,
        max_runtime_hours=None,
    )

    cmd = mod._cmd_for_run(run, tool_tokens=["arena.train"], cfg=cfg)
    assert "--dry-run" in cmd
