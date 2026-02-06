from typing import TYPE_CHECKING, Any, Optional

import torch
import torch.nn.functional as F
from pydantic import Field
from tensordict import TensorDict
from torch import Tensor
from torchrl.data import Composite, UnboundedContinuous

from metta.rl.loss.loss import Loss, LossConfig
from metta.rl.policy_assets import PolicyAssetRegistry
from metta.rl.training import ComponentContext, TrainingEnvironment

# Keep: heavy module + manages circular dependency (loss <-> trainer)
if TYPE_CHECKING:
    from metta.rl.trainer_config import TrainerConfig


class KickstarterConfig(LossConfig):
    teacher: str = Field(default="teacher0")  # key in the policy_assets dict
    action_loss_coef: float = Field(default=0.6, ge=0, le=1.0)
    value_loss_coef: float = Field(default=1.0, ge=0, le=1.0)
    temperature: float = Field(default=2.0, gt=0)
    teacher_led_proportion: float = Field(default=0.0, ge=0, le=1.0)  # at 0.0, it's purely student-led

    def create(
        self,
        policy_assets: Any,
        trainer_cfg: "TrainerConfig",
        vec_env: Any,
        device: torch.device,
        instance_name: str,
    ) -> "Kickstarter":
        """Create Kickstarter loss instance."""
        return Kickstarter(
            policy_assets,
            trainer_cfg,
            vec_env,
            device,
            instance_name,
            self,
        )


class Kickstarter(Loss):
    """This uses another policy that is forwarded during rollout, here, in the loss and then compares its logits and
    value against the student's using a KL divergence and MSE loss respectively.
    """

    cfg: "KickstarterConfig"

    __slots__ = ("teacher_policy",)

    def __init__(
        self,
        policy_assets: PolicyAssetRegistry,
        trainer_cfg: "TrainerConfig",
        env: TrainingEnvironment,
        device: torch.device,
        instance_name: str,
        cfg: "KickstarterConfig",
    ):
        super().__init__(policy_assets, trainer_cfg, env, device, instance_name, cfg)
        self.teacher_policy = policy_assets.get(cfg.teacher)

    def get_experience_spec(self) -> Composite:
        # Get action space size for logits shape
        act_space = self.env.single_action_space
        num_actions = act_space.n

        scalar_f32 = UnboundedContinuous(shape=torch.Size([]), dtype=torch.float32)
        logits_f32 = UnboundedContinuous(shape=torch.Size([num_actions]), dtype=torch.float32)

        return Composite(
            teacher_logits=logits_f32,
            teacher_values=scalar_f32,
        )

    def run_rollout_postprocess(self, td: TensorDict, context: ComponentContext) -> None:
        teacher_td = td.get(self.cfg.teacher, None)
        primary_policy_name = self._primary_policy_name()
        student_td = td.get(primary_policy_name, None)
        # move teacher's logits and values to the student's td, under the keys listed in our experience spec.
        # we only pass the student_td to the buffer for saving by key listed in the experience spec.
        student_td.set("teacher_logits", teacher_td.get("logits"))
        student_td.set("teacher_values", teacher_td.get("values"))

        if torch.rand(1) < self.cfg.teacher_led_proportion:
            # overwrite student actions w teacher actions with some probability. anneal this.
            student_td["actions"] = teacher_td["actions"]

    def policy_output_keys(self, policy_td: Optional[TensorDict] = None) -> set[str]:
        return {"logits", "values"}

    def run_train(
        self,
        shared_loss_data: TensorDict,
        context: ComponentContext,
        mb_idx: int,
    ) -> tuple[Tensor, TensorDict, bool]:
        minibatch: TensorDict = shared_loss_data["sampled_mb"]
        B, TT = minibatch.batch_size

        student_td: TensorDict = shared_loss_data["policy_td"].reshape(B * TT)

        # action loss
        temperature = self.cfg.temperature
        teacher_logits: Tensor = minibatch["teacher_logits"]
        teacher_logits = teacher_logits.to(dtype=torch.float32).reshape(B * TT, -1).detach()
        student_logits: Tensor = student_td["logits"]
        student_logits = student_logits.to(dtype=torch.float32)
        teacher_log_probs = F.log_softmax(teacher_logits / temperature, dim=-1).detach()
        student_log_probs = F.log_softmax(student_logits / temperature, dim=-1)
        student_probs = torch.exp(student_log_probs)
        ks_action_loss = (temperature**2) * (
            (student_probs * (student_log_probs - teacher_log_probs)).sum(dim=-1).mean()
        )

        # value loss
        teacher_value: Tensor = minibatch["teacher_values"]
        teacher_value = teacher_value.to(dtype=torch.float32).reshape(B * TT).detach()
        student_value: Tensor = student_td["values"]
        student_value = student_value.to(dtype=torch.float32)
        ks_value_loss = ((teacher_value.detach() - student_value) ** 2).mean()

        loss = ks_action_loss * self.cfg.action_loss_coef + ks_value_loss * self.cfg.value_loss_coef

        assert self.loss_tracker is not None
        self.loss_tracker["ks_act_loss"].append(float(ks_action_loss.item()))
        self.loss_tracker["ks_val_loss"].append(float(ks_value_loss.item()))
        self.loss_tracker["ks_act_loss_coef"].append(float(self.cfg.action_loss_coef))
        self.loss_tracker["ks_val_loss_coef"].append(float(self.cfg.value_loss_coef))

        return loss, shared_loss_data, False
