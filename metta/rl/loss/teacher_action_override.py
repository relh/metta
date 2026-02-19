"""Loss-slot component that overrides student actions with teacher actions.

This does not compute any training loss.  It only uses the rollout postprocess
hook to unconditionally replace the student's ``actions`` with the supervisor's
``teacher_actions``.  Intended for trajectory-isolation slices where agents
should behave exactly like the teacher without any gradient signal.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

import torch
from tensordict import TensorDict
from torchrl.data import Composite, UnboundedContinuous, UnboundedDiscrete

from metta.rl.loss.loss import Loss, LossConfig
from metta.rl.loss.teacher_action_utils import teacher_action_indices_and_valid_mask
from metta.rl.training import ComponentContext

# Keep: heavy module + manages circular dependency (loss <-> trainer)
if TYPE_CHECKING:
    from metta.rl.trainer_config import TrainerConfig


class TeacherActionOverrideConfig(LossConfig):
    """Config for the teacher-action override (no training loss)."""

    def create(
        self,
        policy_assets: Any,
        trainer_cfg: "TrainerConfig",
        vec_env: Any,
        device: torch.device,
        instance_name: str,
    ) -> "TeacherActionOverride":
        return TeacherActionOverride(policy_assets, trainer_cfg, vec_env, device, instance_name, self)


class TeacherActionOverride(Loss):
    """Replaces student actions with valid teacher actions during rollout.

    No gradient / training loss is produced — ``run_train`` returns zero (the
    base-class default).  The only effect is the ``run_rollout_postprocess``
    hook which copies ``teacher_actions`` into ``actions``.
    """

    cfg: TeacherActionOverrideConfig

    __slots__ = ("num_actions",)

    def __init__(
        self,
        policy_assets: Any,
        trainer_cfg: "TrainerConfig",
        vec_env: Any,
        device: torch.device,
        instance_name: str,
        cfg: "TeacherActionOverrideConfig",
    ):
        super().__init__(policy_assets, trainer_cfg, vec_env, device, instance_name, cfg)
        self.num_actions = int(self.env.single_action_space.n)

    def policy_output_keys(self, policy_td: Optional[TensorDict] = None) -> set[str]:
        return set()

    def get_experience_spec(self) -> Composite:
        scalar_f32 = UnboundedContinuous(shape=torch.Size([]), dtype=torch.float32)
        action_long = UnboundedDiscrete(shape=torch.Size([]), dtype=torch.long)

        return Composite(
            actions=action_long,
            teacher_actions=action_long,
            rewards=scalar_f32,
            dones=scalar_f32,
            truncateds=scalar_f32,
            act_log_prob=scalar_f32,
        )

    def run_rollout_postprocess(self, td: TensorDict, context: ComponentContext) -> None:
        primary_policy_name = context.current_slice_cfg.primary_policy
        student_td = td.get(primary_policy_name, None)
        teacher_actions, valid_teacher_actions = teacher_action_indices_and_valid_mask(
            student_td["teacher_actions"],
            self.num_actions,
        )
        if bool(valid_teacher_actions.any()):
            student_td["actions"][valid_teacher_actions] = teacher_actions[valid_teacher_actions].to(
                dtype=student_td["actions"].dtype
            )
