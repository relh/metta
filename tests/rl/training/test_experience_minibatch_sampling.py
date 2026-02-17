from __future__ import annotations

import torch
from torchrl.data import Composite, UnboundedContinuous, UnboundedDiscrete

from metta.rl.trainer_config import TrainerConfig
from metta.rl.training.experience import Experience


def test_sample_from_indices_minibatch_mutation_does_not_corrupt_buffer() -> None:
    # Regression test: minibatch sampling must not return views into the rollout buffer.
    # If this ever becomes view-based, in-place writes during training could silently corrupt rollouts.
    device = torch.device("cpu")

    total_agents = 4
    batch_size = 8
    bptt_horizon = 2
    minibatch_size = 4
    max_minibatch_size = 4
    segments = batch_size // bptt_horizon

    experience_spec = Composite(
        actions=UnboundedDiscrete(shape=torch.Size([]), dtype=torch.int64),
        rewards=UnboundedContinuous(shape=torch.Size([]), dtype=torch.float32),
    )
    exp = Experience(
        total_agents=total_agents,
        batch_size=batch_size,
        bptt_horizon=bptt_horizon,
        minibatch_size=minibatch_size,
        max_minibatch_size=max_minibatch_size,
        experience_spec=experience_spec,
        device=device,
    )

    # Fill with distinct values to make corruption obvious.
    exp.buffer["actions"][:] = torch.arange(segments * bptt_horizon, dtype=torch.int64).reshape(segments, bptt_horizon)
    exp.buffer["rewards"][:] = torch.arange(segments * bptt_horizon, dtype=torch.float32).reshape(
        segments, bptt_horizon
    )

    base_actions = exp.buffer["actions"].clone()
    base_rewards = exp.buffer["rewards"].clone()

    indices = torch.arange(segments, dtype=torch.int64)
    advantages = torch.zeros((segments, bptt_horizon), dtype=torch.float32)
    sampling_config = TrainerConfig().sampling

    mb = exp.sample_from_indices(
        indices=indices,
        ordered_indices=None,
        count=2,
        mb_idx=0,
        advantages=advantages,
        sampling_config=sampling_config,
        epoch=0,
        total_timesteps=0,
        batch_size=batch_size,
    )["sampled_mb"]

    mb["actions"].fill_(-1)
    mb["rewards"].fill_(-2.0)

    assert torch.equal(exp.buffer["actions"], base_actions)
    assert torch.equal(exp.buffer["rewards"], base_rewards)


def test_sample_indices_and_weights_matches_sample_from_indices_sequential() -> None:
    device = torch.device("cpu")

    total_agents = 4
    batch_size = 8
    bptt_horizon = 2
    minibatch_size = 4
    max_minibatch_size = 4
    segments = batch_size // bptt_horizon

    experience_spec = Composite(
        actions=UnboundedDiscrete(shape=torch.Size([]), dtype=torch.int64),
        rewards=UnboundedContinuous(shape=torch.Size([]), dtype=torch.float32),
    )
    exp = Experience(
        total_agents=total_agents,
        batch_size=batch_size,
        bptt_horizon=bptt_horizon,
        minibatch_size=minibatch_size,
        max_minibatch_size=max_minibatch_size,
        experience_spec=experience_spec,
        device=device,
    )

    exp.buffer["actions"][:] = torch.arange(segments * bptt_horizon, dtype=torch.int64).reshape(segments, bptt_horizon)
    exp.buffer["rewards"][:] = torch.arange(segments * bptt_horizon, dtype=torch.float32).reshape(
        segments, bptt_horizon
    )

    indices = torch.arange(segments, dtype=torch.int64)
    advantages = torch.arange(segments * bptt_horizon, dtype=torch.float32).reshape(segments, bptt_horizon)
    sampling_config = TrainerConfig().sampling

    sampled_idx, prio_weights = exp.sample_indices_and_weights(
        indices=indices,
        ordered_indices=None,
        count=2,
        mb_idx=0,
        advantages=advantages,
        sampling_config=sampling_config,
        epoch=0,
        total_timesteps=0,
        batch_size=batch_size,
    )

    mb_full = exp.sample_from_indices(
        indices=indices,
        ordered_indices=None,
        count=2,
        mb_idx=0,
        advantages=advantages,
        sampling_config=sampling_config,
        epoch=0,
        total_timesteps=0,
        batch_size=batch_size,
    )

    assert sampled_idx.dtype == torch.long
    assert prio_weights.shape == (2, bptt_horizon)
    torch.testing.assert_close(mb_full["prio_weights"], prio_weights)
    torch.testing.assert_close(mb_full["indices"][:, 0], sampled_idx)
    torch.testing.assert_close(mb_full["advantages"], advantages[sampled_idx])
    torch.testing.assert_close(mb_full["sampled_mb"]["actions"], exp.buffer["actions"][sampled_idx])
