import torch
from tensordict import TensorDict
from torchrl.data import Composite, UnboundedContinuous, UnboundedDiscrete

from metta.rl.training.experience import Experience


def _make_step_td(start: int, stop: int) -> TensorDict:
    n = stop - start
    agent_ids = torch.arange(start, stop, dtype=torch.int64)
    return TensorDict(
        {
            "reward_baseline": torch.zeros(n, dtype=torch.float32),
            "agent_slot_ids": agent_ids.view(n, 1),
            "rewards": torch.ones(n, dtype=torch.float32),
        },
        batch_size=[n],
    )


def test_experience_store_supports_mixed_t_in_row_with_async_batches() -> None:
    # segments == total_agents: one replay row per agent.
    #
    # We purposely create a store call where agents in the same batch are at different
    # t_in_row offsets (async / partial env batches).
    exp = Experience(
        total_agents=4,
        batch_size=8,
        bptt_horizon=2,
        minibatch_size=4,
        max_minibatch_size=4,
        experience_spec=Composite(
            {
                "reward_baseline": UnboundedContinuous(shape=torch.Size([]), dtype=torch.float32),
                "agent_slot_ids": UnboundedDiscrete(shape=torch.Size([1]), dtype=torch.int64),
                "rewards": UnboundedContinuous(shape=torch.Size([]), dtype=torch.float32),
            }
        ),
        device="cpu",
    )
    exp.reset_for_rollout()

    exp.store(_make_step_td(0, 2), slice(0, 2))
    exp.store(_make_step_td(0, 4), slice(0, 4))
    # Agents 0..1 are done; a mixed done/active store should only write agents 2..3.
    exp.store(_make_step_td(0, 4), slice(0, 4))

    assert exp.ready_for_training
    assert exp.full_rows == exp.segments

    agent_slot_ids = exp.buffer["agent_slot_ids"][:, :, 0]
    assert bool((agent_slot_ids == agent_slot_ids[:, :1]).all())
