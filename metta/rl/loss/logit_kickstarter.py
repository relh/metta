from typing import TYPE_CHECKING, Any

import torch
from pydantic import Field

from metta.rl.loss.kickstarter import Kickstarter, KickstarterConfig

if TYPE_CHECKING:
    from metta.rl.trainer_config import TrainerConfig


class LogitKickstarterConfig(KickstarterConfig):
    teacher: str = Field(default="teacher")
    teacher_led_proportion: float = Field(default=1.0, ge=0, le=1.0)

    def create(
        self,
        policy_assets: Any,
        trainer_cfg: "TrainerConfig",
        vec_env: Any,
        device: torch.device,
        instance_name: str,
    ) -> "LogitKickstarter":
        return LogitKickstarter(
            policy_assets,
            trainer_cfg,
            vec_env,
            device,
            instance_name,
            self,
        )


class LogitKickstarter(Kickstarter):
    cfg: LogitKickstarterConfig
