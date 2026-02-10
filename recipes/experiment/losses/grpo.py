"""Arena recipe with GRPO (Group Relative Policy Optimization) for comparison testing."""

from __future__ import annotations

import metta.tools as tools
from metta.agent.policies.vit_grpo import ViTGRPOConfig
from metta.rl.loss.grpo import GRPOConfig
from metta.rl.loss.losses import LossesConfig
from metta.rl.loss.ppo_actor import PPOActorConfig
from metta.rl.loss.ppo_critic import PPOCriticConfig
from metta.rl.policy_assets import OptimizerConfig, PolicyAssetConfig
from metta.rl.trainer_config import TrainerConfig
from metta.rl.training import EvaluatorConfig, TrainingEnvironmentConfig

# Import everything from the base arena recipe
from recipes.experiment.arena import (
    make_curriculum,
    simulations,
)
from recipes.experiment.arena import train_shaped as base_train_shaped
from recipes.prod.arena_basic_easy_shaped import (
    train as arena_basic_easy_shaped_train,
)


def train() -> tools.TrainTool:
    """Train with GRPO loss (critic-free, group-based advantages).

    GRPO eliminates the value network and computes advantages by comparing
    each trajectory's return against the mean return of a group of sampled
    trajectories. This can be more sample efficient and stable than PPO
    in certain environments.
    """
    curriculum = make_curriculum()

    # Configure GRPO loss
    grpo_config = GRPOConfig(
        clip_coef=0.2,
        ent_coef=0.01,
        gamma=0.99,
        group_size=4,
        norm_adv=True,
        target_kl=None,
    )

    # Configure optimizer
    optimizer_config = OptimizerConfig(
        type="adamw_schedulefree",
        learning_rate=0.01,
        beta1=0.9,
        beta2=0.999,
        eps=3.186531e-07,
        weight_decay=0.01,
        warmup_steps=2000,
    )

    trainer_config = TrainerConfig(
        losses=LossesConfig(
            losses={
                "ppo_actor": PPOActorConfig(),
                "ppo_critic": PPOCriticConfig(),
                "grpo": grpo_config,
            }
        ),
        total_timesteps=50_000_000_000,
    )

    tt = tools.TrainTool(
        training_env=TrainingEnvironmentConfig(curriculum=curriculum),
        trainer=trainer_config,
        evaluator=EvaluatorConfig(simulations=simulations()),
        policy_assets={"learner0": PolicyAssetConfig(architecture=ViTGRPOConfig())},
    )
    tt.policy_assets["learner0"].optimizer = optimizer_config
    return tt


def train_shaped(rewards: bool = True, converters: bool = True) -> tools.TrainTool:
    """Train with GRPO loss on shaped rewards task.

    This provides easier training with reward shaping and converters enabled,
    using the critic-free GRPO algorithm.
    """

    # Get the base shaped training tool
    base_tool = base_train_shaped(rewards=rewards)

    # Configure GRPO loss
    grpo_config = GRPOConfig(
        clip_coef=0.2,
        ent_coef=0.01,
        gamma=0.99,
        group_size=4,
        norm_adv=True,
        target_kl=None,
    )

    loss_config = LossesConfig(
        losses={
            "ppo_actor": PPOActorConfig(),
            "ppo_critic": PPOCriticConfig(),
            "grpo": grpo_config,
        }
    )

    # Configure optimizer
    optimizer_config = OptimizerConfig(
        type="adamw_schedulefree",
        learning_rate=0.01,
        beta1=0.9,
        beta2=0.999,
        eps=3.186531e-07,
        weight_decay=0.01,
        warmup_steps=2000,
    )

    trainer_config = TrainerConfig(
        losses=loss_config,
        total_timesteps=50_000_000_000,
    )

    tt = tools.TrainTool(
        training_env=base_tool.training_env,
        trainer=trainer_config,
        evaluator=base_tool.evaluator,
        policy_assets={"learner0": PolicyAssetConfig(architecture=ViTGRPOConfig())},
    )
    tt.policy_assets["learner0"].optimizer = optimizer_config
    return tt


def basic_easy_shaped() -> tools.TrainTool:
    """Train with GRPO loss on basic easy shaped rewards task.

    This provides easier training with reward shaping and converters enabled,
    using the critic-free GRPO algorithm.
    """

    # Get the base shaped training tool
    base_tool = arena_basic_easy_shaped_train()

    # Configure GRPO loss
    grpo_config = GRPOConfig(
        clip_coef=0.2,
        ent_coef=0.01,
        gamma=0.99,
        group_size=4,
        norm_adv=True,
        target_kl=None,
    )

    loss_config = LossesConfig(
        losses={
            "ppo_actor": PPOActorConfig(),
            "ppo_critic": PPOCriticConfig(),
            "grpo": grpo_config,
        }
    )

    # Configure optimizer
    optimizer_config = OptimizerConfig(
        type="adamw_schedulefree",
        learning_rate=0.01,
        beta1=0.9,
        beta2=0.999,
        eps=3.186531e-07,
        weight_decay=0.01,
        warmup_steps=2000,
    )

    trainer_config = TrainerConfig(
        losses=loss_config,
        total_timesteps=50_000_000_000,
    )

    tt = tools.TrainTool(
        training_env=base_tool.training_env,
        trainer=trainer_config,
        evaluator=base_tool.evaluator,
        policy_assets={"learner0": PolicyAssetConfig(architecture=ViTGRPOConfig())},
    )
    tt.policy_assets["learner0"].optimizer = optimizer_config
    return tt
