from __future__ import annotations

from collections.abc import Callable

import pytest
import torch
from cortex.config import (
    AGaLiTeCoreConfig,
    AxonCoreConfig,
    CausalConv1dCoreConfig,
    LSTMCoreConfig,
    XLCoreConfig,
    mLSTMCoreConfig,
    sLSTMCoreConfig,
)
from cortex.cores.agalite import AGaLiTeCore
from cortex.cores.conv import CausalConv1dCore
from cortex.cores.core.axon_core import AxonCore
from cortex.cores.lstm import LSTMCore
from cortex.cores.mlstm import mLSTMCore
from cortex.cores.slstm import sLSTMCore
from cortex.cores.xl import XLCore
from tensordict import TensorDict
from torch.func import functional_call, stack_module_state

CUDA_REQUIRED = pytest.mark.skipif(not torch.cuda.is_available(), reason="CUDA required")

_SMOKE_CASES: list[tuple[str, Callable[[], torch.nn.Module]]] = [
    ("axon", lambda: AxonCore(AxonCoreConfig(hidden_size=16))),
    ("slstm", lambda: sLSTMCore(sLSTMCoreConfig(hidden_size=16, num_heads=2, use_axon_layer=False))),
    ("slstm_axon", lambda: sLSTMCore(sLSTMCoreConfig(hidden_size=16, num_heads=2, use_axon_layer=True))),
    (
        "mlstm",
        lambda: mLSTMCore(
            mLSTMCoreConfig(hidden_size=16, num_heads=2, chunk_size=4, use_axon_layer=False, use_axon_qkv=False)
        ),
    ),
    (
        "mlstm_axon",
        lambda: mLSTMCore(
            mLSTMCoreConfig(
                hidden_size=16,
                num_heads=2,
                chunk_size=4,
                use_axon_layer=True,
                use_axon_qkv=True,
                axon_qkv_config=AxonCoreConfig(hidden_size=16, out_dim=16, activation="identity"),
            )
        ),
    ),
    ("agalite", lambda: AGaLiTeCore(AGaLiTeCoreConfig(hidden_size=16, n_heads=2, eta=2, r=2))),
    (
        "xl",
        lambda: XLCore(
            XLCoreConfig(
                hidden_size=16,
                n_heads=2,
                mem_len=4,
                use_axon_qkv=True,
                axon_qkv_config=AxonCoreConfig(hidden_size=16, out_dim=16, activation="identity"),
            )
        ),
    ),
    ("lstm", lambda: LSTMCore(LSTMCoreConfig(hidden_size=16, num_layers=1, dropout=0.0))),
    (
        "conv_depthwise",
        lambda: CausalConv1dCore(
            CausalConv1dCoreConfig(hidden_size=16, kernel_size=3, causal_conv_bias=True, channel_mixing=False)
        ),
    ),
    (
        "conv_channelmix",
        lambda: CausalConv1dCore(
            CausalConv1dCoreConfig(hidden_size=16, kernel_size=3, causal_conv_bias=True, channel_mixing=True)
        ),
    ),
]

_PARITY_CASES: list[tuple[str, Callable[[], torch.nn.Module]]] = [
    ("axon", lambda: AxonCore(AxonCoreConfig(hidden_size=16))),
    ("slstm_axon", lambda: sLSTMCore(sLSTMCoreConfig(hidden_size=16, num_heads=2, use_axon_layer=True))),
    (
        "mlstm_axon",
        lambda: mLSTMCore(
            mLSTMCoreConfig(
                hidden_size=16,
                num_heads=2,
                chunk_size=4,
                use_axon_layer=True,
                use_axon_qkv=True,
                axon_qkv_config=AxonCoreConfig(hidden_size=16, out_dim=16, activation="identity"),
            )
        ),
    ),
    ("agalite", lambda: AGaLiTeCore(AGaLiTeCoreConfig(hidden_size=16, n_heads=2, eta=2, r=2))),
    (
        "xl",
        lambda: XLCore(
            XLCoreConfig(
                hidden_size=16,
                n_heads=2,
                mem_len=4,
                use_axon_qkv=True,
                axon_qkv_config=AxonCoreConfig(hidden_size=16, out_dim=16, activation="identity"),
            )
        ),
    ),
    (
        "conv_channelmix",
        lambda: CausalConv1dCore(
            CausalConv1dCoreConfig(hidden_size=16, kernel_size=3, causal_conv_bias=True, channel_mixing=True)
        ),
    ),
    ("lstm", lambda: LSTMCore(LSTMCoreConfig(hidden_size=16, num_layers=1, dropout=0.0))),
]


def _clone_params(params: dict[str, torch.Tensor]) -> dict[str, torch.Tensor]:
    return {key: value.detach().clone().requires_grad_(value.requires_grad) for key, value in params.items()}


def _clone_buffers(buffers: dict[str, torch.Tensor]) -> dict[str, torch.Tensor]:
    return {key: value.detach().clone() for key, value in buffers.items()}


def _run_vmap(
    module: torch.nn.Module,
    params: dict[str, torch.Tensor],
    buffers: dict[str, torch.Tensor],
    state: TensorDict,
    x: torch.Tensor,
    resets: torch.Tensor,
) -> tuple[torch.Tensor, TensorDict]:
    def fn(p, b, s):
        return functional_call(module, (p, b), (x, s), {"resets": resets})

    return torch.vmap(fn, in_dims=(0, 0, 0))(params, buffers, state)


def _run_loop(
    module: torch.nn.Module,
    params: dict[str, torch.Tensor],
    buffers: dict[str, torch.Tensor],
    state: TensorDict,
    x: torch.Tensor,
    resets: torch.Tensor,
) -> tuple[torch.Tensor, TensorDict]:
    outputs = []
    states = []
    for index in range(next(iter(params.values())).shape[0]):
        param_slice = {key: value[index] for key, value in params.items()}
        buffer_slice = {key: value[index] for key, value in buffers.items()}
        y_i, state_i = functional_call(module, (param_slice, buffer_slice), (x, state[index]), {"resets": resets})
        outputs.append(y_i)
        states.append(state_i)
    return torch.stack(outputs, dim=0), torch.stack(states, dim=0)


@CUDA_REQUIRED
@pytest.mark.cuda
@pytest.mark.parametrize(("name", "factory"), _SMOKE_CASES, ids=[name for name, _ in _SMOKE_CASES])
def test_parameter_batched_vmap_cuda_smoke(name: str, factory: Callable[[], torch.nn.Module]) -> None:
    torch.manual_seed(0)
    device = torch.device("cuda")
    dtype = torch.float32
    ensemble = 2
    batch = 2
    seq = 4

    modules = [factory().to(device=device, dtype=dtype) for _ in range(ensemble)]
    for module in modules:
        if isinstance(module, LSTMCore):
            module.train()
        else:
            module.eval()
    params, buffers = stack_module_state(modules)
    state = torch.stack([module.init_state(batch=batch, device=device, dtype=dtype) for module in modules], dim=0)
    x = torch.randn(batch, seq, modules[0].hidden_size, device=device, dtype=dtype, requires_grad=True)
    resets = torch.zeros(batch, seq, device=device, dtype=torch.bool)

    y, next_state = _run_vmap(modules[0], params, buffers, state, x, resets)
    grads = torch.autograd.grad(y.sum(), tuple(params.values()) + (x,))

    assert y.shape == (ensemble, batch, seq, modules[0].hidden_size), name
    assert next_state.batch_size == torch.Size([ensemble, batch]), name
    assert grads[-1].shape == x.shape, name


@CUDA_REQUIRED
@pytest.mark.cuda
@pytest.mark.parametrize(("name", "factory"), _PARITY_CASES, ids=[name for name, _ in _PARITY_CASES])
def test_parameter_batched_vmap_matches_loop_on_cuda(name: str, factory: Callable[[], torch.nn.Module]) -> None:
    torch.manual_seed(0)
    device = torch.device("cuda")
    dtype = torch.float32
    ensemble = 2
    batch = 2
    seq = 4

    modules = [factory().to(device=device, dtype=dtype) for _ in range(ensemble)]
    for module in modules:
        if isinstance(module, LSTMCore):
            module.train()
        else:
            module.eval()
    params_base, buffers_base = stack_module_state(modules)
    state_base = torch.stack([module.init_state(batch=batch, device=device, dtype=dtype) for module in modules], dim=0)
    x_base = torch.randn(batch, seq, modules[0].hidden_size, device=device, dtype=dtype)
    resets = torch.zeros(batch, seq, device=device, dtype=torch.bool)

    params_vmap = _clone_params(params_base)
    buffers_vmap = _clone_buffers(buffers_base)
    state_vmap = state_base.clone(recurse=True)
    x_vmap = x_base.detach().clone().requires_grad_(True)
    y_vmap, next_state_vmap = _run_vmap(modules[0], params_vmap, buffers_vmap, state_vmap, x_vmap, resets)
    grads_vmap = torch.autograd.grad(y_vmap.sum(), tuple(params_vmap.values()) + (x_vmap,))

    params_loop = _clone_params(params_base)
    buffers_loop = _clone_buffers(buffers_base)
    state_loop = state_base.clone(recurse=True)
    x_loop = x_base.detach().clone().requires_grad_(True)
    y_loop, next_state_loop = _run_loop(modules[0], params_loop, buffers_loop, state_loop, x_loop, resets)
    grads_loop = torch.autograd.grad(y_loop.sum(), tuple(params_loop.values()) + (x_loop,))

    torch.testing.assert_close(y_vmap, y_loop, rtol=5e-4, atol=5e-4)
    flat_vmap_state = next_state_vmap.flatten_keys(".")
    flat_loop_state = next_state_loop.flatten_keys(".")
    assert set(flat_vmap_state.keys()) == set(flat_loop_state.keys()), name
    for key, value in flat_vmap_state.items():
        torch.testing.assert_close(value, flat_loop_state[key], rtol=5e-4, atol=5e-4)
    for grad_vmap, grad_loop in zip(grads_vmap, grads_loop, strict=True):
        torch.testing.assert_close(grad_vmap, grad_loop, rtol=5e-4, atol=5e-4)
