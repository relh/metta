from __future__ import annotations

import pytest
import torch
import torch.nn as nn
from cortex import (
    CortexStackConfig,
    PassThroughBlockConfig,
    PreUpBlockConfig,
    RoutedAdapterConfig,
    build_column_auto_block,
    build_cortex,
    sLSTMCellConfig,
)
from cortex.config import AGaLiTeCellConfig, XLCellConfig
from cortex.routed_adapter import (
    RoutedAdapterHeadwiseLinearExpand,
    RoutedAdapterLinear,
    apply_routed_adapter_,
    set_trunk_lr_mult_,
    use_route_ids,
)
from cortex.stacks import build_cortex_auto_stack


def test_routed_adapter_linear_noop_init() -> None:
    torch.manual_seed(0)
    linear = nn.Linear(7, 5, bias=True)
    cfg = RoutedAdapterConfig(num_slots=4, rank=3, dropout=0.0, freeze_base=False, require_route_ids=True)
    adapter = RoutedAdapterLinear.from_linear(linear, cfg)

    x = torch.randn(6, 7)
    route_ids = torch.tensor([0, 1, 2, 3, 1, 0], dtype=torch.long)

    with use_route_ids(route_ids):
        y_adapter = adapter(x)
    y_base = linear(x)

    assert torch.allclose(y_adapter, y_base, atol=1e-6)


def test_routed_adapter_default_keeps_base_trainable() -> None:
    linear = nn.Linear(7, 5, bias=True)
    cfg = RoutedAdapterConfig(num_slots=4, rank=3)
    adapter = RoutedAdapterLinear.from_linear(linear, cfg)

    assert adapter.weight.requires_grad
    assert adapter.bias is not None
    assert adapter.bias.requires_grad


def test_routed_adapter_linear_routes_gradients_by_route_id() -> None:
    torch.manual_seed(0)
    linear = nn.Linear(6, 4, bias=False)
    cfg = RoutedAdapterConfig(num_slots=3, rank=2, dropout=0.0, freeze_base=True, require_route_ids=True)
    adapter = RoutedAdapterLinear.from_linear(linear, cfg)
    with torch.no_grad():
        adapter.adapter_B.normal_(mean=0.0, std=0.05)

    x = torch.randn(5, 6)
    route_ids = torch.tensor([0, 1, 1, 2, 2], dtype=torch.long)
    slot_to_optimize = 1

    with use_route_ids(route_ids):
        y = adapter(x)
    mask = route_ids == slot_to_optimize
    loss = y[mask].sum()
    loss.backward()

    assert adapter.weight.grad is None

    grad_a = adapter.adapter_A.grad
    grad_b = adapter.adapter_B.grad
    assert grad_a is not None
    assert grad_b is not None

    for slot in range(cfg.num_slots):
        grad_a_slot = grad_a[slot]
        grad_b_slot = grad_b[slot]
        if slot == slot_to_optimize:
            assert float(grad_a_slot.abs().sum()) > 0.0
            assert float(grad_b_slot.abs().sum()) > 0.0
        else:
            assert torch.allclose(grad_a_slot, torch.zeros_like(grad_a_slot), atol=0.0, rtol=0.0)
            assert torch.allclose(grad_b_slot, torch.zeros_like(grad_b_slot), atol=0.0, rtol=0.0)


def test_routed_adapter_linear_missing_route_ids_uses_slot_zero() -> None:
    torch.manual_seed(0)
    linear = nn.Linear(6, 4, bias=False)
    cfg = RoutedAdapterConfig(num_slots=3, rank=2, dropout=0.0, freeze_base=False, require_route_ids=False)
    adapter = RoutedAdapterLinear.from_linear(linear, cfg)
    with torch.no_grad():
        adapter.adapter_B.normal_(mean=0.0, std=0.05)

    x = torch.randn(5, 6)
    with use_route_ids(None):
        y_none = adapter(x)
    with use_route_ids(torch.zeros(x.shape[0], dtype=torch.long)):
        y_zero = adapter(x)
    assert torch.allclose(y_none, y_zero, atol=1e-6)


def test_routed_adapter_linear_bypass_keeps_adapter_params_in_graph() -> None:
    torch.manual_seed(0)
    linear = nn.Linear(6, 4, bias=False)
    cfg = RoutedAdapterConfig(num_slots=3, rank=2, dropout=0.0, freeze_base=False, require_route_ids=False)
    adapter = RoutedAdapterLinear.from_linear(linear, cfg)

    # 1D input bypasses route-id matching logic inside RoutedAdapterLinear.
    x = torch.randn(6)
    with use_route_ids(None):
        y = adapter(x)
    y.sum().backward()

    assert adapter.adapter_A.grad is not None
    assert adapter.adapter_B.grad is not None
    assert torch.allclose(adapter.adapter_A.grad, torch.zeros_like(adapter.adapter_A.grad), atol=0.0, rtol=0.0)
    assert torch.allclose(adapter.adapter_B.grad, torch.zeros_like(adapter.adapter_B.grad), atol=0.0, rtol=0.0)


def test_routed_adapter_trunk_lr_mult_can_be_updated_on_the_fly() -> None:
    torch.manual_seed(0)

    class Toy(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.ln = nn.LayerNorm(6)
            self.linear = nn.Linear(6, 5, bias=False)

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            return self.linear(self.ln(x))

    model = Toy()
    trunk_lr_mult = 0.1
    apply_routed_adapter_(
        model,
        RoutedAdapterConfig(num_slots=3, rank=2, dropout=0.0, freeze_base=False, trunk_lr_mult=1.0),
    )

    adapters = [m for m in model.modules() if isinstance(m, RoutedAdapterLinear)]
    assert adapters
    with torch.no_grad():
        for adapter in adapters:
            adapter.adapter_B.normal_(mean=0.0, std=0.05)

    B = 4
    x = torch.randn(B, 6)
    route_ids = torch.tensor([0, 1, 2, 0], dtype=torch.long)

    def _grads() -> dict[str, torch.Tensor]:
        model.zero_grad(set_to_none=True)
        with use_route_ids(route_ids):
            y = model(x)
        loss = y.square().mean()
        loss.backward()
        return {name: p.grad.clone() for name, p in model.named_parameters()}

    grads_base = _grads()
    set_trunk_lr_mult_(model, trunk_lr_mult)
    grads_scaled = _grads()

    for name, base_grad in grads_base.items():
        scaled_grad = grads_scaled[name]
        if name.endswith(("adapter_A", "adapter_B")):
            assert torch.allclose(scaled_grad, base_grad, atol=1e-6, rtol=1e-6)
        else:
            assert torch.allclose(scaled_grad, base_grad * trunk_lr_mult, atol=1e-6, rtol=1e-6)


def test_column_router_logits_not_coupled_across_route_id_batch_mix() -> None:
    torch.manual_seed(0)
    block = build_column_auto_block(
        d_hidden=32,
        pattern="AXMS",
        routed_adapter=RoutedAdapterConfig(num_slots=8, rank=4),
    )
    assert block.router is not None

    for module in block.router.modules():
        if isinstance(module, RoutedAdapterLinear):
            with torch.no_grad():
                module.adapter_B.normal_(mean=0.0, std=0.05)

    with use_route_ids(torch.tensor([0, 1], dtype=torch.long)):
        logits_01 = block.router.global_logits(restrict_topk=False)
    with use_route_ids(torch.tensor([0, 2], dtype=torch.long)):
        logits_02 = block.router.global_logits(restrict_topk=False)

    assert logits_01.dim() == 2
    assert logits_01.shape[0] == 2
    assert torch.allclose(logits_01[0], logits_02[0], atol=1e-6)


def test_cortex_stack_requires_route_ids_when_adapter_enabled() -> None:
    cfg = CortexStackConfig(
        d_hidden=16,
        blocks=[PreUpBlockConfig(cell=sLSTMCellConfig(hidden_size=None, num_heads=4), proj_factor=1.0)],
        post_norm=False,
        compile_blocks=False,
        routed_adapter=RoutedAdapterConfig(num_slots=4, rank=2),
    )
    stack = build_cortex(cfg)

    batch_size, seq_len = 3, 2
    x = torch.randn(batch_size, seq_len, 16)
    state = stack.init_state(batch=batch_size, device=x.device, dtype=x.dtype)

    with pytest.raises(ValueError, match="route_ids"):
        stack(x, state)


def test_cortex_stack_routed_adapter_sequence_and_step() -> None:
    torch.manual_seed(0)
    cfg = CortexStackConfig(
        d_hidden=32,
        blocks=[PreUpBlockConfig(cell=sLSTMCellConfig(hidden_size=None, num_heads=4), proj_factor=1.5)],
        post_norm=False,
        compile_blocks=True,
        routed_adapter=RoutedAdapterConfig(num_slots=8, rank=4),
    )
    stack = build_cortex(cfg)

    assert stack._routed_adapter_replaced_modules > 0
    assert stack._compiled_blocks is None

    batch_size, seq_len = 4, 3
    route_ids = torch.tensor([0, 1, 2, 3], dtype=torch.long)
    x_seq = torch.randn(batch_size, seq_len, 32)
    state = stack.init_state(batch=batch_size, device=x_seq.device, dtype=x_seq.dtype)

    y_seq, next_state = stack(x_seq, state, route_ids=route_ids)
    assert y_seq.shape == x_seq.shape

    x_step = torch.randn(batch_size, 32)
    y_step, _ = stack.step(x_step, next_state, route_ids=route_ids)
    assert y_step.shape == x_step.shape


def test_slstm_headwise_linear_is_adapter_wrapped() -> None:
    cfg = CortexStackConfig(
        d_hidden=24,
        blocks=[PassThroughBlockConfig(cell=sLSTMCellConfig(hidden_size=24, num_heads=4, use_axon_layer=False))],
        post_norm=False,
        compile_blocks=False,
        routed_adapter=RoutedAdapterConfig(num_slots=5, rank=2),
    )
    stack = build_cortex(cfg)

    wrapped = [m for m in stack.modules() if isinstance(m, RoutedAdapterHeadwiseLinearExpand)]
    assert wrapped, "Expected _HeadwiseLinearExpand modules to be adapter-wrapped."

    batch_size, seq_len = 2, 4
    x = torch.randn(batch_size, seq_len, 24)
    state = stack.init_state(batch=batch_size, device=x.device, dtype=x.dtype)
    route_ids = torch.tensor([0, 4], dtype=torch.long)
    y, _ = stack(x, state, route_ids=route_ids)
    assert y.shape == x.shape


def test_routed_adapter_auto_stack_axms_sequence_and_step() -> None:
    stack = build_cortex_auto_stack(
        d_hidden=32,
        num_layers=1,
        pattern="AXMS",
        compile_blocks=False,
        routed_adapter=RoutedAdapterConfig(num_slots=8, rank=4),
    )

    batch_size, seq_len = 4, 3
    x_seq = torch.randn(batch_size, seq_len, 32)
    route_ids = torch.tensor([0, 1, 2, 3], dtype=torch.long)
    state = stack.init_state(batch=batch_size, device=x_seq.device, dtype=x_seq.dtype)
    y_seq, next_state = stack(x_seq, state, route_ids=route_ids)
    assert y_seq.shape == x_seq.shape

    x_step = torch.randn(batch_size, 32)
    y_step, _ = stack.step(x_step, next_state, route_ids=route_ids)
    assert y_step.shape == x_step.shape


def test_routed_adapter_auto_stack_axon_optins_sequence_and_step() -> None:
    stack = build_cortex_auto_stack(
        d_hidden=32,
        num_layers=1,
        pattern="X^M^S^",
        compile_blocks=False,
        routed_adapter=RoutedAdapterConfig(num_slots=8, rank=4),
    )

    batch_size, seq_len = 4, 3
    x_seq = torch.randn(batch_size, seq_len, 32)
    route_ids = torch.tensor([0, 1, 2, 3], dtype=torch.long)
    state = stack.init_state(batch=batch_size, device=x_seq.device, dtype=x_seq.dtype)
    y_seq, next_state = stack(x_seq, state, route_ids=route_ids)
    assert y_seq.shape == x_seq.shape

    x_step = torch.randn(batch_size, 32)
    y_step, _ = stack.step(x_step, next_state, route_ids=route_ids)
    assert y_step.shape == x_step.shape


def test_routed_adapter_column_dsl_block_smoke() -> None:
    block = build_column_auto_block(
        d_hidden=32,
        pattern="AXMS",
        routed_adapter=RoutedAdapterConfig(num_slots=8, rank=4),
    )
    assert any(isinstance(module, RoutedAdapterLinear) for module in block.modules())

    batch_size, seq_len = 4, 3
    x = torch.randn(batch_size, seq_len, 32)
    state = block.init_state(batch=batch_size, device=x.device, dtype=x.dtype)
    route_ids = torch.tensor([0, 1, 2, 3], dtype=torch.long)

    with use_route_ids(route_ids):
        y, next_state = block(x, state)
    assert y.shape == x.shape
    assert next_state is not None


def test_routed_adapter_column_dsl_axon_optins_smoke() -> None:
    block = build_column_auto_block(
        d_hidden=32,
        pattern="X^M^S^",
        routed_adapter=RoutedAdapterConfig(num_slots=8, rank=4),
    )
    assert any(isinstance(module, RoutedAdapterLinear) for module in block.modules())

    batch_size, seq_len = 4, 3
    x = torch.randn(batch_size, seq_len, 32)
    state = block.init_state(batch=batch_size, device=x.device, dtype=x.dtype)
    route_ids = torch.tensor([0, 1, 2, 3], dtype=torch.long)

    with use_route_ids(route_ids):
        y, next_state = block(x, state)
    assert y.shape == x.shape
    assert next_state is not None


def test_routed_adapter_supports_xl_and_agalite_cells() -> None:
    for cell_cfg in (XLCellConfig(hidden_size=None, n_heads=4), AGaLiTeCellConfig(hidden_size=None, n_heads=4)):
        stack = build_cortex(
            CortexStackConfig(
                d_hidden=32,
                blocks=[PassThroughBlockConfig(cell=cell_cfg)],
                post_norm=False,
                compile_blocks=False,
                routed_adapter=RoutedAdapterConfig(num_slots=8, rank=4),
            )
        )
        batch_size, seq_len = 4, 3
        x_seq = torch.randn(batch_size, seq_len, 32)
        x_step = torch.randn(batch_size, 32)
        route_ids = torch.tensor([0, 1, 2, 3], dtype=torch.long)
        state = stack.init_state(batch=batch_size, device=x_seq.device, dtype=x_seq.dtype)

        y_seq, state = stack(x_seq, state, route_ids=route_ids)
        assert y_seq.shape == x_seq.shape
        y_step, _ = stack.step(x_step, state, route_ids=route_ids)
        assert y_step.shape == x_step.shape
