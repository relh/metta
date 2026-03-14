from __future__ import annotations

import pytest
import torch
from cortex import (
    LSTMCellConfig,
    MultiScaleLayerConfig,
    MultiScaleStackConfig,
    PassThroughScaffoldConfig,
    build_multiscale_stack,
    build_multiscale_stack_config,
)
from cortex.scaffolds import ColumnScaffold
from tensordict import TensorDict


def test_build_multiscale_stack_config_preserves_split_boundary() -> None:
    cfg = build_multiscale_stack_config(
        d_hidden=16,
        num_layers=3,
        num_inner_steps=4,
        periods=[1, 2, 4],
        layers=[[LSTMCellConfig()]] * 3,
        splits=["rl", "wm"],
        split_start_layer=1,
        post_norm=False,
        compile_scaffolds=False,
    )

    assert [layer.period for layer in cfg.layers] == [1, 2, 4]
    assert cfg.splits == ["rl", "wm"]
    assert cfg.split_start_layer == 1
    assert cfg.layers[0].scaffold is not cfg.layers[1].scaffold
    assert cfg.layers[1].scaffold is not cfg.layers[2].scaffold


def test_multiscale_stack_config_rejects_invalid_schedule() -> None:
    with pytest.raises(ValueError, match="divide"):
        MultiScaleStackConfig(
            d_hidden=8,
            num_inner_steps=4,
            splits=["rl", "wm"],
            split_start_layer=1,
            layers=[
                MultiScaleLayerConfig(
                    period=1,
                    scaffold=PassThroughScaffoldConfig(core=LSTMCellConfig().core),
                ),
                MultiScaleLayerConfig(
                    period=3,
                    scaffold=PassThroughScaffoldConfig(core=LSTMCellConfig().core),
                ),
            ],
            post_norm=False,
        )


def test_multiscale_stack_config_rejects_invalid_split_boundary() -> None:
    with pytest.raises(ValueError, match="split_start_layer"):
        MultiScaleStackConfig(
            d_hidden=8,
            num_inner_steps=4,
            splits=["rl", "wm"],
            split_start_layer=2,
            layers=[
                MultiScaleLayerConfig(
                    period=1,
                    scaffold=PassThroughScaffoldConfig(core=LSTMCellConfig().core),
                ),
                MultiScaleLayerConfig(
                    period=2,
                    scaffold=PassThroughScaffoldConfig(core=LSTMCellConfig().core),
                ),
            ],
            post_norm=False,
        )


def test_multiscale_stack_sequence_matches_step_unroll() -> None:
    torch.manual_seed(0)
    stack = build_multiscale_stack(
        d_hidden=12,
        num_layers=3,
        num_inner_steps=4,
        periods=[1, 2, 4],
        layers=[[LSTMCellConfig()]] * 3,
        splits=["rl", "wm", "sf"],
        split_start_layer=1,
        post_norm=False,
        compile_scaffolds=False,
    )

    x = torch.randn(3, 5, 12)
    outputs_seq, state_seq = stack(x, state=None)

    state = stack.init_state(batch=x.shape[0], device=x.device, dtype=x.dtype)
    output_lists = {key: [] for key in outputs_seq.keys()}
    for t in range(x.shape[1]):
        outputs_t, state = stack.step(x[:, t], state)
        for key in output_lists:
            output_lists[key].append(outputs_t.get(key))

    outputs_step = TensorDict(
        {key: torch.stack(values, dim=1) for key, values in output_lists.items()},
        batch_size=list(x.shape[:2]),
        device=x.device,
    )

    _assert_tensordict_close(outputs_seq, outputs_step)
    _assert_tensordict_close(state_seq, state)


def test_multiscale_stack_outputs_full_batch_and_towers_are_independent() -> None:
    torch.manual_seed(0)
    stack = build_multiscale_stack(
        d_hidden=10,
        num_layers=3,
        num_inner_steps=4,
        periods=[1, 2, 4],
        layers=[[LSTMCellConfig()]] * 3,
        splits=["rl", "wm"],
        split_start_layer=1,
        post_norm=False,
        compile_scaffolds=False,
    )

    x = torch.randn(4, 6, 10)
    outputs_before, _ = stack(x, state=None)

    assert outputs_before["multiscale_trunk_out"].shape == (4, 6, 10)
    assert outputs_before["multiscale_split_rl_out"].shape == (4, 6, 10)
    assert outputs_before["multiscale_split_wm_out"].shape == (4, 6, 10)

    rl_param = next(stack.split_layers["rl"].parameters())
    with torch.no_grad():
        rl_param.add_(1.0)

    outputs_after, _ = stack(x, state=None)

    assert not torch.allclose(outputs_before["multiscale_split_rl_out"], outputs_after["multiscale_split_rl_out"])
    torch.testing.assert_close(outputs_before["multiscale_split_wm_out"], outputs_after["multiscale_split_wm_out"])
    torch.testing.assert_close(outputs_before["multiscale_trunk_out"], outputs_after["multiscale_trunk_out"])


def test_multiscale_stack_parallel_matches_sequential_reference_with_resets() -> None:
    torch.manual_seed(0)
    stack = build_multiscale_stack(
        d_hidden=10,
        num_layers=4,
        num_inner_steps=8,
        periods=[1, 2, 4, 8],
        layers=[[LSTMCellConfig()]] * 4,
        splits=["rl", "wm", "sf"],
        split_start_layer=2,
        post_norm=False,
        compile_scaffolds=False,
    )

    warmup_x = torch.randn(3, 2, 10)
    _, warm_state = stack._forward_outer_loop(warmup_x, state=None)

    x = torch.randn(3, 5, 10)
    resets = torch.tensor(
        [
            [False, False, True, False, False],
            [False, True, False, False, False],
            [False, False, False, True, False],
        ],
        dtype=torch.bool,
    )

    outputs_parallel, state_parallel = stack(x, state=warm_state.clone(recurse=True), resets=resets)
    outputs_reference, state_reference = stack._forward_outer_loop(
        x,
        state=warm_state.clone(recurse=True),
        resets=resets,
    )

    _assert_tensordict_close(outputs_parallel, outputs_reference)
    _assert_tensordict_close(state_parallel, state_reference)


def test_multiscale_stack_compile_uses_column_expert_compile(monkeypatch: pytest.MonkeyPatch) -> None:
    if not hasattr(torch, "compile"):
        pytest.skip("torch.compile is unavailable")

    compiled_modules: list[torch.nn.Module] = []

    def fake_compile(module: torch.nn.Module) -> torch.nn.Module:
        compiled_modules.append(module)
        return module

    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    monkeypatch.setattr(torch, "compile", fake_compile)

    stack = build_multiscale_stack(
        d_hidden=8,
        num_layers=3,
        num_inner_steps=4,
        periods=[1, 2, 4],
        layers=[[LSTMCellConfig(), LSTMCellConfig()]] * 3,
        splits=["rl", "wm"],
        split_start_layer=1,
        post_norm=False,
        compile_scaffolds=True,
    )

    all_layers = list(stack.shared_layers) + [
        layer for split_layers in stack.split_layers.values() for layer in split_layers
    ]
    assert all(isinstance(layer, ColumnScaffold) for layer in all_layers)
    assert stack._compiled_shared_layers == list(stack.shared_layers)
    assert stack._compiled_split_layers is not None
    assert all(
        stack._compiled_split_layers[split] == list(split_layers) for split, split_layers in stack.split_layers.items()
    )

    for layer in all_layers:
        assert layer._compiled_experts is not None

    expected_compiles = sum(len(layer.experts) for layer in all_layers)
    assert len(compiled_modules) == expected_compiles
    assert all(not isinstance(module, ColumnScaffold) for module in compiled_modules)


def _assert_tensordict_close(actual: TensorDict, expected: TensorDict) -> None:
    assert type(actual) is type(expected)
    for key, actual_leaf in actual.items(include_nested=True, leaves_only=True):
        expected_leaf = expected.get(key)
        assert isinstance(actual_leaf, torch.Tensor)
        assert isinstance(expected_leaf, torch.Tensor)
        torch.testing.assert_close(actual_leaf, expected_leaf)
