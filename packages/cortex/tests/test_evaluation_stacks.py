from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import torch


def _load_evaluation_stacks_module():
    module_path = Path(__file__).resolve().parents[1] / "evaluations" / "stacks.py"
    spec = importlib.util.spec_from_file_location("cortex_evaluation_stacks", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_non_hf_evaluation_stack_builders_use_current_api():
    stacks_module = _load_evaluation_stacks_module()
    x = torch.randn(2, 4, 128)

    for stack_name in (
        "slstm",
        "mlstm",
        "slstm_axon",
        "mlstm_axon",
        "axons",
        "cortex_auto",
        "cortex_auto_compiled",
        "cortex_auto_axon",
    ):
        stack = stacks_module.STACKS[stack_name].builder()
        y, _ = stack(x, state=None)
        assert y.shape == x.shape
