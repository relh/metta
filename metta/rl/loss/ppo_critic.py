from typing import Any, Optional, cast

import numpy as np
import torch
from cortex.rl.diff_horde import diff_horde_delta_lambda, diff_horde_update_phi_bar_agents_
from pydantic import Field
from tensordict import TensorDict
from torch import Tensor
from torchrl.data import Composite, UnboundedContinuous, UnboundedDiscrete
from typing_extensions import Literal

from metta.rl.advantage import compute_advantage, compute_delta_lambda
from metta.rl.loss.loss import Loss, LossConfig
from metta.rl.policy_assets import PolicyAssetRegistry
from metta.rl.training import ComponentContext, TrainingEnvironment


class PPOCriticConfig(LossConfig):
    vf_clip_coef: float = Field(default=0.1, ge=0)
    vf_coef: float = Field(default=0.49657103419303894, ge=0)
    # Value loss clipping toggle
    clip_vloss: bool = True
    critic_update: Literal["mse", "gtd_lambda"] = "gtd_lambda"
    aux_coef: float = Field(default=1.0, ge=0)
    beta: float = Field(default=1.0, ge=0)
    rho_clip: float = Field(default=1.0, gt=0)

    def create(
        self,
        policy_assets: PolicyAssetRegistry,
        trainer_cfg: Any,
        env: TrainingEnvironment,
        device: torch.device,
        instance_name: str,
    ) -> "PPOCritic":
        return PPOCritic(policy_assets, trainer_cfg, env, device, instance_name, self)


class PPOCritic(Loss):
    """PPO value loss."""

    __slots__ = ("reward_phi_bar_agentF",)

    def __init__(
        self,
        policy_assets: PolicyAssetRegistry,
        trainer_cfg: Any,
        env: TrainingEnvironment,
        device: torch.device,
        instance_name: str,
        cfg: "PPOCriticConfig",
    ):
        super().__init__(policy_assets, trainer_cfg, env, device, instance_name, cfg)
        self.reward_phi_bar_agentF = torch.empty((0, 1), dtype=torch.float32, device=self.device)
        self.register_state_attr("reward_phi_bar_agentF")

    def get_experience_spec(self) -> Composite:
        act_space = self.env.single_action_space
        act_dtype = torch.int32 if np.issubdtype(act_space.dtype, np.integer) else torch.float32
        scalar_f32 = UnboundedContinuous(shape=torch.Size([]), dtype=torch.float32)

        return Composite(
            actions=UnboundedDiscrete(shape=torch.Size([]), dtype=act_dtype),
            values=scalar_f32,
            rewards=scalar_f32,
            dones=scalar_f32,
            truncateds=scalar_f32,
        )

    def policy_output_keys(self, policy_td: Optional[TensorDict] = None) -> set[str]:
        if self.cfg.critic_update == "gtd_lambda":
            return {"values", "h_values"}
        return {"values"}

    def on_rollout_start(self, context: ComponentContext | None = None) -> None:
        ctx = self._ensure_context(context)
        self._ensure_reward_phi_bar_agentF(total_agents=int(ctx.experience.total_agents), context=ctx)

    def run_rollout_postprocess(self, td: TensorDict, context: ComponentContext) -> None:
        student_td = td.get(self._primary_policy_name(), None)
        if student_td is None:
            return

        self._ensure_reward_phi_bar_agentF(total_agents=int(context.experience.total_agents), context=context)

        agent_ids = student_td["agent_slot_ids"].squeeze(-1).to(dtype=torch.long)
        rewards = student_td["rewards"].to(device=self.reward_phi_bar_agentF.device, dtype=torch.float32).reshape(-1, 1)
        avg_reward = context.state.avg_reward
        if isinstance(avg_reward, Tensor) and avg_reward.numel() == int(context.experience.total_agents):
            baseline_b1 = (
                avg_reward[agent_ids].to(device=self.reward_phi_bar_agentF.device, dtype=torch.float32).reshape(-1, 1)
            )
        else:
            baseline_b1 = self.reward_phi_bar_agentF[agent_ids]
        uninitialized = torch.isnan(baseline_b1)
        if bool(uninitialized.any()):
            # Initialize each agent baseline from the first observed reward.
            baseline_b1 = torch.where(uninitialized, rewards, baseline_b1)
        with torch.no_grad():
            self.reward_phi_bar_agentF[agent_ids] = baseline_b1
        student_td["reward_baseline"] = baseline_b1.squeeze(-1).detach()

        eta = float(context.current_slice_cfg.advantage.reward_centering.beta)
        with torch.no_grad():
            diff_horde_update_phi_bar_agents_(
                phi_bar_agentF=self.reward_phi_bar_agentF,
                agent_ids_b=agent_ids,
                phi_bF=rewards,
                eta=eta,
            )

    def _ensure_reward_phi_bar_agentF(self, *, total_agents: int, context: ComponentContext) -> None:
        expected = (total_agents, 1)
        if self.reward_phi_bar_agentF.shape == expected and self.reward_phi_bar_agentF.device == self.device:
            return
        if self.reward_phi_bar_agentF.numel() == 0:
            avg_reward = context.state.avg_reward
            if isinstance(avg_reward, Tensor) and avg_reward.numel() == total_agents:
                self.reward_phi_bar_agentF = (
                    avg_reward.to(device=self.device, dtype=torch.float32).reshape(-1, 1).clone()
                )
            else:
                self.reward_phi_bar_agentF = torch.full(expected, torch.nan, device=self.device, dtype=torch.float32)
            return
        if self.reward_phi_bar_agentF.shape != expected:
            raise RuntimeError(
                "PPOCritic reward baseline shape mismatch: "
                f"expected {expected}, got {tuple(self.reward_phi_bar_agentF.shape)}"
            )
        self.reward_phi_bar_agentF = self.reward_phi_bar_agentF.to(device=self.device, dtype=torch.float32)

    def _ensure_advantages_pg(self, shared_loss_data: TensorDict, context: ComponentContext) -> None:
        if "advantages_pg" in shared_loss_data:
            return

        minibatch = shared_loss_data["sampled_mb"]
        if context.current_slice_cfg is None:
            raise RuntimeError("PPOCritic requires a trajectory slice to select advantage config.")
        advantage_cfg = context.current_slice_cfg.advantage
        if self.cfg.critic_update == "gtd_lambda":
            if "values" not in minibatch:
                raise RuntimeError("delta_lambda advantages require minibatch['values']")

            policy_td = shared_loss_data["policy_td"]
            new_values = policy_td["values"]
            if new_values.dim() == 3 and new_values.shape[-1] == 1:
                new_values = new_values.squeeze(-1)
            new_values = new_values.reshape(minibatch["values"].shape)

            centered_rewards = minibatch["rewards"] - minibatch["reward_baseline"]
            shared_loss_data["advantages_pg"] = compute_delta_lambda(
                values=new_values,
                rewards=centered_rewards,
                dones=minibatch["dones"],
                gamma=float(advantage_cfg.gamma),
                gae_lambda=float(advantage_cfg.gae_lambda),
            )
            return

        values_for_adv = minibatch["values"] if "values" in minibatch else None
        if values_for_adv is not None:
            if values_for_adv.dim() > 2:
                values_for_adv = values_for_adv.mean(dim=-1)

            importance_sampling_ratio = shared_loss_data.get("importance_sampling_ratio", None)
            if importance_sampling_ratio is None:
                importance_sampling_ratio = torch.ones_like(values_for_adv)

            with torch.no_grad():
                centered_rewards = minibatch["rewards"] - minibatch["reward_baseline"]
                shared_loss_data["advantages_pg"] = compute_advantage(
                    values_for_adv,
                    centered_rewards,
                    minibatch["dones"],
                    importance_sampling_ratio,
                    shared_loss_data["advantages"].clone(),
                    advantage_cfg.gamma,
                    advantage_cfg.gae_lambda,
                    self.device,
                    advantage_cfg.vtrace_rho_clip,
                    advantage_cfg.vtrace_c_clip,
                )
        else:
            shared_loss_data["advantages_pg"] = shared_loss_data["advantages"]

    def run_train(
        self, shared_loss_data: TensorDict, context: ComponentContext, mb_idx: int
    ) -> tuple[Tensor, TensorDict, bool]:
        assert self.loss_tracker is not None
        assert self.replay is not None
        # Sampling happens in the core loop; use the shared minibatch and indices.
        minibatch: TensorDict = shared_loss_data["sampled_mb"]

        if minibatch.batch_size.numel() == 0:  # early exit if minibatch is empty
            return self._zero(), shared_loss_data, False

        self._ensure_advantages_pg(shared_loss_data, context)

        # Keep the full advantages around for explained variance logging and prioritized sampling.
        old_values: Tensor = minibatch["values"]
        if self.cfg.critic_update == "gtd_lambda":
            policy_td: TensorDict = shared_loss_data["policy_td"]
            if "h_values" not in policy_td:
                raise RuntimeError("Policy must output 'h_values' for critic_update='gtd_lambda'")

            new_values: Tensor = policy_td["values"]
            new_values = new_values.reshape(old_values.shape)
            h_values: Tensor = policy_td["h_values"]
            if h_values.dim() == 3 and h_values.shape[-1] == 1:
                h_values = h_values.squeeze(-1)
            h_values = h_values.reshape(old_values.shape)

            rewards_bt = minibatch["rewards"].reshape(old_values.shape)
            reward_baseline_bt = minibatch["reward_baseline"].reshape(old_values.shape)
            dones_bt = minibatch["dones"].reshape(old_values.shape)
            truncateds_bt = minibatch["truncateds"].reshape(old_values.shape)
            resets_bt = torch.logical_or(dones_bt > 0.5, truncateds_bt > 0.5).to(dtype=new_values.dtype)

            rho_bt = shared_loss_data.get("importance_sampling_ratio", None)
            if rho_bt is None:
                raise RuntimeError("TD(λ) off-policy correction requires shared_loss_data['importance_sampling_ratio']")
            rho_bt = rho_bt.reshape(old_values.shape).detach()

            rho_clip = float(self.cfg.rho_clip)
            if "teacher_mask" in minibatch:
                teacher_mask = minibatch["teacher_mask"][:, 0].to(dtype=torch.bool)
                if bool(teacher_mask.any()):
                    rho_trim = rho_bt[teacher_mask][:, :-1]
                    self.loss_tracker["teacher_td_lambda_rho_clipfrac"].append(
                        float((rho_trim > rho_clip).float().mean().item())
                    )

            advantage_cfg = context.current_slice_cfg.advantage
            delta_lambda_bt1F, _metrics = diff_horde_delta_lambda(
                psi_btF=new_values.unsqueeze(-1),
                phi_btF=rewards_bt.unsqueeze(-1),
                phi_bar_btF=reward_baseline_bt.unsqueeze(-1),
                resets_bt=resets_bt,
                gamma=float(advantage_cfg.gamma),
                lambda_=float(advantage_cfg.gae_lambda),
                rho_bt=rho_bt,
                rho_clip=rho_clip,
            )

            delta_lambda = torch.zeros_like(new_values)
            delta_lambda[:, :-1] = delta_lambda_bt1F.squeeze(-1)
            shared_loss_data["advantages_pg"] = delta_lambda

            dl = delta_lambda[:, :-1]
            v_t = new_values[:, :-1]
            h_t = h_values[:, :-1]

            critic_loss = (h_t.detach() * dl).mean() - ((dl.detach() - h_t.detach()) * v_t).mean()

            l2_sum = torch.tensor(0.0, device=critic_loss.device, dtype=critic_loss.dtype)
            l2_count = 0
            if self.cfg.beta > 0:
                aux_module = getattr(self.policy, "gtd_aux", None)
                components = getattr(self.policy, "components", None)
                if aux_module is None and components is not None:
                    aux_module = components.get("gtd_aux", None)
                if aux_module is not None:
                    for param in aux_module.parameters():
                        l2_sum = l2_sum + (param * param).sum()
                        l2_count += int(param.numel())
            l2 = l2_sum / max(l2_count, 1)
            aux_loss = 0.5 * ((dl.detach() - h_t) ** 2).mean() + 0.5 * float(self.cfg.beta) * l2

            total = float(self.cfg.vf_coef) * critic_loss + float(self.cfg.aux_coef) * aux_loss
            self.loss_tracker["value_loss"].append(float(total.item()))
            self.loss_tracker["gtd_critic_loss"].append(float(critic_loss.item()))
            self.loss_tracker["gtd_aux_loss"].append(float(aux_loss.item()))
            self.loss_tracker["gtd_h_mse"].append(float(((dl.detach() - h_t) ** 2).mean().item()))
            self.loss_tracker["gtd_delta_lambda_abs"].append(float(dl.detach().abs().mean().item()))

            # Update values in experience buffer for advantage_full recomputation + EV logging.
            mb_values: Tensor = minibatch["values"]
            update_td = TensorDict(
                {
                    "values": new_values.reshape(mb_values.shape).detach(),
                },
                batch_size=minibatch.batch_size,
            )
            indices: Tensor = shared_loss_data["indices"]
            self.replay.update(indices[:, 0], update_td)

            return total, shared_loss_data, False

        advantages_mb: Tensor = shared_loss_data["advantages"]
        mb_values2: Tensor = minibatch["values"]
        returns = advantages_mb + mb_values2
        minibatch["returns"] = returns
        # Read policy forward results from the core loop (forward_policy_for_training).
        policy_td2_raw = shared_loss_data.get("policy_td", None)
        newvalue_reshaped: Tensor | None = None
        newvalue: Tensor | None = None
        if policy_td2_raw is not None:
            policy_td2 = cast(TensorDict, policy_td2_raw)
            newvalue = cast(Tensor, policy_td2["values"])
            newvalue_reshaped = newvalue.view(returns.shape)

        if newvalue_reshaped is not None:
            if self.cfg.clip_vloss:
                v_loss_unclipped = (newvalue_reshaped - returns) ** 2
                vf_clip_coef = self.cfg.vf_clip_coef
                v_clipped = old_values + torch.clamp(
                    newvalue_reshaped - old_values,
                    -vf_clip_coef,
                    vf_clip_coef,
                )
                v_loss_clipped = (v_clipped - returns) ** 2
                v_loss_vec = 0.5 * torch.max(v_loss_unclipped, v_loss_clipped)
            else:
                v_loss_vec = 0.5 * ((newvalue_reshaped - returns) ** 2)

            v_loss = v_loss_vec.mean()

            shared_loss_data["ppo_val_loss_vec"] = v_loss_vec

            # Update values in experience buffer
            assert newvalue is not None
            mb_values3: Tensor = minibatch["values"]
            update_td = TensorDict(
                {
                    "values": newvalue.view(mb_values3.shape).detach(),
                },
                batch_size=minibatch.batch_size,
            )
            indices2: Tensor = shared_loss_data["indices"]
            self.replay.update(indices2[:, 0], update_td)
        else:
            v_loss = 0.5 * ((old_values - returns) ** 2).mean()
        # Scale value loss by coefficient
        v_loss = v_loss * self.cfg.vf_coef
        self.loss_tracker["value_loss"].append(float(v_loss.item()))

        return v_loss, shared_loss_data, False

    def on_train_phase_end(self, context: ComponentContext | None = None) -> None:
        """Compute value-function explained variance for logging, mirroring monolithic PPO."""
        assert self.replay is not None
        assert self.loss_tracker is not None
        with torch.no_grad():
            values: Tensor = self.replay.buffer["values"]
            adv_full: Tensor = self.replay.buffer["advantages_full"]
            y_pred = values.flatten()
            y_true = adv_full.flatten() + values.flatten()
            var_y = y_true.var()
            ev = (1 - (y_true - y_pred).var() / var_y).item() if var_y > 0 else 0.0
            self.loss_tracker["explained_variance"].append(float(ev))

        super().on_train_phase_end(context)
