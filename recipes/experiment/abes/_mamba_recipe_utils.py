from __future__ import annotations

import logging
import os
import platform
import subprocess
import sys
from pathlib import Path

import metta.tools as tools
from metta.rl.trainer_config import TorchProfilerConfig

DEFAULT_LEARNING_RATE = 8e-4
DEFAULT_BATCH_SIZE = 131_072
DEFAULT_MINIBATCH_SIZE = 4_096
DEFAULT_FORWARD_PASS_MINIBATCH_TARGET_SIZE = 1_024


def supports_mem_eff_path() -> bool:
    """Return True when fused causal-conv1d kernels are available."""

    try:
        from causal_conv1d import causal_conv1d_fn  # type: ignore[attr-defined]  # noqa: PLC0415
    except ModuleNotFoundError:
        return False

    return callable(causal_conv1d_fn)


def apply_training_overrides(
    tool: tools.TrainTool,
    *,
    learning_rate: float,
    batch_size: int,
    minibatch_size: int,
    forward_pass_minibatch_target_size: int,
) -> None:
    trainer = tool.trainer
    asset = tool.policy_assets["learner0"]  # recipe assumes one trainable policy
    optimizer = asset.optimizer
    optimizer.learning_rate = learning_rate
    trainer.batch_size = batch_size
    trainer.minibatch_size = minibatch_size
    tool.training_env.forward_pass_minibatch_target_size = forward_pass_minibatch_target_size
    tool.torch_profiler = TorchProfilerConfig(interval_epochs=0)


def ensure_cuda_extras_installed(logger: logging.Logger) -> None:
    if platform.system() != "Linux":
        return

    script_path = Path(__file__).resolve().parents[4] / "scripts" / "install_cuda_extras.py"
    if not script_path.exists():
        logger.warning("Could not locate install_cuda_extras.py; skipping CUDA extras installation.")
        return

    env = os.environ.copy()
    subprocess.run(
        [sys.executable, str(script_path), "--quiet"],
        check=True,
        env=env,
    )
