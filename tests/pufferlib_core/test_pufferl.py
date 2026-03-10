from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PUFFERLIB_SRC = REPO_ROOT / "packages" / "pufferlib-core" / "src"
PUFFERLIB_PKG = PUFFERLIB_SRC / "pufferlib"


def _run_pufferl_script(script: str) -> subprocess.CompletedProcess[str]:
    extension_spec = importlib.util.find_spec("pufferlib._C")
    assert extension_spec is not None and extension_spec.origin is not None

    with tempfile.TemporaryDirectory() as tmpdir:
        package_root = Path(tmpdir)
        package_dir = package_root / "pufferlib"
        shutil.copytree(PUFFERLIB_PKG, package_dir)
        shutil.copy2(extension_spec.origin, package_dir / Path(extension_spec.origin).name)

        env = os.environ.copy()
        pythonpath = env.get("PYTHONPATH")
        env["PYTHONPATH"] = str(package_root) if not pythonpath else f"{package_root}:{pythonpath}"
        return subprocess.run(
            [sys.executable, "-c", textwrap.dedent(script)],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )


def test_advantage_cuda_detection_uses_dispatch_registration() -> None:
    result = _run_pufferl_script(
        """
        import importlib
        import torch
        import pufferlib

        calls = []

        def fake_has_kernel(op_name, dispatch_key):
            calls.append((op_name, dispatch_key))
            return False

        torch._C._dispatch_has_kernel_for_dispatch_key = fake_has_kernel
        module = importlib.import_module("pufferlib.pufferl")
        print(module.ADVANTAGE_CUDA)
        print(calls)
        """
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "False",
        "[('pufferlib::compute_puff_advantage', 'CUDA')]",
    ]


def test_advantage_cuda_detection_reports_registered_kernel() -> None:
    result = _run_pufferl_script(
        """
        import importlib
        import torch
        import pufferlib

        torch._C._dispatch_has_kernel_for_dispatch_key = (
            lambda op_name, dispatch_key: op_name == "pufferlib::compute_puff_advantage" and dispatch_key == "CUDA"
        )
        module = importlib.import_module("pufferlib.pufferl")
        print(module.ADVANTAGE_CUDA)
        """
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "True"


def test_compute_puff_advantage_falls_back_to_cpu() -> None:
    result = _run_pufferl_script(
        """
        import importlib
        import torch
        import pufferlib

        torch._C._dispatch_has_kernel_for_dispatch_key = lambda *_args: False
        module = importlib.import_module("pufferlib.pufferl")

        seen_devices = []

        def fake_compute(values, rewards, terminals, ratio, advantages, *_args):
            seen_devices.extend(t.device.type for t in (values, rewards, terminals, ratio, advantages))
            advantages.copy_(torch.full_like(advantages, 7.0))

        torch.ops.pufferlib.compute_puff_advantage = fake_compute

        values = torch.zeros((2, 4), dtype=torch.float32)
        rewards = torch.zeros((2, 4), dtype=torch.float32)
        terminals = torch.zeros((2, 4), dtype=torch.float32)
        ratio = torch.ones((2, 4), dtype=torch.float32)
        advantages = torch.zeros((2, 4), dtype=torch.float32)

        out = module.compute_puff_advantage(values, rewards, terminals, ratio, advantages, 0.99, 0.95, 1.0, 1.0)
        print(seen_devices)
        print(out.tolist())
        """
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "['cpu', 'cpu', 'cpu', 'cpu', 'cpu']",
        "[[7.0, 7.0, 7.0, 7.0], [7.0, 7.0, 7.0, 7.0]]",
    ]
