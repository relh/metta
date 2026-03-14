"""Template Cortex stack builders for the synthetic evaluation harness.

This module centralizes a handful of small, readable "stack recipes" that are
useful for quick comparisons on synthetic tasks. They showcase how to compose
cell presets and explicit scaffolds via the configuration layer, and how to
expose higher-level architectures like xLSTM behind a simple callable.

Add new templates by:
1) Writing a `build_*` function that returns a `CortexStack` (see examples).
2) Registering it in `STACKS` with a `StackSpec` so it becomes available via
   the `--stack` CLI flag in `run.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict

import torch
from cortex.cells import AxonCellConfig, XLCellConfig, mLSTMCellConfig, sLSTMCellConfig
from cortex.config import (
    AxonCoreConfig,
    CortexStackConfig,
    PassThroughScaffoldConfig,
    PostUpScaffoldConfig,
    PreUpScaffoldConfig,
    XLCoreConfig,
    mLSTMCoreConfig,
    sLSTMCoreConfig,
)
from cortex.factory import build_cortex
from cortex.stacks import CortexStack, build_cortex_auto_stack, build_hf_stack

# cortex_auto_stack is implemented in core (cortex.stacks.auto);
# this module simply imports and registers it below.


@dataclass
class StackSpec:
    name: str
    builder: Callable[[], CortexStack]
    d_hidden: int


def build_slstm_postup(*, d_hidden: int = 128, proj_factor: float = 1.5, num_heads: int = 4) -> CortexStack:
    """sLSTM core in a PostUp scaffold; core size equals external hidden size."""
    cfg = CortexStackConfig(
        d_hidden=d_hidden,
        post_norm=True,
        scaffolds=[
            PostUpScaffoldConfig(
                proj_factor=proj_factor,
                # hidden_size may be None here; the stack builder sets it to d_hidden for PostUp.
                core=sLSTMCoreConfig(hidden_size=None, num_heads=num_heads, conv1d_kernel_size=4, dropout=0.0),
            )
        ],
    )
    return build_cortex(cfg)


def build_mlstm_preup(*, d_hidden: int = 128, proj_factor: float = 2.0, num_heads: int = 4) -> CortexStack:
    """mLSTM core in a PreUp scaffold; the core runs at inner dim = proj_factor*d_hidden."""
    cfg = CortexStackConfig(
        d_hidden=d_hidden,
        post_norm=True,
        scaffolds=[
            PreUpScaffoldConfig(
                proj_factor=proj_factor,
                # hidden_size may be None here; the stack builder sets it to int(proj_factor * d_hidden) for PreUp.
                core=mLSTMCoreConfig(hidden_size=None, num_heads=num_heads, chunk_size=256, conv1d_kernel_size=4),
            )
        ],
    )
    return build_cortex(cfg)


def build_slstm_postup_axon(*, d_hidden: int = 128, proj_factor: float = 1.5, num_heads: int = 4) -> CortexStack:
    """sLSTM PostUp variant with AxonLayer headwise gates enabled via flag.

    Only the per-head gate projections use Axon; the core sLSTM kernel remains unchanged.
    """
    cfg = CortexStackConfig(
        d_hidden=d_hidden,
        post_norm=True,
        scaffolds=[
            PreUpScaffoldConfig(
                # hidden_size is inferred from PreUp: int(proj_factor * d_hidden)
                core=AxonCoreConfig(
                    hidden_size=None, activation="silu", use_fullrank_rtu=False, use_untraced_linear=True
                )
            ),
            PostUpScaffoldConfig(
                proj_factor=proj_factor,
                core=sLSTMCoreConfig(
                    hidden_size=None,
                    num_heads=num_heads,
                    conv1d_kernel_size=4,
                    dropout=0.0,
                    use_axon_layer=True,
                ),
            ),
        ],
    )
    return build_cortex(cfg)


def build_mlstm_preup_axon(*, d_hidden: int = 128, proj_factor: float = 2.0, num_heads: int = 4) -> CortexStack:
    """mLSTM PreUp variant with AxonLayer gates (3H→NH) enabled via flag."""
    cfg = CortexStackConfig(
        d_hidden=d_hidden,
        post_norm=True,
        scaffolds=[
            PassThroughScaffoldConfig(
                # hidden_size is inferred from PreUp: int(proj_factor * d_hidden)
                core=AxonCoreConfig(
                    hidden_size=None, activation="silu", use_fullrank_rtu=False, use_untraced_linear=True
                )
            ),
            PreUpScaffoldConfig(
                proj_factor=proj_factor,
                core=mLSTMCoreConfig(
                    hidden_size=None,
                    num_heads=num_heads,
                    chunk_size=256,
                    conv1d_kernel_size=4,
                    use_axon_layer=True,
                    use_axon_qkv=True,
                ),
            ),
        ],
    )
    return build_cortex(cfg)


def build_axons_preup(*, d_hidden: int = 128, proj_factor: float = 2.0) -> CortexStack:
    """Axon cores (streaming RTU, diagonal) wrapped in a PreUp scaffold.

    - The PreUp scaffold projects inputs to an inner dim of ``proj_factor*d_hidden``
      before applying the Axon core.
    - Axon assumes D == H internally and projects its 2H activation
      back to H, keeping the external hidden size consistent.
    """
    cfg = CortexStackConfig(
        d_hidden=d_hidden,
        post_norm=True,
        scaffolds=[
            PassThroughScaffoldConfig(
                # hidden_size is inferred from PreUp: int(proj_factor * d_hidden)
                core=AxonCoreConfig(
                    hidden_size=None, activation="silu", use_fullrank_rtu=False, use_untraced_linear=True
                )
            ),
            PreUpScaffoldConfig(
                proj_factor=proj_factor,
                # hidden_size is inferred from PreUp: int(proj_factor * d_hidden)
                core=AxonCoreConfig(
                    hidden_size=None, activation="silu", use_fullrank_rtu=False, use_untraced_linear=True
                ),
            ),
        ],
    )
    return build_cortex(cfg)


def build_smollm_stack(*, model_name: str = "HuggingFaceTB/SmolLM-360M") -> CortexStack:
    """SmolLM (LLaMA-derivative) HF stack with lightweight dtype defaults."""
    return build_hf_stack(
        model_name=model_name,
        torch_dtype=torch.bfloat16,
        trust_remote_code=False,
        mem_len=64,
        compile_scaffolds=False,
    )


# Registry of available stacks for the evaluation harness
STACKS: Dict[str, StackSpec] = {
    # Single-scaffold templates
    "slstm": StackSpec(name="slstm_postup", builder=lambda: build_slstm_postup(), d_hidden=128),
    "mlstm": StackSpec(name="mlstm_preup", builder=lambda: build_mlstm_preup(), d_hidden=128),
    "slstm_axon": StackSpec(name="slstm_postup_axon", builder=lambda: build_slstm_postup_axon(), d_hidden=128),
    "mlstm_axon": StackSpec(name="mlstm_preup_axon", builder=lambda: build_mlstm_preup_axon(), d_hidden=128),
    "axons": StackSpec(name="axons_preup", builder=lambda: build_axons_preup(), d_hidden=128),
    # Composite templates
    # Mixed auto stack cycling Axon/mLSTM/sLSTM with PreUp/PreUp/PostUp
    "cortex_auto": StackSpec(
        name="cortex_auto_stack",
        builder=lambda: build_cortex_auto_stack(
            d_hidden=128,
            num_layers=2,
            compile_scaffolds=False,
            layers=[[AxonCellConfig(), mLSTMCellConfig(), sLSTMCellConfig()]] * 2,
        ),
        d_hidden=128,
    ),
    # Variant with per-scaffold torch.compile enabled for A/B comparisons
    "cortex_auto_compiled": StackSpec(
        name="cortex_auto_stack",
        builder=lambda: build_cortex_auto_stack(
            d_hidden=128,
            num_layers=2,
            compile_scaffolds=True,
            layers=[[AxonCellConfig(), XLCellConfig(), mLSTMCellConfig(), sLSTMCellConfig()]] * 2,
        ),
        d_hidden=128,
    ),
    "cortex_auto_axon": StackSpec(
        name="cortex_auto_stack",
        builder=lambda: build_cortex_auto_stack(
            d_hidden=128,
            num_layers=2,
            layers=[
                [
                    mLSTMCellConfig(core=mLSTMCoreConfig(use_axon_layer=True, use_axon_qkv=True)),
                    XLCellConfig(core=XLCoreConfig(use_axon_qkv=True)),
                    sLSTMCellConfig(core=sLSTMCoreConfig(use_axon_layer=True)),
                ]
            ]
            * 2,
        ),
        d_hidden=128,
    ),
    "smollm": StackSpec(
        name="smollm_stack",
        builder=lambda: build_smollm_stack(),
        d_hidden=960,
    ),
}


__all__ = [
    "StackSpec",
    "STACKS",
    "build_slstm_postup",
    "build_mlstm_preup",
    "build_axons_preup",
    "build_cortex_auto_stack",
    "build_smollm_stack",
]
