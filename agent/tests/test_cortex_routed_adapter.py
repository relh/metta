from __future__ import annotations

from types import SimpleNamespace

import pytest
import torch
from cortex import CortexStackConfig, LSTMCoreConfig, PassThroughScaffoldConfig, RoutedAdapterConfig
from tensordict import TensorDict

from metta.agent.components.cortex import CortexTD, CortexTDConfig
from metta.agent.utils import ensure_sequence_metadata


def _make_component(*, num_slots: int, num_agents_per_env: int = 8) -> CortexTD:
    stack_cfg = CortexStackConfig(
        d_hidden=16,
        scaffolds=[PassThroughScaffoldConfig(core=LSTMCoreConfig(hidden_size=16, num_layers=1))],
        post_norm=False,
        compile_blocks=False,
        routed_adapter=RoutedAdapterConfig(num_slots=num_slots, rank=2),
    )
    component = CortexTD(
        CortexTDConfig(
            in_key="core_in",
            out_key="core_out",
            d_hidden=16,
            stack_cfg=stack_cfg,
        )
    )
    component.initialize_to_environment(SimpleNamespace(num_agents=num_agents_per_env), torch.device("cpu"))
    return component


def _make_rollout_td(agent_slot_ids: torch.Tensor) -> TensorDict:
    batch_size = int(agent_slot_ids.numel())
    td = TensorDict(
        {
            "core_in": torch.randn(batch_size, 16),
            "dones": torch.zeros(batch_size),
            "truncateds": torch.zeros(batch_size),
            "agent_slot_ids": agent_slot_ids.view(batch_size, 1),
        },
        batch_size=[batch_size],
    )
    ensure_sequence_metadata(td, batch_size=batch_size, time_steps=1)
    return td


def _make_training_td(agent_slot_ids: torch.Tensor, *, time_steps: int) -> TensorDict:
    batch_size = int(agent_slot_ids.numel())
    flat_agent_slot_ids = agent_slot_ids.repeat_interleave(time_steps)
    row_ids = torch.arange(batch_size, dtype=torch.long).repeat_interleave(time_steps)
    td = TensorDict(
        {
            "core_in": torch.randn(batch_size * time_steps, 16),
            "row_id": row_ids,
            "agent_slot_ids": flat_agent_slot_ids.view(-1, 1),
        },
        batch_size=[batch_size * time_steps],
    )
    ensure_sequence_metadata(td, batch_size=batch_size, time_steps=time_steps)
    return td


@pytest.mark.parametrize(
    ("num_slots", "expected_route_ids"),
    [
        (8, [0, 1, 2, 3, 0, 1, 2, 3]),
        (2, [0, 1, 0, 1, 0, 1, 0, 1]),
    ],
)
def test_cortex_routed_adapter_uses_within_env_index_in_step_mode(
    num_slots: int, expected_route_ids: list[int]
) -> None:
    component = _make_component(num_slots=num_slots, num_agents_per_env=8)
    captured_route_ids: list[torch.Tensor] = []
    original_step = component.stack.step

    def capture_step(x: torch.Tensor, state=None, **kwargs):  # type: ignore[no-untyped-def]
        route_ids = kwargs.get("route_ids")
        assert route_ids is not None
        captured_route_ids.append(route_ids.detach().cpu().clone())
        return original_step(x, state, **kwargs)

    component.stack.step = capture_step  # type: ignore[method-assign]

    td = _make_rollout_td(torch.tensor([0, 1, 2, 3, 8, 9, 10, 11], dtype=torch.long))
    out = component(td)

    assert out["core_out"].shape == torch.Size([8, 16])
    assert captured_route_ids
    torch.testing.assert_close(captured_route_ids[-1], torch.tensor(expected_route_ids, dtype=torch.long))


def test_cortex_routed_adapter_uses_within_env_index_in_sequence_mode() -> None:
    component = _make_component(num_slots=2, num_agents_per_env=8)
    captured_route_ids: list[torch.Tensor] = []
    original_forward = component.stack.forward

    def capture_forward(x: torch.Tensor, state=None, **kwargs):  # type: ignore[no-untyped-def]
        route_ids = kwargs.get("route_ids")
        assert route_ids is not None
        captured_route_ids.append(route_ids.detach().cpu().clone())
        return original_forward(x, state, **kwargs)

    component.stack.forward = capture_forward  # type: ignore[method-assign]

    td = _make_training_td(torch.tensor([0, 1, 8, 9], dtype=torch.long), time_steps=3)
    out = component(td)

    assert out["core_out"].shape == torch.Size([12, 16])
    assert captured_route_ids
    torch.testing.assert_close(captured_route_ids[-1], torch.tensor([0, 1, 0, 1], dtype=torch.long))


def test_cortex_routed_adapter_prefers_explicit_route_ids() -> None:
    component = _make_component(num_slots=8, num_agents_per_env=8)
    captured_route_ids: list[torch.Tensor] = []
    original_step = component.stack.step

    def capture_step(x: torch.Tensor, state=None, **kwargs):  # type: ignore[no-untyped-def]
        route_ids = kwargs.get("route_ids")
        assert route_ids is not None
        captured_route_ids.append(route_ids.detach().cpu().clone())
        return original_step(x, state, **kwargs)

    component.stack.step = capture_step  # type: ignore[method-assign]

    td = _make_rollout_td(torch.tensor([0, 1, 2, 3], dtype=torch.long))
    td.set("cortex_route_ids", torch.tensor([[7], [6], [5], [4]], dtype=torch.long))
    out = component(td)

    assert out["core_out"].shape == torch.Size([4, 16])
    assert captured_route_ids
    torch.testing.assert_close(captured_route_ids[-1], torch.tensor([7, 6, 5, 4], dtype=torch.long))


def test_cortex_routed_adapter_requires_agent_slot_ids() -> None:
    component = _make_component(num_slots=2, num_agents_per_env=8)
    td = TensorDict({"core_in": torch.randn(2, 16)}, batch_size=[2])
    ensure_sequence_metadata(td, batch_size=2, time_steps=1)

    with pytest.raises(KeyError, match="agent_slot_ids"):
        component(td)


def test_cortex_routed_adapter_validates_num_slots_vs_num_agents() -> None:
    stack_cfg = CortexStackConfig(
        d_hidden=16,
        scaffolds=[PassThroughScaffoldConfig(core=LSTMCoreConfig(hidden_size=16, num_layers=1))],
        post_norm=False,
        compile_blocks=False,
        routed_adapter=RoutedAdapterConfig(num_slots=9, rank=2),
    )
    component = CortexTD(
        CortexTDConfig(
            in_key="core_in",
            out_key="core_out",
            d_hidden=16,
            stack_cfg=stack_cfg,
        )
    )

    with pytest.raises(ValueError, match="num_slots"):
        component.initialize_to_environment(SimpleNamespace(num_agents=8), torch.device("cpu"))
