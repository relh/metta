from typing import TYPE_CHECKING, Any, Optional, cast

import torch
from pydantic import Field
from tensordict import TensorDict
from torch import Tensor
from torchrl.data import Composite, UnboundedContinuous

from metta.rl.loss.loss import Loss, LossConfig
from metta.rl.policy_assets import PolicyAssetRegistry
from metta.rl.training import ComponentContext

if TYPE_CHECKING:
    from metta.rl.trainer_config import TrainerConfig


class EERKickstarterConfig(LossConfig):
    policy: str = Field(default="primary")
    teacher: str = Field(default="teacher")
    action_loss_coef: float = Field(default=0.6, ge=0, le=1.0)
    value_loss_coef: float = Field(default=1.0, ge=0, le=1.0)
    r_lambda: float = Field(default=0.01, ge=0)  # scale the teacher log likelihoods that are added to rewards

    def create(
        self,
        policy_assets: Any,
        trainer_cfg: "TrainerConfig",
        vec_env: Any,
        device: torch.device,
        instance_name: str,
    ) -> "EERKickstarter":
        """Create EERKickstarter loss instance."""
        return EERKickstarter(
            policy_assets,
            trainer_cfg,
            vec_env,
            device,
            instance_name,
            self,
        )


class EERKickstarter(Loss):
    """Expected Entropy Regularization Kickstarter. See "Distilling Policy Distillation."

    Implements:
    1. Reward shaping: r' = r + lambda * log(pi_teacher(a|s))
       This corresponds to minimizing Expected Entropy Regularized objective.
    2. Auxiliary Distillation Loss: KL(pi_student || pi_teacher) minimization term.
    """

    cfg: EERKickstarterConfig

    __slots__ = ("last_teacher_log_probs", "has_last_probs")

    def __init__(
        self,
        policy_assets: PolicyAssetRegistry,
        trainer_cfg: "TrainerConfig",
        vec_env: Any,
        device: torch.device,
        instance_name: str,
        cfg: "EERKickstarterConfig",
    ):
        super().__init__(policy_assets, trainer_cfg, vec_env, device, instance_name, cfg)

        # Cache for teacher log probs from previous step, needed for reward shaping R_{t-1} + log(pi(A_{t-1}))
        # We need this because run_rollout receives R_t (reward for action at t-1), but computes pi(S_t).
        # So we must use the cached pi(S_{t-1}) to shape R_t.
        num_agents = self.env.total_parallel_agents
        num_actions = self.env.single_action_space.n
        self.last_teacher_log_probs = torch.zeros((num_agents, num_actions), device=self.device)
        self.has_last_probs = torch.zeros(num_agents, dtype=torch.bool, device=self.device)

    def get_experience_spec(self) -> Composite:
        act_space = self.env.single_action_space
        num_actions = act_space.n

        scalar_f32 = UnboundedContinuous(shape=torch.Size([]), dtype=torch.float32)
        logits_f32 = UnboundedContinuous(shape=torch.Size([num_actions]), dtype=torch.float32)

        return Composite(
            teacher_full_log_probs=logits_f32,
            teacher_values=scalar_f32,
        )

    def run_rollout_postprocess(self, td: TensorDict, context: ComponentContext) -> None:
        teacher_td = td.get(self.cfg.teacher, None)
        primary_policy_name = self._primary_policy_name()
        student_td = td.get(primary_policy_name, None)

        with torch.no_grad():
            # Store teacher outputs for action and value losses
            student_td["teacher_full_log_probs"] = teacher_td["full_log_probs"]
            student_td["teacher_values"] = teacher_td["values"]

            # --- Reward Shaping ---
            # td["rewards"] contains R_{t-1}. We want to add r_lambda * log(pi_teacher(A_{t-1}|S_{t-1})).
            # We use cached teacher probs from the previous step.
            agent_ids = student_td["agent_slot_ids"].squeeze(-1).to(dtype=torch.long)
            valid_mask = self.has_last_probs[agent_ids]
            if valid_mask.any():
                last_probs = self.last_teacher_log_probs[agent_ids]

                # Get actions taken at t-1: (batch,)
                last_actions = student_td["last_actions"]
                if last_actions.dim() > 1:
                    last_actions = last_actions.squeeze(-1)
                last_actions = last_actions.long()

                # Gather log prob of taken action: (batch,)
                intrinsic_reward = last_probs.gather(1, last_actions.unsqueeze(1)).squeeze(1)

                # Add to rewards in place (modifies the buffer view)
                student_td["rewards"] += self.cfg.r_lambda * intrinsic_reward * valid_mask.float()

            # Update cache for next step
            self.last_teacher_log_probs[agent_ids] = teacher_td["full_log_probs"]
            self.has_last_probs[agent_ids] = True

    def policy_output_keys(self, policy_td: Optional[TensorDict] = None) -> set[str]:
        return {"full_log_probs", "values"}

    def run_train(
        self,
        shared_loss_data: TensorDict,
        context: ComponentContext,
        mb_idx: int,
    ) -> tuple[Tensor, TensorDict, bool]:
        minibatch = cast(TensorDict, shared_loss_data["sampled_mb"])
        student_td = cast(TensorDict, shared_loss_data["policy_td"])

        student_full_log_probs = student_td["full_log_probs"]
        teacher_full_log_probs = minibatch["teacher_full_log_probs"]
        ks_action_loss = -(student_full_log_probs.exp() * teacher_full_log_probs).sum(dim=-1).mean()

        # Value loss
        teacher_value = minibatch["teacher_values"].to(dtype=torch.float32).detach()
        student_value = student_td["values"].to(dtype=torch.float32)
        ks_value_loss_vec = (teacher_value.detach() - student_value) ** 2
        ks_value_loss = ks_value_loss_vec.mean()

        loss = ks_action_loss * self.cfg.action_loss_coef + ks_value_loss * self.cfg.value_loss_coef

        # track losses for plotting
        self.loss_tracker["ks_act_loss"].append(float(ks_action_loss.item()))
        self.loss_tracker["ks_val_loss"].append(float(ks_value_loss.item()))
        self.loss_tracker["ks_act_loss_coef"].append(float(self.cfg.action_loss_coef))
        self.loss_tracker["ks_val_loss_coef"].append(float(self.cfg.value_loss_coef))

        return loss, shared_loss_data, False
