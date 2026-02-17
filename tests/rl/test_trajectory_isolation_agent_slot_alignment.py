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


def test_slice_row_indices_handles_unordered_agent_slot_ids() -> None:
    isolator, runtime_slices = _build_agent_count_runtime()
    miner_slice = runtime_slices["miner"]
    aligner_slice = runtime_slices["aligner"]
    experience = SimpleNamespace(
        buffer=TensorDict(
            {"agent_slot_ids": torch.tensor([4, 0, 12, 8, 7, 15, 1, 9], dtype=torch.long).view(8, 1, 1)},
            batch_size=[8, 1],
            device=torch.device("cpu"),
        ),
        device=torch.device("cpu"),
    )

    miner_rows = isolator._slice_row_indices(experience, miner_slice)
    aligner_rows = isolator._slice_row_indices(experience, aligner_slice)
    torch.testing.assert_close(miner_rows, torch.tensor([1, 3, 6, 7], dtype=torch.long))
    torch.testing.assert_close(aligner_rows, torch.tensor([0, 2, 4, 5], dtype=torch.long))


def test_slice_row_indices_cached_per_slice() -> None:
    isolator, runtime_slices = _build_agent_count_runtime()
    miner_slice = runtime_slices["miner"]
    experience = SimpleNamespace(
        buffer=TensorDict(
            {"agent_slot_ids": torch.arange(16, dtype=torch.long).view(16, 1, 1)},
            batch_size=[16, 1],
            device=torch.device("cpu"),
        ),
        device=torch.device("cpu"),
    )

    first = isolator._slice_row_indices(experience, miner_slice)
    second = isolator._slice_row_indices(experience, miner_slice)
    assert first.data_ptr() == second.data_ptr()


def test_slice_row_indices_out_of_range_slots_fallback() -> None:
    isolator, runtime_slices = _build_agent_count_runtime()
    miner_slice = runtime_slices["miner"]
    experience = SimpleNamespace(
        buffer=TensorDict(
            {"agent_slot_ids": torch.tensor([0, 99], dtype=torch.long).view(2, 1, 1)},
            batch_size=[2, 1],
            device=torch.device("cpu"),
        ),
        device=torch.device("cpu"),
    )

    miner_rows = isolator._slice_row_indices(experience, miner_slice)
    torch.testing.assert_close(miner_rows, torch.tensor([0], dtype=torch.long))


def test_split_rollout_td_uses_shallow_policy_clones() -> None:
    cfg = TrajectoryIsolationSliceConfig(
        name="default",
        env_ratio=1.0,
        policies=["learner0", "teacher"],
        losses=["ppo_actor"],
    )
    runtime_slice = TrajectoryIsolationSliceRuntime(
        cfg=cfg,
        lower=0.0,
        upper=1.0,
        env_mask=torch.tensor([True, True, False, False]),
    )
    rollout_td = TensorDict(
        {
            "agent_slot_ids": torch.arange(4, dtype=torch.long).view(-1, 1),
            "rewards": torch.arange(4, dtype=torch.float32),
        },
        batch_size=[4],
        device=torch.device("cpu"),
    )

    split_td, _ = runtime_slice._split_rollout_td_per_slice(
        td=rollout_td,
        training_env_id=slice(0, 4),
        context=SimpleNamespace(),
    )
    assert split_td is not None

    learner_td = split_td["learner0"]
    teacher_td = split_td["teacher"]

    # Input tensors should be shared across policy views to avoid deep clones.
    assert learner_td["agent_slot_ids"].data_ptr() == teacher_td["agent_slot_ids"].data_ptr()
    assert learner_td["rewards"].data_ptr() == teacher_td["rewards"].data_ptr()

    # Policy containers remain independent for outputs.
    learner_td["actions"] = torch.zeros(learner_td.batch_size, dtype=torch.int32)
    assert "actions" not in teacher_td.keys()


def test_build_rollout_policy_batches_single_slice_fast_path() -> None:
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
        env_mask=torch.tensor([True, True], dtype=torch.bool),
    )
    isolator._slice_plan = [runtime_slice]
    isolator._all_policies = {"learner0"}
    isolator._policy_to_slices = {"learner0": [runtime_slice]}

    policy_td = TensorDict(
        {"agent_slot_ids": torch.arange(2, dtype=torch.long).view(-1, 1)},
        batch_size=[2],
        device=torch.device("cpu"),
    )
    isolator._slice_tds_rollout_step = {
        "default": TensorDict({"learner0": policy_td}, batch_size=[2], device=torch.device("cpu"))
    }

    batches = isolator.build_rollout_policy_batches()
    assert len(batches) == 1
    assert batches[0].stitched_td is policy_td

    batches[0].stitched_td["actions"] = torch.zeros(2, dtype=torch.int32)
    isolator.apply_rollout_policy_batch(batches[0])
    updated = isolator._slice_tds_rollout_step["default"]["learner0"]
    assert updated is batches[0].stitched_td
    assert "actions" in updated.keys()


def test_writeback_rollout_tds_uses_direct_mode_for_compatible_shapes() -> None:
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
    isolator._slice_masks_rollout_step = {"default": mask}
    isolator._slice_tds_rollout_step = {
        "default": TensorDict(
            {
                "actions": torch.tensor([7, 9], dtype=torch.int32),
                "values": torch.tensor([[1.0, 2.0], [3.0, 4.0]], dtype=torch.float32),
            },
            batch_size=[2],
            device=torch.device("cpu"),
        )
    }

    rollout_td = TensorDict(
        {
            "actions": torch.full((4,), -1, dtype=torch.int32),
            "values": torch.full((4, 2), -1.0, dtype=torch.float32),
        },
        batch_size=[4],
        device=torch.device("cpu"),
    )

    isolator.writeback_rollout_tds(rollout_td)

    assert isolator._slice_writeback_mode["default"] == "direct"
    torch.testing.assert_close(rollout_td["actions"][mask], torch.tensor([7, 9], dtype=torch.int32))
    torch.testing.assert_close(rollout_td["values"][mask], torch.tensor([[1.0, 2.0], [3.0, 4.0]]))
    torch.testing.assert_close(rollout_td["actions"][~mask], torch.tensor([-1, -1], dtype=torch.int32))


def test_writeback_rollout_tds_falls_back_to_pad_mode_for_shape_mismatch() -> None:
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
    isolator._slice_masks_rollout_step = {"default": mask}
    isolator._slice_tds_rollout_step = {
        "default": TensorDict(
            {"obs": torch.tensor([[1.0, 2.0], [3.0, 4.0]], dtype=torch.float32)},
            batch_size=[2],
            device=torch.device("cpu"),
        )
    }

    rollout_td = TensorDict(
        {"obs": torch.full((4, 3), 9.0, dtype=torch.float32)},
        batch_size=[4],
        device=torch.device("cpu"),
    )

    isolator.writeback_rollout_tds(rollout_td)

    assert isolator._slice_writeback_mode["default"] == "pad"
    torch.testing.assert_close(
        rollout_td["obs"][mask],
        torch.tensor([[1.0, 2.0, 9.0], [3.0, 4.0, 9.0]], dtype=torch.float32),
    )
    torch.testing.assert_close(
        rollout_td["obs"][~mask],
        torch.tensor([[9.0, 9.0, 9.0], [9.0, 9.0, 9.0]], dtype=torch.float32),
    )
