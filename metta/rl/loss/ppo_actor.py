from typing import Any, Optional

import numpy as np
import torch
from pydantic import Field
from tensordict import TensorDict
from torch import Tensor
from torchrl.data import Composite, UnboundedContinuous, UnboundedDiscrete

from metta.rl.advantage import normalize_advantage_distributed
from metta.rl.loss.loss import Loss, LossConfig
from metta.rl.policy_assets import PolicyAssetRegistry
from metta.rl.training import ComponentContext, TrainingEnvironment


class PPOActorConfig(LossConfig):
    # Clip coefficient (0.1-0.3 typical; Schulman et al. 2017)
    clip_coef: float = Field(default=0.22017136216163635, gt=0, le=1.0)
    # Entropy term weight from sweep
    ent_coef: float = Field(default=0.01, ge=0)
    # Relative weight for this actor loss
    loss_coef: float = Field(default=1.0, ge=0)

    # Actor-head routing keys so one PPOActor implementation can serve multiple heads.
    actor_name: str = "primary"
    log_prob_key: str = "act_log_prob"
    entropy_key: str = "entropy"
    importance_sampling_ratio_key: str | None = "importance_sampling_ratio"
    replay_ratio_key: str = "ratio"
    extra_action_keys: list[str] = Field(default_factory=list)

    # Normalization and clipping
    # Advantage normalization toggle
    norm_adv: bool = True
    # Target KL for early stopping (None disables)
    target_kl: float | None = None

    def create(
        self,
        policy_assets: PolicyAssetRegistry,
        trainer_cfg: Any,
        env: TrainingEnvironment,
        device: torch.device,
        instance_name: str,
    ) -> "PPOActor":
        return PPOActor(policy_assets, trainer_cfg, env, device, instance_name, self)


class PPOActor(Loss):
    """PPO actor loss."""

    cfg: "PPOActorConfig"

    __slots__ = ()

    def __init__(
        self,
        policy_assets: PolicyAssetRegistry,
        trainer_cfg: Any,
        env: TrainingEnvironment,
        device: torch.device,
        instance_name: str,
        cfg: "PPOActorConfig",
    ):
        super().__init__(policy_assets, trainer_cfg, env, device, instance_name, cfg)

    def get_experience_spec(self) -> Composite:
        spec = Composite(
            **{
                self.cfg.log_prob_key: UnboundedContinuous(shape=torch.Size([]), dtype=torch.float32),
            }
        )
        for key in self.cfg.extra_action_keys:
            if key in spec.keys():
                continue
            spec[key] = UnboundedDiscrete(shape=torch.Size([]), dtype=torch.int32)
        return spec

    def policy_output_keys(self, policy_td: Optional[TensorDict] = None) -> set[str]:
        if policy_td is not None:
            if self.cfg.log_prob_key not in policy_td.keys() or self.cfg.entropy_key not in policy_td.keys():
                return set()
        return {self.cfg.log_prob_key, self.cfg.entropy_key}

    def _ppo_policy_loss(
        self,
        *,
        advantages: Tensor,
        old_logprob: Tensor,
        new_logprob: Tensor,
        ratio: Optional[Tensor] = None,
    ) -> tuple[Tensor, Tensor, Tensor, Tensor]:
        if ratio is None:
            logratio = torch.clamp(new_logprob - old_logprob, -10, 10)
            ratio = logratio.exp()

        pg_loss1 = -advantages * ratio
        pg_loss2 = -advantages * torch.clamp(
            ratio,
            1 - self.cfg.clip_coef,
            1 + self.cfg.clip_coef,
        )
        pg_loss = torch.max(pg_loss1, pg_loss2).mean()

        logratio_metric = new_logprob - old_logprob
        approx_kl = ((ratio - 1) - logratio_metric).mean()
        clipfrac = ((ratio - 1.0).abs() > self.cfg.clip_coef).float().mean()
        return pg_loss, ratio, approx_kl, clipfrac

    def run_train(
        self, shared_loss_data: TensorDict, context: ComponentContext, mb_idx: int
    ) -> tuple[Tensor, TensorDict, bool]:
        assert self.loss_tracker is not None
        stop_update_epoch = False
        if mb_idx > 0 and self.cfg.target_kl is not None:
            avg_kl = np.mean(self.loss_tracker["approx_kl"]) if self.loss_tracker["approx_kl"] else 0.0
            if avg_kl > self.cfg.target_kl:
                stop_update_epoch = True

        cfg = self.cfg

        minibatch: TensorDict = shared_loss_data["sampled_mb"]

        if minibatch.batch_size.numel() == 0:  # early exit if minibatch is empty
            return self._zero(), shared_loss_data, False

        policy_td: TensorDict = shared_loss_data["policy_td"]
        if self.cfg.log_prob_key not in minibatch.keys():
            raise RuntimeError(
                f"PPOActor[{self.cfg.actor_name}] expected minibatch['{self.cfg.log_prob_key}'], but it was missing."
            )
        if self.cfg.log_prob_key not in policy_td.keys():
            raise RuntimeError(
                f"PPOActor[{self.cfg.actor_name}] expected policy_td['{self.cfg.log_prob_key}'], but it was missing."
            )
        if self.cfg.entropy_key not in policy_td.keys():
            raise RuntimeError(
                f"PPOActor[{self.cfg.actor_name}] expected policy_td['{self.cfg.entropy_key}'], but it was missing."
            )

        old_logprob: Tensor = minibatch[self.cfg.log_prob_key]
        new_logprob: Tensor = policy_td[self.cfg.log_prob_key]
        new_logprob = new_logprob.reshape(old_logprob.shape)
        entropy: Tensor = policy_td[self.cfg.entropy_key]

        importance_sampling_ratio = None
        if self.cfg.importance_sampling_ratio_key is not None:
            importance_sampling_ratio = shared_loss_data.get(self.cfg.importance_sampling_ratio_key, None)

        adv = shared_loss_data.get("advantages_pg", None)
        if adv is None:
            adv = shared_loss_data.get("advantages", None)
        if adv is None:
            raise RuntimeError(
                "PPOActor expected advantages in shared_loss_data, but none were found. "
                "Ensure PPOCritic runs before PPOActor."
            )
        adv = adv.detach()

        # Normalize advantages with distributed support, then apply prioritized weights
        adv = normalize_advantage_distributed(adv, cfg.norm_adv)
        prio_weights: Tensor = shared_loss_data["prio_weights"]
        adv = prio_weights * adv

        pg_loss, importance_sampling_ratio, approx_kl, clipfrac = self._ppo_policy_loss(
            advantages=adv,
            old_logprob=old_logprob,
            new_logprob=new_logprob,
            ratio=importance_sampling_ratio,
        )

        entropy_loss = entropy.mean()

        loss = cfg.loss_coef * pg_loss - cfg.ent_coef * entropy_loss

        update_td = TensorDict(
            {self.cfg.replay_ratio_key: importance_sampling_ratio.detach()},
            batch_size=minibatch.batch_size,
        )

        indices: Tensor = shared_loss_data["indices"]
        assert self.replay is not None
        self.replay.update(indices[:, 0], update_td)

        # Update loss tracking
        self.loss_tracker["policy_loss"].append(float(pg_loss.item()))
        self.loss_tracker["entropy"].append(float(entropy_loss.item()))
        self.loss_tracker["approx_kl"].append(float(approx_kl.item()))
        self.loss_tracker["clipfrac"].append(float(clipfrac.item()))
        self.loss_tracker["importance"].append(float(importance_sampling_ratio.mean().item()))
        self.loss_tracker["current_logprobs"].append(float(new_logprob.mean().item()))

        return loss, shared_loss_data, stop_update_epoch
