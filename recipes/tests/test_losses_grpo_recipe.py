from __future__ import annotations

import inspect

from recipes.experiment.losses import grpo


def test_grpo_train_shaped_signature_exposes_only_rewards() -> None:
    params = inspect.signature(grpo.train_shaped).parameters
    assert list(params) == ["rewards"]


def test_grpo_train_shaped_wires_grpo_loss() -> None:
    tool = grpo.train_shaped(rewards=False)
    assert set(tool.trainer.losses.losses) == {"ppo_actor", "ppo_critic", "grpo"}
