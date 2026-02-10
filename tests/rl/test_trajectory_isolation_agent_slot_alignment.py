from __future__ import annotations

from types import SimpleNamespace

import torch
from tensordict import TensorDict

from metta.rl.training.trajectory_isolation import (
    TrajectoryIsolationConfig,
    TrajectoryIsolationSliceConfig,
    TrajectoryIsolationSliceRuntime,
    TrajectoryIsolator,
)


def _build_agent_count_runtime() -> tuple[TrajectoryIsolator, dict[str, TrajectoryIsolationSliceRuntime]]:
    config = TrajectoryIsolationConfig(
        slicing_method="agent_count",
        num_agents_per_env=8,
        slices=[
            TrajectoryIsolationSliceConfig(name="miner", agent_count=4, policies=["learner0"], losses=["ppo_actor"]),
            TrajectoryIsolationSliceConfig(
                name="aligner",
                agent_count=4,
                policies=["learner0"],
                losses=["ppo_critic"],
            ),
        ],
    )
    isolator = TrajectoryIsolator(config=config)
    isolator._context = SimpleNamespace(
        experience=SimpleNamespace(total_agents=16),
        device=torch.device("cpu"),
        training_env_id=None,
    )
    runtime_slices = {runtime_slice.name: runtime_slice for runtime_slice in isolator._build_plan_agent_count()}
    return isolator, runtime_slices


def _make_rollout_td(start: int, stop: int) -> TensorDict:
    agent_slot_ids = torch.arange(start, stop, dtype=torch.long)
    return TensorDict(
        {"agent_slot_ids": agent_slot_ids.view(-1, 1)},
        batch_size=[agent_slot_ids.numel()],
        device=torch.device("cpu"),
    )


def test_agent_count_slice_masks_align_with_agent_slot_windows() -> None:
    isolator, runtime_slices = _build_agent_count_runtime()
    miner_slice = runtime_slices["miner"]
    aligner_slice = runtime_slices["aligner"]
    context = SimpleNamespace()

    rollout_td_env1 = _make_rollout_td(8, 16)
    miner_td, miner_mask = miner_slice._split_rollout_td_per_slice(
        td=rollout_td_env1,
        training_env_id=slice(8, 16),
        context=context,
    )
    aligner_td, aligner_mask = aligner_slice._split_rollout_td_per_slice(
        td=rollout_td_env1,
        training_env_id=slice(8, 16),
        context=context,
    )

    assert miner_td is not None and miner_mask is not None
    assert aligner_td is not None and aligner_mask is not None
    torch.testing.assert_close(miner_mask, torch.tensor([True, True, True, True, False, False, False, False]))
    torch.testing.assert_close(aligner_mask, torch.tensor([False, False, False, False, True, True, True, True]))
    torch.testing.assert_close(miner_td["learner0"]["agent_slot_ids"].squeeze(-1), torch.tensor([8, 9, 10, 11]))
    torch.testing.assert_close(aligner_td["learner0"]["agent_slot_ids"].squeeze(-1), torch.tensor([12, 13, 14, 15]))

    rollout_td_all = _make_rollout_td(0, 16)
    miner_all_td, miner_all_mask = miner_slice._split_rollout_td_per_slice(
        td=rollout_td_all,
        training_env_id=slice(0, 16),
        context=context,
    )
    aligner_all_td, aligner_all_mask = aligner_slice._split_rollout_td_per_slice(
        td=rollout_td_all,
        training_env_id=slice(0, 16),
        context=context,
    )

    assert miner_all_td is not None and miner_all_mask is not None
    assert aligner_all_td is not None and aligner_all_mask is not None
    torch.testing.assert_close(
        miner_all_td["learner0"]["agent_slot_ids"].squeeze(-1),
        torch.tensor([0, 1, 2, 3, 8, 9, 10, 11]),
    )
    torch.testing.assert_close(
        aligner_all_td["learner0"]["agent_slot_ids"].squeeze(-1),
        torch.tensor([4, 5, 6, 7, 12, 13, 14, 15]),
    )

    experience = SimpleNamespace(
        buffer=TensorDict(
            {"agent_slot_ids": torch.arange(16, dtype=torch.long).view(16, 1, 1)},
            batch_size=[16, 1],
            device=torch.device("cpu"),
        ),
        device=torch.device("cpu"),
    )
    miner_rows = isolator._slice_row_indices(experience, miner_slice)
    aligner_rows = isolator._slice_row_indices(experience, aligner_slice)
    torch.testing.assert_close(miner_rows, torch.tensor([0, 1, 2, 3, 8, 9, 10, 11], dtype=torch.long))
    torch.testing.assert_close(aligner_rows, torch.tensor([4, 5, 6, 7, 12, 13, 14, 15], dtype=torch.long))
