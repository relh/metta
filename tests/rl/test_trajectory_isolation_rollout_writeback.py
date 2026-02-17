from __future__ import annotations

import torch
from tensordict import TensorDict

from metta.rl.training.trajectory_isolation import (
    TrajectoryIsolationConfig,
    TrajectoryIsolationSliceConfig,
    TrajectoryIsolationSliceRuntime,
    TrajectoryIsolator,
)


def test_rollout_writeback_skips_aliased_inputs_and_writes_outputs() -> None:
    batch_size = 4
    config = TrajectoryIsolationConfig(
        slices=[
            TrajectoryIsolationSliceConfig(
                name="default",
                env_ratio=1.0,
                policies=["learner0"],
                losses=["ppo_actor"],
            )
        ]
    )
    isolator = TrajectoryIsolator(config=config)
    runtime_slice = TrajectoryIsolationSliceRuntime(
        cfg=config.slices[0],
        lower=0.0,
        upper=1.0,
        env_mask=torch.tensor([True, True, True, True], dtype=torch.bool),
    )
    mask = torch.tensor([True, False, True, False], dtype=torch.bool)
    isolator._slice_plan = [runtime_slice]

    rollout_td = TensorDict(
        {
            "env_obs": torch.randn(batch_size, 4),
            "rewards": torch.zeros(batch_size, 1),
        },
        batch_size=[batch_size],
    )
    base_td = rollout_td[mask]
    policy_td = base_td.clone(recurse=False)
    # New output key: does not alias rollout storage and must be written back.
    policy_td.set("actions", torch.tensor([7, 9], dtype=torch.long))
    # Replaced key: does not alias rollout storage and must be written back.
    policy_td.set("rewards", torch.ones_like(policy_td["rewards"]))

    isolator._slice_tds_rollout_step = {runtime_slice.name: policy_td}
    isolator._slice_masks_rollout_step = {runtime_slice.name: mask}

    isolator.writeback_rollout_tds(rollout_td=rollout_td)

    assert "actions" in rollout_td.keys()
    torch.testing.assert_close(rollout_td["actions"][mask], torch.tensor([7, 9], dtype=torch.long))
    torch.testing.assert_close(rollout_td["actions"][~mask], torch.zeros(2, dtype=torch.long))
    torch.testing.assert_close(rollout_td["rewards"][mask], torch.ones(2, 1))
    torch.testing.assert_close(rollout_td["rewards"][~mask], torch.zeros(2, 1))
