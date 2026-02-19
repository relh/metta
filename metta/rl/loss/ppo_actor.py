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
    # Relative weight for the vibe branch policy loss
    vibe_loss_coef: float = Field(default=1.0, ge=0)
    # Entropy coefficient for vibe branch
    vibe_ent_coef: float = Field(default=0.01, ge=0)

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
        spec = Composite(act_log_prob=UnboundedContinuous(shape=torch.Size([]), dtype=torch.float32))
        if self.env.policy_env_info.vibe_action_names:
            spec.update(
                Composite(
                    vibe_actions=UnboundedDiscrete(shape=torch.Size([]), dtype=torch.int32),
                    vibe_act_log_prob=UnboundedContinuous(shape=torch.Size([]), dtype=torch.float32),
                )
            )
        return spec

    def policy_output_keys(self, policy_td: Optional[TensorDict] = None) -> set[str]:
        keys = {"act_log_prob", "entropy"}
        if self.env.policy_env_info.vibe_action_names:
            keys.update({"vibe_act_log_prob", "vibe_entropy"})
        if policy_td is not None and "vibe_act_log_prob" not in policy_td.keys():
            keys.discard("vibe_act_log_prob")
            keys.discard("vibe_entropy")
        return keys

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
        old_logprob: Tensor = minibatch["act_log_prob"]
        new_logprob: Tensor = policy_td["act_log_prob"]
        new_logprob = new_logprob.reshape(old_logprob.shape)
        entropy: Tensor = policy_td["entropy"]

        importance_sampling_ratio = shared_loss_data.get("importance_sampling_ratio", None)

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

        loss = pg_loss - cfg.ent_coef * entropy_loss

        update_td = TensorDict({"ratio": importance_sampling_ratio.detach()}, batch_size=minibatch.batch_size)

        if "vibe_act_log_prob" in minibatch.keys():
            if "vibe_act_log_prob" not in policy_td.keys():
                raise RuntimeError("PPOActor expected policy_td['vibe_act_log_prob'] when minibatch has vibe labels")
            if "vibe_entropy" not in policy_td.keys():
                raise RuntimeError("PPOActor expected policy_td['vibe_entropy'] when minibatch has vibe labels")

            old_vibe_logprob: Tensor = minibatch["vibe_act_log_prob"]
            new_vibe_logprob: Tensor = policy_td["vibe_act_log_prob"].reshape(old_vibe_logprob.shape)
            vibe_pg_loss, vibe_ratio, vibe_approx_kl, vibe_clipfrac = self._ppo_policy_loss(
                advantages=adv,
                old_logprob=old_vibe_logprob,
                new_logprob=new_vibe_logprob,
            )
            vibe_entropy = policy_td["vibe_entropy"].mean()
            loss = loss + cfg.vibe_loss_coef * vibe_pg_loss - cfg.vibe_ent_coef * vibe_entropy
            update_td["vibe_ratio"] = vibe_ratio.detach()
            self.loss_tracker["vibe_policy_loss"].append(float(vibe_pg_loss.item()))
            self.loss_tracker["vibe_entropy"].append(float(vibe_entropy.item()))
            self.loss_tracker["vibe_approx_kl"].append(float(vibe_approx_kl.item()))
            self.loss_tracker["vibe_clipfrac"].append(float(vibe_clipfrac.item()))
            self.loss_tracker["vibe_importance"].append(float(vibe_ratio.mean().item()))
            self.loss_tracker["vibe_current_logprobs"].append(float(new_vibe_logprob.mean().item()))

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
