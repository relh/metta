from __future__ import annotations

from typing import Any, Optional

import numpy as np
import torch
from cortex.rl.diff_horde import (
    diff_horde_delta_lambda,
    diff_horde_update_phi_bar_agents_,
    gather_action_values,
)
from pydantic import Field
from tensordict import TensorDict
from torch import Tensor
from torchrl.data import Composite, UnboundedContinuous, UnboundedDiscrete
from typing_extensions import Literal

from metta.rl.diff_horde.cumulants import DiffHordeCumulantExtractor, DiffHordeCumulantsConfig
from metta.rl.loss.loss import Loss, LossConfig
from metta.rl.policy_assets import PolicyAssetRegistry
from metta.rl.training import ComponentContext, TrainingEnvironment


class DiffHordeLossConfig(LossConfig):
    cumulants: DiffHordeCumulantsConfig

    vf_coef: float = Field(default=1.0, ge=0)
    aux_coef: float = Field(default=1.0, ge=0)
    eta: float = Field(default=1e-3, gt=0, le=1.0)
    beta: float = Field(default=1.0, ge=0)
    rho_clip: float = Field(default=1.0, gt=0)
    gamma: float | list[float] = 1.0
    lambda_: float | list[float] = 0.95
    reduce_cumulants: Literal["mean", "sum"] = "mean"
    normalize_cumulants: bool = True
    cumulant_centering: Literal["none", "ema"] = "none"
    cumulant_center_alpha: float = Field(default=1e-3, gt=0, le=1.0)
    cumulant_rms_alpha: float = Field(default=1e-3, gt=0, le=1.0)
    cumulant_rms_epsilon: float = Field(default=1e-6, gt=0)
    cumulant_rms_min_scale: float = Field(default=1e-3, gt=0)
    cumulant_rms_clip: float | None = Field(default=5.0, gt=0)
    aux_module_name: str = "gtd_aux"

    actions_key: str = "actions"
    dones_key: str = "dones"
    truncateds_key: str = "truncateds"

    psi_key: str = "horde_psi"
    h_key: str = "horde_h"
    psi_all_actions_key: str | None = "horde_psi_all_actions"
    h_all_actions_key: str | None = "horde_h_all_actions"

    cumulants_key: Literal["cumulants"] = "cumulants"
    cumulants_phi_bar_key: Literal["cumulants_phi_bar"] = "cumulants_phi_bar"
    behavior_log_prob_key: Literal["act_log_prob"] = "act_log_prob"
    target_log_prob_key: Literal["act_log_prob"] = "act_log_prob"
    missing_info_scalar_default: float | None = 0.0

    def create(
        self,
        policy_assets: PolicyAssetRegistry,
        trainer_cfg: Any,
        env: TrainingEnvironment,
        device: torch.device,
        instance_name: str,
    ) -> "DiffHordeLoss":
        return DiffHordeLoss(policy_assets, trainer_cfg, env, device, instance_name, self)


class DiffHordeLoss(Loss):
    cfg: "DiffHordeLossConfig"

    __slots__ = (
        "phi_bar_agentF",
        "cumulant_extractor",
        "_aux_module_params",
        "_gamma_vector_cache",
        "_lambda_vector_cache",
        "cumulant_mean_F",
        "cumulant_rms_sq_F",
        "cumulant_rms_updates",
    )

    def __init__(
        self,
        policy_assets: PolicyAssetRegistry,
        trainer_cfg: Any,
        env: TrainingEnvironment,
        device: torch.device,
        instance_name: str,
        cfg: "DiffHordeLossConfig",
    ) -> None:
        super().__init__(policy_assets, trainer_cfg, env, device, instance_name, cfg)
        policy_env_info = getattr(env, "policy_env_info", None)
        self.cumulant_extractor = DiffHordeCumulantExtractor(cfg.cumulants, policy_env_info)
        self.phi_bar_agentF = torch.empty((0, self._num_cumulants), dtype=torch.float32, device=self.device)
        self.cumulant_mean_F = torch.zeros((self._num_cumulants,), dtype=torch.float32, device=self.device)
        self.cumulant_rms_sq_F = torch.ones((self._num_cumulants,), dtype=torch.float32, device=self.device)
        self.cumulant_rms_updates = torch.zeros((), dtype=torch.int64, device=self.device)
        self._aux_module_params: tuple[Tensor, ...] | None = None
        self._gamma_vector_cache: dict[tuple[torch.device, torch.dtype], Tensor] = {}
        self._lambda_vector_cache: dict[tuple[torch.device, torch.dtype], Tensor] = {}
        self.register_state_attr("phi_bar_agentF")
        self.register_state_attr("cumulant_mean_F", "cumulant_rms_sq_F", "cumulant_rms_updates")

    @property
    def _num_cumulants(self) -> int:
        return self.cfg.cumulants.num_cumulants

    def required_env_info_keys(self) -> set[str]:
        return self.cfg.cumulants.required_info_keys()

    def env_info_missing_scalar_default(self) -> float | None:
        return self.cfg.missing_info_scalar_default

    def get_experience_spec(self) -> Composite:
        act_space = self.env.single_action_space
        act_dtype = torch.int32 if np.issubdtype(act_space.dtype, np.integer) else torch.float32
        scalar_f32 = UnboundedContinuous(shape=torch.Size([]), dtype=torch.float32)

        return Composite(
            actions=UnboundedDiscrete(shape=torch.Size([]), dtype=act_dtype),
            dones=scalar_f32,
            truncateds=scalar_f32,
            act_log_prob=scalar_f32,
            cumulants=UnboundedContinuous(shape=torch.Size([self._num_cumulants]), dtype=torch.float32),
            cumulants_phi_bar=UnboundedContinuous(shape=torch.Size([self._num_cumulants]), dtype=torch.float32),
        )

    def policy_output_keys(self, policy_td: Optional[TensorDict] = None) -> set[str]:
        keys = {self.cfg.psi_key, self.cfg.h_key, self.cfg.target_log_prob_key}
        if self.cfg.psi_all_actions_key:
            keys.add(self.cfg.psi_all_actions_key)
        if self.cfg.h_all_actions_key:
            keys.add(self.cfg.h_all_actions_key)
        return keys

    def on_rollout_start(self, context: ComponentContext | None = None) -> None:
        ctx = self._ensure_context(context)
        self._ensure_phi_bar_agentF(total_agents=int(ctx.experience.total_agents), device=self.device)

    def run_rollout_postprocess(self, td: TensorDict, context: ComponentContext) -> None:
        student_td = td.get(self._primary_policy_name(), None)
        if student_td is None:
            return

        phi_bF = self.cumulant_extractor(student_td)
        if self.cfg.normalize_cumulants:
            phi_bF = self._update_and_normalize_cumulants(phi_bF)

        self._ensure_phi_bar_agentF(total_agents=int(context.experience.total_agents), device=phi_bF.device)

        agent_ids = student_td["agent_slot_ids"].squeeze(-1).to(device=phi_bF.device, dtype=torch.long)
        baseline_bF = self.phi_bar_agentF[agent_ids]
        uninitialized = torch.isnan(baseline_bF).any(dim=-1, keepdim=True)
        if bool(uninitialized.any()):
            # Initialize each agent baseline from the first observed cumulant vector.
            baseline_bF = torch.where(uninitialized, phi_bF, baseline_bF)

        student_td[self.cfg.cumulants_key] = phi_bF.detach()
        student_td[self.cfg.cumulants_phi_bar_key] = baseline_bF.detach()

        with torch.no_grad():
            if bool(uninitialized.any()):
                self.phi_bar_agentF[agent_ids] = baseline_bF
            diff_horde_update_phi_bar_agents_(
                phi_bar_agentF=self.phi_bar_agentF,
                agent_ids_b=agent_ids,
                phi_bF=phi_bF,
                eta=float(self.cfg.eta),
            )

    def _update_and_normalize_cumulants(self, phi_bF: Tensor) -> Tensor:
        phi_f32 = phi_bF.to(device=self.device, dtype=torch.float32)
        with torch.no_grad():
            centered_phi_bF = phi_f32
            if self.cfg.cumulant_centering == "ema":
                batch_mean_F = phi_f32.mean(dim=0)
                if int(self.cumulant_rms_updates.item()) == 0:
                    self.cumulant_mean_F.copy_(batch_mean_F)
                else:
                    self.cumulant_mean_F.lerp_(batch_mean_F, float(self.cfg.cumulant_center_alpha))
                centered_phi_bF = phi_f32 - self.cumulant_mean_F.unsqueeze(0)

            # Keep RMS stats rank-local: rollout postprocess runs per trajectory slice and
            # slices can be empty on some ranks, so cross-rank collectives can deadlock.
            batch_sq_mean_F = centered_phi_bF.pow(2).mean(dim=0)
            if int(self.cumulant_rms_updates.item()) == 0:
                self.cumulant_rms_sq_F.copy_(batch_sq_mean_F)
            else:
                self.cumulant_rms_sq_F.lerp_(batch_sq_mean_F, float(self.cfg.cumulant_rms_alpha))
            self.cumulant_rms_updates.add_(1)

            scale_F = torch.sqrt(self.cumulant_rms_sq_F + float(self.cfg.cumulant_rms_epsilon)).clamp_min(
                float(self.cfg.cumulant_rms_min_scale)
            )

        normalized = centered_phi_bF / scale_F.unsqueeze(0)
        if self.cfg.cumulant_rms_clip is not None:
            clip = float(self.cfg.cumulant_rms_clip)
            normalized = normalized.clamp(min=-clip, max=clip)
        return normalized

    def run_train(
        self,
        shared_loss_data: TensorDict,
        context: ComponentContext,
        mb_idx: int,
    ) -> tuple[Tensor, TensorDict, bool]:
        _ = mb_idx
        minibatch: TensorDict = shared_loss_data["sampled_mb"]
        if minibatch.batch_size.numel() == 0:
            return self._zero(), shared_loss_data, False

        policy_td: TensorDict = shared_loss_data["policy_td"]
        b, t = minibatch.batch_size
        psi_btF = self._extract_train_head(
            policy_td=policy_td,
            minibatch=minibatch,
            direct_key=self.cfg.psi_key,
            all_actions_key=self.cfg.psi_all_actions_key,
            b=b,
            t=t,
        )
        h_btF = self._extract_train_head(
            policy_td=policy_td,
            minibatch=minibatch,
            direct_key=self.cfg.h_key,
            all_actions_key=self.cfg.h_all_actions_key,
            b=b,
            t=t,
        )
        phi_btF = self._as_btF(
            tensor=minibatch[self.cfg.cumulants_key],
            b=b,
            t=t,
            f=self._num_cumulants,
            key=self.cfg.cumulants_key,
        )
        phi_bar_btF = self._as_btF(
            tensor=minibatch[self.cfg.cumulants_phi_bar_key],
            b=b,
            t=t,
            f=self._num_cumulants,
            key=self.cfg.cumulants_phi_bar_key,
        )

        dones = minibatch[self.cfg.dones_key].to(device=psi_btF.device, dtype=psi_btF.dtype)
        truncateds = minibatch[self.cfg.truncateds_key].to(device=psi_btF.device, dtype=psi_btF.dtype)
        resets_bt = torch.logical_or(dones > 0.5, truncateds > 0.5).to(dtype=psi_btF.dtype)
        rho_bt = self._resolve_offpolicy_rho(minibatch=minibatch, policy_td=policy_td, device=psi_btF.device)

        gamma = self._parameter_to_vector_cached(
            self.cfg.gamma,
            size=self._num_cumulants,
            device=psi_btF.device,
            dtype=psi_btF.dtype,
            cache=self._gamma_vector_cache,
        )
        lambda_ = self._parameter_to_vector_cached(
            self.cfg.lambda_,
            size=self._num_cumulants,
            device=psi_btF.device,
            dtype=psi_btF.dtype,
            cache=self._lambda_vector_cache,
        )

        delta_lambda_bt1F, residual_metrics = diff_horde_delta_lambda(
            psi_btF=psi_btF,
            phi_btF=phi_btF,
            phi_bar_btF=phi_bar_btF,
            resets_bt=resets_bt,
            gamma=gamma,
            lambda_=lambda_,
            rho_bt=rho_bt,
            rho_clip=float(self.cfg.rho_clip),
        )

        psi_t = psi_btF[:, :-1, :]
        h_t = h_btF[:, :-1, :]

        def reduce_fn(x: Tensor) -> Tensor:
            reduced = x.sum(dim=-1) if self.cfg.reduce_cumulants == "sum" else x.mean(dim=-1)
            return reduced.mean()

        critic_loss = reduce_fn(h_t.detach() * delta_lambda_bt1F) - reduce_fn(
            (delta_lambda_bt1F.detach() - h_t.detach()) * psi_t
        )
        h_mse = (delta_lambda_bt1F.detach() - h_t).pow(2)
        aux_loss = 0.5 * reduce_fn(h_mse)

        l2_sum = psi_btF.new_zeros(())
        l2_count = 0
        if self.cfg.beta > 0:
            for param in self._get_aux_module_parameters():
                l2_sum = l2_sum + (param * param).sum()
                l2_count += int(param.numel())
        l2 = l2_sum / max(l2_count, 1)
        aux_total = aux_loss + 0.5 * float(self.cfg.beta) * l2
        total = float(self.cfg.vf_coef) * critic_loss + float(self.cfg.aux_coef) * aux_total

        self.loss_tracker["value_loss"].append(float(total.item()))
        self.loss_tracker["diff_horde_critic_loss"].append(float(critic_loss.item()))
        self.loss_tracker["diff_horde_aux_loss"].append(float(aux_total.item()))
        self.loss_tracker["diff_horde_h_mse"].append(float(h_mse.mean().item()))
        self.loss_tracker["diff_horde_delta_lambda_abs"].append(float(delta_lambda_bt1F.abs().mean().item()))
        if "rho_clipfrac" in residual_metrics:
            self.loss_tracker["diff_horde_rho_clipfrac"].append(float(residual_metrics["rho_clipfrac"].item()))
        return total, shared_loss_data, False

    def _ensure_phi_bar_agentF(self, *, total_agents: int, device: torch.device) -> None:
        expected_shape = (total_agents, self._num_cumulants)
        if self.phi_bar_agentF.shape == expected_shape and self.phi_bar_agentF.device == device:
            return
        if self.phi_bar_agentF.numel() == 0:
            self.phi_bar_agentF = torch.full(expected_shape, torch.nan, dtype=torch.float32, device=device)
            return
        if self.phi_bar_agentF.shape != expected_shape:
            raise RuntimeError(
                f"DiffHordeLoss state shape mismatch: expected {expected_shape}, got {tuple(self.phi_bar_agentF.shape)}"
            )
        self.phi_bar_agentF = self.phi_bar_agentF.to(device=device, dtype=torch.float32)

    def _extract_train_head(
        self,
        *,
        policy_td: TensorDict,
        minibatch: TensorDict,
        direct_key: str,
        all_actions_key: str | None,
        b: int,
        t: int,
    ) -> Tensor:
        if all_actions_key and all_actions_key in policy_td:
            values = self._gather_action_conditional(
                values=policy_td[all_actions_key],
                actions=minibatch[self.cfg.actions_key],
            )
            return self._as_btF(tensor=values, b=b, t=t, f=self._num_cumulants, key=all_actions_key)
        if direct_key in policy_td:
            return self._as_btF(tensor=policy_td[direct_key], b=b, t=t, f=self._num_cumulants, key=direct_key)
        raise RuntimeError(f"DiffHordeLoss missing policy output key '{direct_key}'")

    def _resolve_offpolicy_rho(
        self,
        *,
        minibatch: TensorDict,
        policy_td: TensorDict,
        device: torch.device,
    ) -> Tensor:
        if self.cfg.target_log_prob_key not in policy_td:
            raise RuntimeError("DiffHordeLoss off-policy correction requires policy_td['act_log_prob']")
        if self.cfg.behavior_log_prob_key not in minibatch:
            raise RuntimeError("DiffHordeLoss off-policy correction requires minibatch['act_log_prob']")

        actions_shape = minibatch[self.cfg.actions_key].shape
        target_log_prob = (
            policy_td[self.cfg.target_log_prob_key]
            .reshape(actions_shape)
            .to(
                device=device,
                dtype=torch.float32,
            )
        )
        behavior_log_prob = (
            minibatch[self.cfg.behavior_log_prob_key]
            .reshape(actions_shape)
            .to(
                device=device,
                dtype=torch.float32,
            )
        )
        logratio = torch.clamp(target_log_prob - behavior_log_prob, -10, 10)
        return logratio.exp().detach()

    @staticmethod
    def _parameter_to_vector_cached(
        value: float | list[float],
        *,
        size: int,
        device: torch.device,
        dtype: torch.dtype,
        cache: dict[tuple[torch.device, torch.dtype], Tensor],
    ) -> float | Tensor:
        if isinstance(value, list):
            if len(value) != size:
                raise ValueError(f"Expected parameter list of length {size}, got {len(value)}")
            cache_key = (device, dtype)
            cached = cache.get(cache_key)
            if cached is None:
                cached = torch.tensor(value, device=device, dtype=dtype)
                cache[cache_key] = cached
            return cached
        return float(value)

    def _get_aux_module_parameters(self) -> tuple[Tensor, ...]:
        if self._aux_module_params is not None:
            return self._aux_module_params

        aux_module = getattr(self.policy, self.cfg.aux_module_name, None)
        components = getattr(self.policy, "components", None)
        if aux_module is None and components is not None:
            aux_module = components.get(self.cfg.aux_module_name, None)

        if aux_module is None:
            self._aux_module_params = ()
        else:
            self._aux_module_params = tuple(aux_module.parameters())
        return self._aux_module_params

    @staticmethod
    def _as_btF(*, tensor: Tensor, b: int, t: int, f: int, key: str) -> Tensor:
        if tensor.dim() == 2:
            tensor = tensor.unsqueeze(-1)
        if tensor.dim() != 3:
            raise RuntimeError(f"Expected '{key}' as [B,T,F], got shape {tuple(tensor.shape)}")
        if tensor.shape[0] != b or tensor.shape[1] != t or tensor.shape[2] != f:
            raise RuntimeError(f"Expected '{key}' with shape [{b},{t},{f}], got shape {tuple(tensor.shape)}")
        return tensor.to(dtype=torch.float32)

    @staticmethod
    def _gather_action_conditional(*, values: Tensor, actions: Tensor) -> Tensor:
        if values.dim() == 4:
            return gather_action_values(values, actions)
        if values.dim() != 3:
            raise RuntimeError(f"Expected action-conditional values as [B,A,F] or [B,T,A,F], got {tuple(values.shape)}")
        if actions.dim() != 1:
            raise RuntimeError(f"Expected rollout actions with shape [B], got {tuple(actions.shape)}")
        actions_long = actions.to(dtype=torch.int64)
        index = actions_long.unsqueeze(-1).unsqueeze(-1).expand(values.shape[0], 1, values.shape[-1])
        return values.gather(dim=1, index=index).squeeze(1)
