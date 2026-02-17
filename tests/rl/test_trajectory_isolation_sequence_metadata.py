import torch
from tensordict import TensorDict

from metta.rl.training.trajectory_isolation import (
    TrajectoryIsolationSliceConfig,
    TrajectoryIsolationSliceRuntime,
    TrajectoryIsolator,
    default_trajectory_isolation_config,
)


def _mk_policy_td(batch: int) -> TensorDict:
    td = TensorDict(
        {
            "obs": torch.zeros((batch, 4), dtype=torch.float32),
            # Pre-existing metadata (will be wrong after cat/split unless overwritten).
            "batch": torch.full((batch,), batch, dtype=torch.long),
            "bptt": torch.ones((batch,), dtype=torch.long),
        },
        batch_size=(batch,),
    )
    return td


def test_rollout_policy_batch_metadata_overwritten_after_stitch_and_split() -> None:
    # Regression: after stitching policy batches (cat) and splitting them back,
    # sequence metadata must reflect the new geometry (not the pre-stitch values).
    device = torch.device("cpu")

    cfg1 = TrajectoryIsolationSliceConfig(name="s1", env_ratio=0.5, policies=["learner0"], losses=["ppo_actor"])
    cfg2 = TrajectoryIsolationSliceConfig(name="s2", env_ratio=0.5, policies=["learner0"], losses=["ppo_actor"])
    s1 = TrajectoryIsolationSliceRuntime(cfg=cfg1, lower=0.0, upper=0.5, env_mask=torch.tensor([True], device=device))
    s2 = TrajectoryIsolationSliceRuntime(cfg=cfg2, lower=0.5, upper=1.0, env_mask=torch.tensor([True], device=device))

    isolator = TrajectoryIsolator(config=default_trajectory_isolation_config())
    isolator._all_policies = {"learner0"}
    isolator._policy_to_slices = {"learner0": [s1, s2]}
    isolator._slice_tds_rollout_step = {
        "s1": TensorDict({"learner0": _mk_policy_td(2)}, batch_size=(2,), device=device),
        "s2": TensorDict({"learner0": _mk_policy_td(3)}, batch_size=(3,), device=device),
    }

    batches = isolator.build_rollout_policy_batches()
    assert len(batches) == 1
    batch = batches[0]

    stitched = batch.stitched_td
    assert stitched.batch_size == torch.Size([5])
    assert stitched["batch"].unique().tolist() == [5]
    assert stitched["bptt"].unique().tolist() == [1]

    isolator.apply_rollout_policy_batch(batch)
    td1 = isolator._slice_tds_rollout_step["s1"]["learner0"]
    td2 = isolator._slice_tds_rollout_step["s2"]["learner0"]
    assert td1.batch_size == torch.Size([2])
    assert td2.batch_size == torch.Size([3])
    assert td1["batch"].unique().tolist() == [2]
    assert td2["batch"].unique().tolist() == [3]


def test_split_rollout_td_per_slice_overwrites_parent_metadata() -> None:
    device = torch.device("cpu")

    cfg = TrajectoryIsolationSliceConfig(name="s", env_ratio=1.0, policies=["learner0"], losses=["ppo_actor"])
    # Select 2/5 agents.
    runtime_slice = TrajectoryIsolationSliceRuntime(
        cfg=cfg,
        lower=0.0,
        upper=1.0,
        env_mask=torch.tensor([True, True, False, False, False], device=device),
    )

    parent = TensorDict(
        {
            "obs": torch.zeros((5, 4), dtype=torch.float32),
            # Parent metadata: batch=5.
            "batch": torch.full((5,), 5, dtype=torch.long),
            "bptt": torch.ones((5,), dtype=torch.long),
        },
        batch_size=(5,),
        device=device,
    )

    slice_td, slice_mask = runtime_slice._split_rollout_td_per_slice(
        td=parent,
        training_env_id=slice(None),
        context=None,
    )
    assert slice_mask is not None
    assert int(slice_mask.sum().item()) == 2
    assert slice_td is not None
    inner = slice_td["learner0"]
    assert inner.batch_size == torch.Size([2])
    assert inner["batch"].unique().tolist() == [2]
