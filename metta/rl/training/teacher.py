from __future__ import annotations

from typing import Literal, NamedTuple, cast

from pydantic import Field, model_validator

from metta.rl.loss.action_supervised import ActionSupervisedConfig
from metta.rl.loss.eer_cloner import EERClonerConfig
from metta.rl.loss.eer_kickstarter import EERKickstarterConfig
from metta.rl.loss.kickstarter import KickstarterConfig
from metta.rl.loss.loss import LossConfig
from metta.rl.loss.losses import LossesConfig
from metta.rl.loss.ppo_actor import PPOActorConfig
from metta.rl.policy_assets import PolicyAssetConfig
from metta.rl.trainer_config import TrainerConfig
from metta.rl.training.scheduler import LossRunGate, ScheduleRule
from metta.rl.training.training_environment import TrainingEnvironmentConfig
from metta.rl.training.trajectory_isolation import (
    TrajectoryIsolationConfig,
    TrajectoryIsolationSliceConfig,
    default_trajectory_isolation_config,
)
from mettagrid.base_config import Config

TeacherSource = Literal["scripted", "learned"]
DistillFamily = Literal["supervisor", "kickstarter", "eer_kickstarter", "eer_cloner"]
TeacherSliceMode = Literal["sliced", "mixed"]
TeacherMode = Literal[
    "scripted.supervisor.mixed",
    "scripted.supervisor.sliced",
    "scripted.eer_cloner.mixed",
    "scripted.eer_cloner.sliced",
    "learned.kickstarter.mixed",
    "learned.kickstarter.sliced",
    "learned.eer_kickstarter.mixed",
    "learned.eer_kickstarter.sliced",
]

DEFAULT_TEACHER_POLICY_URI = "metta://policy/role?miner=4&aligner=2&scrambler=4"
DEFAULT_TEACHER_MODE: TeacherMode = "scripted.supervisor.mixed"
DEFAULT_TEACHER_STEPS = 5_500_000_000
DEFAULT_TEACHER_ANNEAL_START_STEP = 2_500_000_000
DEFAULT_TEACHER_TEACHER_LED_PROPORTION = 0.0
DEFAULT_TEACHER_PPO_BEGIN_STEP = 0


class _TeacherModeParts(NamedTuple):
    source: TeacherSource
    family: DistillFamily
    slice_mode: TeacherSliceMode


def _parse_teacher_mode(mode: TeacherMode) -> _TeacherModeParts:
    source, family, slice_mode = mode.split(".")
    source_typed = cast(TeacherSource, source)
    family_typed = cast(DistillFamily, family)
    slice_typed = cast(TeacherSliceMode, slice_mode)
    if source_typed == "scripted" and family_typed not in {"supervisor", "eer_cloner"}:
        raise ValueError(f"TeacherConfig.mode='{mode}' is invalid: scripted only supports supervisor or eer_cloner")
    if source_typed == "learned" and family_typed in {"supervisor", "eer_cloner"}:
        raise ValueError(f"TeacherConfig.mode='{mode}' is invalid: learned supports kickstarter families")
    return _TeacherModeParts(source=source_typed, family=family_typed, slice_mode=slice_typed)


class TeacherConfig(Config):
    """Shared knobs for enabling teacher/supervisor driven training phases."""

    policy_uri: str | None = DEFAULT_TEACHER_POLICY_URI
    mode: TeacherMode = DEFAULT_TEACHER_MODE
    execution: Literal["env_side", "trainer_side"] = "env_side"
    steps: int | None = DEFAULT_TEACHER_STEPS
    # Teacher (led) and student slices should leave some remainder for PPO.
    # Defaults align with the standard supervisor preset.
    teacher_led_proportion: float = Field(default=DEFAULT_TEACHER_TEACHER_LED_PROPORTION, ge=0.0, le=1.0)
    student_led_proportion: float = Field(default=0.0, ge=0.0, le=1.0)
    # Optional step to begin annealing proportions; defaults to 0 when unset.
    anneal_start_step: int | None = Field(default=DEFAULT_TEACHER_ANNEAL_START_STEP, ge=0)
    # Gate PPO training until this step (useful for pure supervised/BC warm-start).
    ppo_begin_step: int = Field(default=DEFAULT_TEACHER_PPO_BEGIN_STEP, ge=0)

    @property
    def enabled(self) -> bool:
        return self.policy_uri is not None

    @model_validator(mode="after")
    def validate_proportions(self) -> "TeacherConfig":
        total = self.teacher_led_proportion + self.student_led_proportion
        if total > 1.0:
            raise ValueError(
                f"teacher_led_proportion ({self.teacher_led_proportion}) + "
                f"student_led_proportion ({self.student_led_proportion}) must be <= 1.0"
            )
        return self


def apply_teacher_phase(
    *,
    trainer_cfg: TrainerConfig,
    losses: LossesConfig | None = None,
    policy_assets: dict[str, PolicyAssetConfig] | None = None,
    training_env_cfg: TrainingEnvironmentConfig,
    scheduler_rules: list[ScheduleRule],
    scheduler_run_gates: list[LossRunGate],
    teacher_cfg: TeacherConfig,
    trajectory_isolation: TrajectoryIsolationConfig | None = None,
    default_steps: int = DEFAULT_TEACHER_STEPS,
) -> None:
    """Enable and schedule the requested teacher loss.

    Modifies the provided configs in place:
    - policy_assets: adds teacher policy if needed
    - training_env_cfg: sets supervisor_policy_uri if needed
    - scheduler_rules: adds scheduling rules
    - scheduler_run_gates: adds run gates
    - trajectory_isolation: configures if provided (required for sliced mode)
    """

    if not teacher_cfg.enabled:
        return

    if losses is None:
        losses = trainer_cfg.losses
    if policy_assets is None:
        raise ValueError("apply_teacher_phase requires explicit policy_assets")

    total_steps = teacher_cfg.steps or default_steps
    anneal_start_step = 0 if teacher_cfg.anneal_start_step is None else int(teacher_cfg.anneal_start_step)
    ppo_begin_step = int(teacher_cfg.ppo_begin_step)
    teacher_policy_name = "teacher"
    primary_policy_name = next(iter(policy_assets.keys()), "learner0")

    mode_parts = _parse_teacher_mode(teacher_cfg.mode)
    is_sliced = mode_parts.slice_mode == "sliced"
    supervisor_modes = {"supervisor", "eer_cloner"}
    teacher_asset_modes = {"kickstarter", "eer_kickstarter"}

    if mode_parts.family in supervisor_modes:
        _require_policy_uri(teacher_cfg)
        if teacher_cfg.execution == "trainer_side":
            training_env_cfg.cuda_teacher_policy_uri = teacher_cfg.policy_uri
        else:
            training_env_cfg.supervisor_policy_uri = teacher_cfg.policy_uri

    if mode_parts.family in teacher_asset_modes:
        _require_policy_uri(teacher_cfg)
        _ensure_teacher_policy_asset(
            policy_assets,
            teacher_cfg.policy_uri,
            teacher_name=teacher_policy_name,
        )

    teacher_loss_names = _select_teacher_loss_cfg(
        losses=losses,
        family=mode_parts.family,
        is_sliced=is_sliced,
        teacher_cfg=teacher_cfg,
        primary_policy_name=primary_policy_name,
        teacher_policy_name=teacher_policy_name,
    )
    if not is_sliced:
        if trajectory_isolation is None:
            raise ValueError(
                "trajectory_isolation must be provided when using mixed teacher mode. "
                "Pass TrainTool.trajectory_isolation or create one with default_trajectory_isolation_config()"
            )
        _wire_teacher_loss_into_mixed_slice(
            trajectory_isolation=trajectory_isolation,
            teacher_loss_names=teacher_loss_names,
            primary_policy_name=primary_policy_name,
            teacher_policy_name=teacher_policy_name,
            include_teacher_policy=(mode_parts.family in teacher_asset_modes),
        )

    def _gate_loss(name: str, end_at_step: int = total_steps) -> None:
        if end_at_step:
            scheduler_run_gates.extend(
                [
                    LossRunGate(loss_instance_name=name, phase="rollout", end_at_step=end_at_step),
                    LossRunGate(loss_instance_name=name, phase="train", end_at_step=end_at_step),
                ]
            )

    def _gate_loss_train_begin(name: str, *, begin_at_step: int) -> None:
        scheduler_run_gates.append(LossRunGate(loss_instance_name=name, phase="train", begin_at_step=begin_at_step))

    if ppo_begin_step > 0:
        # Delay PPO training, but keep PPO rollout active so experience collection remains unchanged.
        ppo_losses_for_gating = [
            name for name, loss_cfg in losses if name == "ppo_critic" or isinstance(loss_cfg, PPOActorConfig)
        ]
        for loss_name in ppo_losses_for_gating:
            if losses.has_loss(loss_name):
                _gate_loss_train_begin(loss_name, begin_at_step=ppo_begin_step)

    def _anneal_range(loss_name: str, attr_path: str, start_value: float, *, start_step: int, end_step: int) -> None:
        if end_step and start_value > 0.0 and start_step < end_step:
            scheduler_rules.append(
                ScheduleRule(
                    target_path=f"losses.{loss_name}.{attr_path}",
                    mode="progress",
                    style="linear",
                    start_value=start_value,
                    end_value=0.0,
                    start_agent_step=start_step,
                    end_agent_step=end_step,
                )
            )

    def _anneal(loss_name: str, attr_path: str, start_value: float) -> None:
        if total_steps:
            _anneal_range(
                loss_name,
                attr_path,
                start_value,
                start_step=anneal_start_step,
                end_step=total_steps,
            )

    def _anneal_slice_ratio(*, slice_name: str, start_value: float, end_value: float) -> None:
        if total_steps and anneal_start_step < total_steps and start_value != end_value:
            if trajectory_isolation is None:
                return
            trajectory_isolation.rules.append(
                ScheduleRule(
                    target_path=f"slices[{slice_name!r}].env_ratio",
                    mode="progress",
                    style="linear",
                    start_value=start_value,
                    end_value=end_value,
                    start_agent_step=anneal_start_step,
                    end_agent_step=total_steps,
                )
            )

    if is_sliced:
        if trajectory_isolation is None:
            raise ValueError(
                "trajectory_isolation must be provided when using sliced teacher mode. "
                "Pass TrainTool.trajectory_isolation or create one with default_trajectory_isolation_config()"
            )
        ppo_loss_names = ["ppo_critic"]
        ppo_loss_names.extend(name for name, loss_cfg in losses if isinstance(loss_cfg, PPOActorConfig))

        _setup_trajectory_isolation(
            trajectory_isolation=trajectory_isolation,
            family=mode_parts.family,
            teacher_cfg=teacher_cfg,
            primary_policy_name=primary_policy_name,
            teacher_policy_name=teacher_policy_name,
            ppo_loss_names=ppo_loss_names,
        )
        for loss_name in teacher_loss_names:
            _gate_loss(loss_name)

        if total_steps:
            ratio_sum = teacher_cfg.teacher_led_proportion + teacher_cfg.student_led_proportion
            if ratio_sum > 0:
                ppo_slice = _slice_by_name(trajectory_isolation, "ppo")
                _anneal_slice_ratio(
                    slice_name="ppo",
                    start_value=ppo_slice.env_ratio,
                    end_value=1.0,
                )
                if teacher_cfg.teacher_led_proportion > 0:
                    teacher_slice = _slice_by_name(trajectory_isolation, "teacher_led")
                    _anneal_slice_ratio(
                        slice_name="teacher_led",
                        start_value=teacher_slice.env_ratio,
                        end_value=0.0,
                    )
                if teacher_cfg.student_led_proportion > 0:
                    student_slice = _slice_by_name(trajectory_isolation, "student_led")
                    _anneal_slice_ratio(
                        slice_name="student_led",
                        start_value=student_slice.env_ratio,
                        end_value=0.0,
                    )

        return

    if mode_parts.family == "supervisor":
        supervisor = losses["supervisor"]
        _gate_loss("supervisor")
        _anneal("supervisor", attr_path="action_loss_coef", start_value=supervisor.action_loss_coef)
        _anneal("supervisor", attr_path="teacher_led_proportion", start_value=supervisor.teacher_led_proportion)

    elif mode_parts.family == "eer_kickstarter":
        eer_kick = losses["eer_kickstarter"]

        _gate_loss("eer_kickstarter")
        if total_steps:
            scheduler_rules.append(
                ScheduleRule(
                    target_path="losses.eer_kickstarter.action_loss_coef",
                    mode="progress",
                    style="linear",
                    start_value=eer_kick.action_loss_coef,
                    end_value=0.0,
                    start_agent_step=total_steps // 2,
                    end_agent_step=total_steps,
                )
            )
            scheduler_rules.append(
                ScheduleRule(
                    target_path="losses.eer_kickstarter.value_loss_coef",
                    mode="progress",
                    style="linear",
                    start_value=eer_kick.value_loss_coef,
                    end_value=0.0,
                    start_agent_step=total_steps // 2,
                    end_agent_step=total_steps,
                )
            )
            scheduler_rules.append(
                ScheduleRule(
                    target_path="losses.eer_kickstarter.r_lambda",
                    mode="progress",
                    style="linear",
                    start_value=eer_kick.r_lambda,
                    end_value=0.0,
                    start_agent_step=total_steps // 2,
                    end_agent_step=total_steps,
                )
            )
    elif mode_parts.family == "kickstarter":
        ks = losses["kickstarter"]
        ks.teacher_led_proportion = teacher_cfg.teacher_led_proportion

        _gate_loss("kickstarter")
        _anneal("kickstarter", attr_path="teacher_led_proportion", start_value=teacher_cfg.teacher_led_proportion)
        if total_steps:
            scheduler_rules.append(
                ScheduleRule(
                    target_path="losses.kickstarter.action_loss_coef",
                    mode="progress",
                    style="linear",
                    start_value=ks.action_loss_coef,
                    end_value=0.0,
                    start_agent_step=total_steps // 2,
                    end_agent_step=total_steps,
                )
            )
            scheduler_rules.append(
                ScheduleRule(
                    target_path="losses.kickstarter.value_loss_coef",
                    mode="progress",
                    style="linear",
                    start_value=ks.value_loss_coef,
                    end_value=0.0,
                    start_agent_step=total_steps // 2,
                    end_agent_step=total_steps,
                )
            )

    elif mode_parts.family == "eer_cloner":
        eer_cl = losses["eer_cloner"]

        _gate_loss("eer_cloner")
        if total_steps:
            scheduler_rules.append(
                ScheduleRule(
                    target_path="losses.eer_cloner.action_loss_coef",
                    mode="progress",
                    style="linear",
                    start_value=eer_cl.action_loss_coef,
                    end_value=0.0,
                    start_agent_step=total_steps // 2,
                    end_agent_step=total_steps,
                )
            )
            scheduler_rules.append(
                ScheduleRule(
                    target_path="losses.eer_cloner.r_lambda",
                    mode="progress",
                    style="linear",
                    start_value=eer_cl.r_lambda,
                    end_value=0.0,
                    start_agent_step=total_steps // 2,
                    end_agent_step=total_steps,
                )
            )
    else:
        raise ValueError(f"Unsupported teacher mode '{teacher_cfg.mode}'")


def _require_policy_uri(cfg: TeacherConfig) -> None:
    if not cfg.policy_uri:
        raise ValueError(f"TeacherConfig.mode='{cfg.mode}' requires policy_uri to be set.")


def _select_teacher_loss_cfg(
    *,
    losses: LossesConfig,
    family: DistillFamily,
    is_sliced: bool,
    teacher_cfg: TeacherConfig,
    primary_policy_name: str,
    teacher_policy_name: str,
) -> list[str]:
    """Instantiate and add the teacher loss config to losses if not already present."""
    loss_names: list[str] = []

    def _add_if_missing(name: str, cfg: LossConfig) -> None:
        if losses.has_loss(name):
            return
        losses.add_loss(name, cfg)

    if family == "supervisor" and not is_sliced:
        _add_if_missing("supervisor", ActionSupervisedConfig(teacher_led_proportion=teacher_cfg.teacher_led_proportion))
        loss_names.append("supervisor")
    elif family == "supervisor" and is_sliced:
        _add_if_missing("teacher_led", ActionSupervisedConfig(teacher_led_proportion=1.0))
        _add_if_missing("student_led", ActionSupervisedConfig(teacher_led_proportion=0.0))
        loss_names.extend(["teacher_led", "student_led"])
    elif family == "eer_kickstarter" and not is_sliced:
        _add_if_missing(
            "eer_kickstarter",
            EERKickstarterConfig(policy=primary_policy_name, teacher=teacher_policy_name),
        )
        loss_names.append("eer_kickstarter")
    elif family == "eer_kickstarter" and is_sliced:
        _add_if_missing("teacher_led", EERKickstarterConfig(policy=primary_policy_name, teacher=teacher_policy_name))
        _add_if_missing("student_led", EERKickstarterConfig(policy=primary_policy_name, teacher=teacher_policy_name))
        loss_names.extend(["teacher_led", "student_led"])
    elif family == "kickstarter" and not is_sliced:
        _add_if_missing(
            "kickstarter",
            KickstarterConfig(
                teacher=teacher_policy_name,
                teacher_led_proportion=teacher_cfg.teacher_led_proportion,
            ),
        )
        loss_names.append("kickstarter")
    elif family == "kickstarter" and is_sliced:
        _add_if_missing(
            "teacher_led",
            KickstarterConfig(teacher=teacher_policy_name, teacher_led_proportion=1.0),
        )
        _add_if_missing(
            "student_led",
            KickstarterConfig(teacher=teacher_policy_name, teacher_led_proportion=0.0),
        )
        loss_names.extend(["teacher_led", "student_led"])
    elif family == "eer_cloner" and not is_sliced:
        _add_if_missing("eer_cloner", EERClonerConfig())
        loss_names.append("eer_cloner")
    elif family == "eer_cloner" and is_sliced:
        _add_if_missing("teacher_led", EERClonerConfig())
        _add_if_missing("student_led", EERClonerConfig())
        loss_names.extend(["teacher_led", "student_led"])
    else:
        raise ValueError(f"Unsupported teacher mode family '{family}' with sliced={is_sliced}")

    return loss_names


def _ensure_teacher_policy_asset(
    policy_assets: dict[str, PolicyAssetConfig],
    policy_uri: str | None,
    *,
    teacher_name: str,
) -> None:
    if not policy_uri:
        raise ValueError("Teacher policy uri is required to configure policy assets")

    existing = policy_assets.get(teacher_name)
    if existing is None:
        policy_assets[teacher_name] = PolicyAssetConfig(
            uri=policy_uri,
            architecture=None,
            checkpoint=False,
            trainable=False,
            optimizer=None,
        )
        return

    if existing.trainable or existing.checkpoint:
        raise ValueError(
            f"policy_assets['{teacher_name}'] must be trainable=False and checkpoint=False "
            "when used as a teacher policy"
        )


def _setup_trajectory_isolation(
    *,
    trajectory_isolation: TrajectoryIsolationConfig,
    family: DistillFamily,
    teacher_cfg: TeacherConfig,
    primary_policy_name: str,
    teacher_policy_name: str,
    ppo_loss_names: list[str],
) -> None:
    ppo_proportion = 1.0 - teacher_cfg.teacher_led_proportion - teacher_cfg.student_led_proportion
    if ppo_proportion <= 0.0:
        raise ValueError("Sliced teacher modes require teacher_led_proportion + student_led_proportion < 1.0")
    base_slice = (
        trajectory_isolation.slices[0].model_copy(deep=True)
        if trajectory_isolation.slices
        else default_trajectory_isolation_config().slices[0]
    )

    def _clone_slice(
        *,
        name: str,
        env_ratio: float,
        policies: list[str],
        losses: list[str],
    ) -> TrajectoryIsolationSliceConfig:
        return base_slice.model_copy(
            update={
                "name": name,
                "env_ratio": env_ratio,
                "policies": policies,
                "primary_policy": policies[0],
                "losses": losses,
            }
        )

    slices: list[TrajectoryIsolationSliceConfig] = []
    slices.append(
        _clone_slice(
            name="ppo",
            env_ratio=ppo_proportion,
            policies=[primary_policy_name],
            losses=list(ppo_loss_names),
        )
    )

    use_teacher_policy = family not in {"supervisor", "eer_cloner"}
    led_policies = [primary_policy_name] + ([teacher_policy_name] if use_teacher_policy else [])
    led_losses = list(ppo_loss_names) if family in {"supervisor", "kickstarter"} else []

    if teacher_cfg.teacher_led_proportion > 0:
        slices.append(
            _clone_slice(
                name="teacher_led",
                env_ratio=teacher_cfg.teacher_led_proportion,
                policies=led_policies,
                losses=led_losses + ["teacher_led"],
            )
        )
    if teacher_cfg.student_led_proportion > 0:
        slices.append(
            _clone_slice(
                name="student_led",
                env_ratio=teacher_cfg.student_led_proportion,
                policies=led_policies,
                losses=led_losses + ["student_led"],
            )
        )

    trajectory_isolation.slices = slices


def _slice_by_name(trajectory_isolation: TrajectoryIsolationConfig, name: str) -> TrajectoryIsolationSliceConfig:
    for slice_cfg in trajectory_isolation.slices:
        if slice_cfg.name == name:
            return slice_cfg
    raise KeyError(f"Missing trajectory slice '{name}'")


def _wire_teacher_loss_into_mixed_slice(
    *,
    trajectory_isolation: TrajectoryIsolationConfig,
    teacher_loss_names: list[str],
    primary_policy_name: str,
    teacher_policy_name: str,
    include_teacher_policy: bool,
) -> None:
    matching_slices = [
        slice_cfg for slice_cfg in trajectory_isolation.slices if slice_cfg.primary_policy == primary_policy_name
    ]
    if len(matching_slices) != 1:
        raise ValueError(
            "Mixed teacher mode requires exactly one trajectory isolation slice with "
            f"primary_policy={primary_policy_name!r}. Found: "
            f"{[(s.name, s.primary_policy) for s in trajectory_isolation.slices]!r}"
        )

    target_slice = matching_slices[0]

    for loss_name in teacher_loss_names:
        used_in = [slice_cfg.name for slice_cfg in trajectory_isolation.slices if loss_name in slice_cfg.losses]
        if used_in and used_in != [target_slice.name]:
            raise ValueError(
                "Mixed teacher mode expects teacher loss to be referenced by a single slice. "
                f"loss={loss_name!r} referenced by slices={used_in!r}"
            )
        if loss_name not in target_slice.losses:
            target_slice.losses.append(loss_name)

    if include_teacher_policy and teacher_policy_name not in target_slice.policies:
        target_slice.policies.append(teacher_policy_name)
