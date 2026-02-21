from typing import TYPE_CHECKING, Any, Optional

import torch
from pydantic import Field
from tensordict import TensorDict
from torch import Tensor
from torchrl.data import Composite, UnboundedContinuous, UnboundedDiscrete

from metta.rl.loss.loss import Loss, LossConfig
from metta.rl.loss.teacher_action_utils import safe_teacher_action_indices
from metta.rl.training import ComponentContext

# Keep: heavy module + manages circular dependency (loss <-> trainer)
if TYPE_CHECKING:
    from metta.rl.trainer_config import TrainerConfig


class ActionSupervisedConfig(LossConfig):
    action_loss_coef: float = Field(default=1, ge=0)
    teacher_led_proportion: float = Field(default=0.0, ge=0, le=1.0)  # at 0.0, it's purely student-led

    def create(
        self,
        policy_assets: Any,
        trainer_cfg: "TrainerConfig",
        vec_env: Any,
        device: torch.device,
        instance_name: str,
    ) -> "ActionSupervised":
        """Create ActionSupervised loss instance."""
        return ActionSupervised(policy_assets, trainer_cfg, vec_env, device, instance_name, self)


class ActionSupervised(Loss):
    cfg: "ActionSupervisedConfig"

    __slots__ = ("rollout_batch_size", "teacher_mask")

    def __init__(
        self,
        policy_assets: Any,
        trainer_cfg: "TrainerConfig",
        vec_env: Any,
        device: torch.device,
        instance_name: str,
        cfg: "ActionSupervisedConfig",
    ):
        super().__init__(policy_assets, trainer_cfg, vec_env, device, instance_name, cfg)

    def policy_output_keys(self, policy_td: Optional[TensorDict] = None) -> set[str]:
        return {"full_log_probs"}

    def get_experience_spec(self) -> Composite:
        scalar_f32 = UnboundedContinuous(shape=torch.Size([]), dtype=torch.float32)
        action_spec = UnboundedDiscrete(shape=torch.Size([]), dtype=torch.int32)
        boolean = UnboundedDiscrete(shape=torch.Size([]), dtype=torch.bool)

        return Composite(
            actions=action_spec,
            teacher_actions=UnboundedDiscrete(shape=torch.Size([]), dtype=torch.long),
            teacher_mask=boolean,
            rewards=scalar_f32,
            dones=scalar_f32,
            truncateds=scalar_f32,
            act_log_prob=scalar_f32,
        )

    def run_rollout_preprocess(self, td: TensorDict, context: ComponentContext) -> None:
        if not hasattr(self, "rollout_batch_size") or self.rollout_batch_size != td.batch_size.numel():
            self._create_teacher_mask(td.batch_size.numel())

    def run_rollout_postprocess(self, td: TensorDict, context: ComponentContext) -> None:
        primary_policy_name = context.current_slice_cfg.primary_policy
        student_td = td.get(primary_policy_name, None)
        num_actions = int(student_td["full_log_probs"].shape[-1])
        teacher_actions_long, valid_teacher_actions, _ = safe_teacher_action_indices(
            student_td["teacher_actions"],
            num_actions,
        )
        teacher_mask = self.teacher_mask.to(device=student_td.device) & valid_teacher_actions
        student_td["teacher_mask"] = teacher_mask
        teacher_actions = teacher_actions_long.to(dtype=student_td["actions"].dtype)
        student_td["teacher_actions"] = teacher_actions
        if bool(teacher_mask.any()):
            student_td["actions"][teacher_mask] = teacher_actions[teacher_mask]
            if "act_log_prob" in student_td.keys():
                student_td["act_log_prob"][teacher_mask] = 0.0

    def run_train(
        self,
        shared_loss_data: TensorDict,
        context: ComponentContext,
        mb_idx: int,
    ) -> tuple[Tensor, TensorDict, bool]:
        minibatch: TensorDict = shared_loss_data["sampled_mb"]
        policy_td: TensorDict = shared_loss_data["policy_td"]

        policy_full_log_probs: Tensor = policy_td["full_log_probs"]
        policy_full_log_probs = policy_full_log_probs.reshape(minibatch.shape[0], minibatch.shape[1], -1)
        num_primary_actions = int(policy_full_log_probs.shape[-1])
        teacher_actions_raw: Tensor = minibatch["teacher_actions"].to(dtype=torch.long)
        _, valid_teacher_actions, safe_teacher_actions = safe_teacher_action_indices(
            minibatch["teacher_actions"],
            num_primary_actions,
        )
        # get the student's logprob for the action that the teacher chose
        student_log_probs = policy_full_log_probs.gather(dim=-1, index=safe_teacher_actions.unsqueeze(-1))
        student_log_probs = student_log_probs.reshape(minibatch.shape[0], minibatch.shape[1])

        primary_loss: Tensor
        primary_nll_sum = self._zero()
        if bool(valid_teacher_actions.any()):
            primary_nll = -student_log_probs[valid_teacher_actions]
            primary_nll_sum = primary_nll.sum()
            primary_loss = primary_nll.mean() * self.cfg.action_loss_coef
        else:
            primary_loss = self._zero()

        if bool(valid_teacher_actions.any()):
            teacher_actions_long = teacher_actions_raw
            teacher_actions_valid = teacher_actions_long[valid_teacher_actions]
            counts = torch.bincount(teacher_actions_valid, minlength=num_primary_actions).to(dtype=torch.float32)
            total_valid = counts.sum()
            if bool(total_valid > 0):
                probs = counts / total_valid
                nonzero = probs > 0
                primary_entropy = -(probs[nonzero] * probs[nonzero].log()).sum()
            else:
                primary_entropy = self._zero()

            primary_pred_actions = policy_full_log_probs.argmax(dim=-1)
            primary_top1_acc = (primary_pred_actions == teacher_actions_long)[valid_teacher_actions].float().mean()
        else:
            primary_entropy = self._zero()
            primary_top1_acc = self._zero()

        vibe_loss = self._zero()
        vibe_nll_sum = self._zero()
        valid_vibe_actions = torch.zeros_like(valid_teacher_actions)
        if "vibe_full_log_probs" in policy_td.keys():
            vibe_full_log_probs: Tensor = policy_td["vibe_full_log_probs"]
            vibe_full_log_probs = vibe_full_log_probs.reshape(minibatch.shape[0], minibatch.shape[1], -1)
            num_vibe_actions = int(vibe_full_log_probs.shape[-1])
            if num_vibe_actions > 0:
                teacher_vibe_actions = teacher_actions_raw - num_primary_actions
                valid_vibe_actions = (teacher_vibe_actions >= 0) & (teacher_vibe_actions < num_vibe_actions)
                safe_teacher_vibe_actions = teacher_vibe_actions.clamp(min=0, max=num_vibe_actions - 1)
                student_vibe_log_probs = vibe_full_log_probs.gather(
                    dim=-1,
                    index=safe_teacher_vibe_actions.unsqueeze(-1),
                ).reshape(minibatch.shape[0], minibatch.shape[1])
                if bool(valid_vibe_actions.any()):
                    vibe_nll = -student_vibe_log_probs[valid_vibe_actions]
                    vibe_nll_sum = vibe_nll.sum()
                    vibe_loss = vibe_nll.mean() * self.cfg.action_loss_coef

        total_valid_count = valid_teacher_actions.sum() + valid_vibe_actions.sum()
        if bool(total_valid_count > 0):
            total_nll_sum = primary_nll_sum + vibe_nll_sum
            loss = total_nll_sum / total_valid_count.to(dtype=torch.float32) * self.cfg.action_loss_coef
        else:
            loss = self._zero()

        assert self.loss_tracker is not None
        self.loss_tracker["supervised_action_loss"].append(float(loss.item()))
        total_positions = valid_teacher_actions.numel()
        self.loss_tracker["supervised_action_label_valid_frac"].append(
            float(total_valid_count.to(dtype=torch.float32).div(total_positions).item())
        )
        if "vibe_full_log_probs" in policy_td.keys():
            self.loss_tracker["supervised_primary_action_loss"].append(float(primary_loss.item()))
            self.loss_tracker["supervised_vibe_action_loss"].append(float(vibe_loss.item()))
            self.loss_tracker["supervised_primary_action_label_valid_frac"].append(
                float(valid_teacher_actions.float().mean().item())
            )
            self.loss_tracker["supervised_vibe_action_label_valid_frac"].append(
                float(valid_vibe_actions.float().mean().item())
            )

        self.loss_tracker["supervised_primary_action_top1_acc"].append(float(primary_top1_acc.item()))
        self.loss_tracker["supervised_primary_action_entropy"].append(float(primary_entropy.item()))

        return loss, shared_loss_data, False

    def on_train_phase_end(self, context: ComponentContext | None = None) -> None:
        if hasattr(self, "rollout_batch_size"):
            self._create_teacher_mask(self.rollout_batch_size)
        super().on_train_phase_end(context)

    def _create_teacher_mask(self, batch_size: int) -> None:
        self.rollout_batch_size = int(batch_size)
        rand = torch.rand(self.rollout_batch_size, device=self.device)
        self.teacher_mask = rand < float(self.cfg.teacher_led_proportion)
