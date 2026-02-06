from __future__ import annotations

from typing import Any, Optional

import torch
from pydantic import Field
from tensordict import TensorDict
from torch import Tensor
from torchrl.data import Composite, UnboundedContinuous, UnboundedDiscrete

from metta.agent.policy import Policy
from metta.rl.loss.loss import Loss, LossConfig
from metta.rl.training import ComponentContext, TrainingEnvironment


class FutureAttributePredictionLossConfig(LossConfig):
    """Predict a specific observation attribute value n steps in the future."""

    attribute_id: int = Field(ge=0, le=255, description="Observation attribute ID to predict.")
    prediction_horizon: int = Field(default=1, ge=1, description="Number of steps in the future to predict.")
    loss_coef: float = Field(default=1.0, ge=0.0, description="Multiplier applied to the loss value.")
    hide_target_tokens_from_policy: bool = Field(
        default=False,
        description=(
            "If True, removes target-attribute tokens from env_obs during rollout and stores rollout-time "
            "targets in replay so policies cannot observe the supervised signal."
        ),
    )

    def create(
        self,
        policy: Policy,
        trainer_cfg: Any,
        env: TrainingEnvironment,
        device: torch.device,
        instance_name: str,
    ) -> "FutureAttributePredictionLoss":
        return FutureAttributePredictionLoss(policy, trainer_cfg, env, device, instance_name, self)


class FutureAttributePredictionLoss(Loss):
    """Aux loss predicting a specific attribute value n steps in the future."""

    cfg: FutureAttributePredictionLossConfig

    _TARGET_VALUE_KEY = "future_attr_pred_target_value"
    _TARGET_VALID_KEY = "future_attr_pred_target_valid"

    def get_experience_spec(self) -> Composite:
        if not self.cfg.hide_target_tokens_from_policy:
            return Composite()
        return Composite(
            **{
                self._TARGET_VALUE_KEY: UnboundedContinuous(shape=torch.Size([]), dtype=torch.float32),
                self._TARGET_VALID_KEY: UnboundedDiscrete(shape=torch.Size([]), dtype=torch.bool),
            }
        )

    def policy_output_keys(self, policy_td: Optional[TensorDict] = None) -> set[str]:
        return {"future_attr_pred"}

    def run_rollout_preprocess(self, td: TensorDict, context: ComponentContext) -> None:
        if not self.cfg.hide_target_tokens_from_policy:
            return

        policy_td = td[context.current_slice_cfg.primary_policy]
        env_obs = policy_td["env_obs"]
        target_vals, valid_targets, matches = self._compute_targets_and_matches(env_obs)
        masked_env_obs = env_obs.clone()
        masked_env_obs[matches] = 255

        policy_td["env_obs"] = masked_env_obs
        policy_td[self._TARGET_VALUE_KEY] = target_vals
        policy_td[self._TARGET_VALID_KEY] = valid_targets

    def run_train(
        self,
        shared_loss_data: TensorDict,
        context: ComponentContext,
        mb_idx: int,
    ) -> tuple[Tensor, TensorDict, bool]:
        policy_td = shared_loss_data["policy_td"]
        minibatch = shared_loss_data["sampled_mb"]
        env_obs = minibatch["env_obs"]

        if "future_attr_pred" not in policy_td.keys():
            return self._zero(), shared_loss_data, False

        pred_vals_raw = policy_td["future_attr_pred"]
        pred_vals = pred_vals_raw.to(dtype=torch.float32).squeeze(-1)

        # Handle reshaping: if pred_vals is 2D (flattened) and env_obs is 3D, reshape pred_vals to 3D
        if pred_vals.dim() == 2 and env_obs.dim() >= 3:
            batch_size = minibatch.batch_size
            if len(batch_size) == 2:
                # Reshape from (batch*time,) to (batch, time)
                pred_vals = pred_vals.view(batch_size[0], batch_size[1])

        # Ensure env_obs matches pred_vals dimensions
        if env_obs.dim() == 3 and pred_vals.dim() == 3:
            env_obs = env_obs.view(pred_vals.shape[0], pred_vals.shape[1], env_obs.shape[-2], env_obs.shape[-1])

        if self.cfg.hide_target_tokens_from_policy:
            target_vals = minibatch[self._TARGET_VALUE_KEY].to(dtype=torch.float32)
            valid_targets = minibatch[self._TARGET_VALID_KEY]
        else:
            target_vals, valid_targets, _ = self._compute_targets_and_matches(env_obs)

        if valid_targets.sum() == 0:
            return self._zero(), shared_loss_data, False

        horizon = self.cfg.prediction_horizon
        if pred_vals.shape[1] <= horizon or target_vals.shape[1] <= horizon:
            return self._zero(), shared_loss_data, False

        max_len = min(pred_vals.shape[1] - horizon, target_vals.shape[1] - horizon)
        if max_len <= 0:
            return self._zero(), shared_loss_data, False

        pred = pred_vals[:, :max_len]
        target = target_vals[:, horizon : horizon + max_len]
        valid_mask = valid_targets[:, horizon : horizon + max_len]

        if valid_mask.sum() == 0:
            return self._zero(), shared_loss_data, False

        diff = pred - target
        mse = (diff**2 * valid_mask).sum() / valid_mask.sum().clamp_min(1)
        loss = mse * self.cfg.loss_coef

        mae = (diff.abs() * valid_mask).sum() / valid_mask.sum().clamp_min(1)
        valid_frac = valid_mask.float().mean()

        self.loss_tracker["future_attr_pred_mse"].append(float(mse.item()))
        self.loss_tracker["future_attr_pred_mae"].append(float(mae.item()))
        self.loss_tracker["future_attr_pred_valid_frac"].append(float(valid_frac.item()))

        return loss, shared_loss_data, False

    def _compute_targets_and_matches(self, env_obs: Tensor) -> tuple[Tensor, Tensor, Tensor]:
        attr_ids = env_obs[..., 1].long()
        attr_vals = env_obs[..., 2].to(dtype=torch.float32)
        valid_tokens = env_obs[..., 0] != 255

        matches = valid_tokens & (attr_ids == self.cfg.attribute_id)
        match_counts = matches.sum(dim=-1)
        summed_vals = (attr_vals * matches).sum(dim=-1)
        target_vals = summed_vals / match_counts.clamp_min(1)
        valid_targets = match_counts > 0
        return target_vals, valid_targets, matches
