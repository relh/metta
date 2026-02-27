from typing import TYPE_CHECKING, Any, Optional

import torch
from pydantic import Field
from tensordict import TensorDict
from torch import Tensor
from torchrl.data import Composite, UnboundedContinuous, UnboundedDiscrete

from metta.rl.loss.loss import Loss, LossConfig
from metta.rl.loss.teacher_action_utils import decode_teacher_action_labels
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

    __slots__ = (
        "rollout_batch_size",
        "teacher_mask",
        "num_primary_actions",
        "num_vibe_actions",
        "noop_action_index",
    )

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
        self.num_primary_actions = int(self.env.single_action_space.n)
        self.num_vibe_actions = len(self.env.policy_env_info.vibe_action_names)
        action_names = list(self.env.policy_env_info.action_names)
        self.noop_action_index = action_names.index("noop")
        self.rollout_batch_size = 0
        self.teacher_mask = torch.zeros((0,), dtype=torch.bool, device=self.device)

    def policy_output_keys(self, policy_td: Optional[TensorDict] = None) -> set[str]:
        keys = {"full_log_probs"}
        if self.num_vibe_actions > 0:
            keys.add("vibe_full_log_probs")
        return keys

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
        if self.rollout_batch_size != td.batch_size.numel():
            self._create_teacher_mask(td.batch_size.numel())

    def run_rollout_postprocess(self, td: TensorDict, context: ComponentContext) -> None:
        primary_policy_name = context.current_slice_cfg.primary_policy
        student_td = td[primary_policy_name]
        core_teacher_actions, valid_teacher_actions, teacher_vibe_actions, _ = self._decode_teacher_actions(
            student_td["teacher_actions"]
        )
        teacher_mask = self.teacher_mask.to(device=student_td.device) & valid_teacher_actions
        student_td["teacher_mask"] = teacher_mask
        teacher_actions = core_teacher_actions.to(dtype=student_td["actions"].dtype)
        if bool(teacher_mask.any()):
            student_td["actions"][teacher_mask] = teacher_actions[teacher_mask]
            if "act_log_prob" in student_td:
                student_td["act_log_prob"][teacher_mask] = 0.0
            if "vibe_actions" in student_td.keys():
                vibe_actions = teacher_vibe_actions.to(dtype=student_td["vibe_actions"].dtype)
                student_td["vibe_actions"][teacher_mask] = vibe_actions[teacher_mask]
                if "vibe_act_log_prob" in student_td.keys():
                    student_td["vibe_act_log_prob"][teacher_mask] = 0.0

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
        (
            teacher_actions,
            valid_teacher_actions,
            teacher_vibe_actions,
            valid_teacher_vibe_actions,
        ) = self._decode_teacher_actions(minibatch["teacher_actions"])
        # get the student's logprob for the action that the teacher chose
        student_log_probs = policy_full_log_probs.gather(dim=-1, index=teacher_actions.unsqueeze(-1))
        student_log_probs = student_log_probs.reshape(minibatch.shape[0], minibatch.shape[1])

        loss = self._zero()
        if bool(valid_teacher_actions.any()):
            loss = loss - student_log_probs[valid_teacher_actions].mean() * self.cfg.action_loss_coef

        vibe_loss = self._zero()
        effective_valid_teacher_vibe_actions = torch.zeros_like(valid_teacher_vibe_actions)
        if self.num_vibe_actions > 0 and "vibe_full_log_probs" in policy_td.keys():
            vibe_full_log_probs = policy_td["vibe_full_log_probs"].reshape(minibatch.shape[0], minibatch.shape[1], -1)
            student_vibe_log_probs = vibe_full_log_probs.gather(dim=-1, index=teacher_vibe_actions.unsqueeze(-1))
            student_vibe_log_probs = student_vibe_log_probs.reshape(minibatch.shape[0], minibatch.shape[1])
            effective_valid_teacher_vibe_actions = valid_teacher_vibe_actions
            if bool(effective_valid_teacher_vibe_actions.any()):
                vibe_loss = (
                    -student_vibe_log_probs[effective_valid_teacher_vibe_actions].mean() * self.cfg.action_loss_coef
                )
                loss = loss + vibe_loss

        assert self.loss_tracker is not None
        self.loss_tracker["supervised_action_loss"].append(float(loss.item()))
        self.loss_tracker["supervised_action_label_valid_frac"].append(
            float(valid_teacher_actions.float().mean().item())
        )
        self.loss_tracker["supervised_vibe_action_loss"].append(float(vibe_loss.item()))
        self.loss_tracker["supervised_vibe_action_label_valid_frac"].append(
            float(effective_valid_teacher_vibe_actions.float().mean().item())
        )

        return loss, shared_loss_data, False

    def on_train_phase_end(self, context: ComponentContext | None = None) -> None:
        self._create_teacher_mask(self.rollout_batch_size)
        super().on_train_phase_end(context)

    def _create_teacher_mask(self, batch_size: int) -> None:
        self.rollout_batch_size = int(batch_size)
        rand = torch.rand(self.rollout_batch_size, device=self.device)
        self.teacher_mask = rand < float(self.cfg.teacher_led_proportion)

    def _decode_teacher_actions(self, teacher_actions: Tensor) -> tuple[Tensor, Tensor, Tensor, Tensor]:
        return decode_teacher_action_labels(
            teacher_actions,
            num_primary_actions=self.num_primary_actions,
            num_vibe_actions=self.num_vibe_actions,
            noop_action_index=self.noop_action_index,
        )
