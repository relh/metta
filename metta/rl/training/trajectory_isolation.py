from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, Mapping

import torch
from pydantic import Field, model_validator
from tensordict import TensorDict

from metta.rl.training.component import TrainerComponent
from metta.rl.training.scheduler import ScheduleRule
from mettagrid.base_config import Config

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from metta.rl.training import Experience


def _set_sequence_metadata(td: TensorDict, *, batch_size: int, time_steps: int = 1) -> None:
    total = batch_size * time_steps
    td.set("batch", torch.full((total,), batch_size, dtype=torch.long, device=td.device))
    td.set("bptt", torch.full((total,), time_steps, dtype=torch.long, device=td.device))


def _pad_tensor_like(slice_value: torch.Tensor, rollout_value: torch.Tensor) -> torch.Tensor:
    if slice_value.shape == rollout_value.shape:
        return slice_value
    if slice_value.dim() != rollout_value.dim():
        return rollout_value
    if slice_value.shape[0] != rollout_value.shape[0]:
        return rollout_value

    padded = rollout_value.clone()
    overlap_sizes = tuple(min(slice_value.shape[dim], rollout_value.shape[dim]) for dim in range(1, slice_value.dim()))
    slices = (slice(None),) + tuple(slice(0, size) for size in overlap_sizes)
    padded[slices] = slice_value[slices]
    return padded


def _pad_slice_td_like(slice_td: TensorDict, rollout_td: TensorDict | None) -> TensorDict:
    padded_td = TensorDict({}, batch_size=slice_td.batch_size, device=slice_td.device)
    for key in slice_td.keys():
        slice_value = slice_td.get(key)
        rollout_value = None
        if rollout_td is not None and key in rollout_td.keys():
            rollout_value = rollout_td.get(key)

        if isinstance(slice_value, TensorDict):
            if isinstance(rollout_value, TensorDict):
                padded_td.set(key, _pad_slice_td_like(slice_value, rollout_value))
            else:
                padded_td.set(key, slice_value)
            continue

        if isinstance(slice_value, torch.Tensor) and isinstance(rollout_value, torch.Tensor):
            padded_td.set(key, _pad_tensor_like(slice_value, rollout_value))
            continue

        padded_td.set(key, slice_value)

    return padded_td


class RewardCenteringConfig(Config):
    enabled: bool = True
    beta: float = Field(default=1e-3, gt=0, le=1.0)
    initial_reward_mean: float = 0.0


class AdvantageConfig(Config):
    vtrace_rho_clip: float = Field(default=1.0, gt=0)
    vtrace_c_clip: float = Field(default=1.0, gt=0)

    # Average-reward baseline: replace r with (r - r_bar) and update r_bar via EMA.
    reward_centering: RewardCenteringConfig = Field(default_factory=RewardCenteringConfig)

    gamma: float = Field(default=1.0, ge=0, le=1.0)
    gae_lambda: float = Field(default=0.95, ge=0, le=1.0)
    advantage_method: Literal["vtrace", "delta_lambda"] = "delta_lambda"


class SamplingConfig(Config):
    """Configuration for minibatch sampling during training."""

    method: Literal["sequential", "prioritized"] = "sequential"
    prio_alpha: float = Field(default=0.0, ge=0, le=1.0)
    prio_beta0: float = Field(default=0.6, ge=0, le=1.0)


class TrajectoryIsolationSliceConfig(Config):
    """Declarative slice definition for trajectory isolation.

    Each slice corresponds to some fraction of the full environment workload and can
    be assigned one or more policies and zero or more losses.
    """

    name: str = Field(min_length=1)
    # Used in env_ratio mode; auto-computed in agent_count mode.
    env_ratio: float | None = Field(default=None, gt=0.0, le=1.0)
    agent_count: int | None = Field(default=None, gt=0)  # number of agents per env for this slice (agent_count mode)
    policies: list[str] = Field(min_length=1)
    primary_policy: str | None = None
    losses: list[str] = Field(default_factory=list)
    sampling: SamplingConfig = Field(default_factory=SamplingConfig)
    advantage: AdvantageConfig = Field(default_factory=AdvantageConfig)

    @model_validator(mode="after")
    def _validate_fields(self) -> "TrajectoryIsolationSliceConfig":
        # policy refs should be unique (within the slice)
        if len(set(self.policies)) != len(self.policies):
            raise ValueError(f"Duplicate policy reference(s) in slice '{self.name}': {self.policies}")

        # ensure the primary policy is set and in the slice
        if self.primary_policy is None:
            self.primary_policy = self.policies[0]
        elif self.primary_policy not in self.policies:
            raise ValueError(
                f"Primary policy '{self.primary_policy}' is not listed in slice '{self.name}' policies: {self.policies}"
            )

        # loss refs should be unique (within the slice)
        if len(set(self.losses)) != len(self.losses):
            raise ValueError(f"Duplicate loss reference(s) in slice '{self.name}': {self.losses}")

        return self


class TrajectoryIsolationConfig(Config):
    """Config for trajectory isolation slicing.

    Two slicing methods are supported:

    - ``env_ratio`` (default): each slice specifies a float ``env_ratio`` and
      trajectories are randomly assigned in proportion to those ratios.
    - ``agent_count``: each slice specifies an integer ``agent_count`` representing
      how many of the ``num_agents_per_env`` agents within each environment belong
      to the slice.  Assignment is deterministic and contiguous—within every
      environment the first slice's agents come first, then the second slice's,
      and so on (see ``_build_plan_agent_count`` for details).
    """

    slicing_method: Literal["env_ratio", "agent_count"] = "env_ratio"
    num_agents_per_env: int | None = Field(default=None, gt=0)
    slices: list[TrajectoryIsolationSliceConfig] = Field(default_factory=list)
    rules: list[ScheduleRule] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_fields(self) -> "TrajectoryIsolationConfig":
        if not self.slices:
            raise ValueError("Trajectory isolation config must define at least one slice.")

        slice_names = [slice_config.name for slice_config in self.slices]
        if len(set(slice_names)) != len(slice_names):
            raise ValueError(f"Duplicate slice name(s) in trajectory isolation config: {slice_names}")

        if self.slicing_method == "env_ratio":
            for slice_config in self.slices:
                if slice_config.env_ratio is None:
                    raise ValueError(
                        f"Slice '{slice_config.name}' must specify env_ratio when slicing_method is 'env_ratio'"
                    )
            total_ratio = sum(float(slice_config.env_ratio) for slice_config in self.slices)
            if abs(total_ratio - 1.0) > 1e-9:
                raise ValueError(f"Sum of slice env_ratio must be 1.0 (got {total_ratio})")

        elif self.slicing_method == "agent_count":
            if self.num_agents_per_env is None:
                raise ValueError("num_agents_per_env is required when slicing_method is 'agent_count'")
            for slice_config in self.slices:
                if slice_config.agent_count is None:
                    raise ValueError(
                        f"Slice '{slice_config.name}' must specify agent_count when slicing_method is 'agent_count'"
                    )
            total_agents = sum(slice_config.agent_count for slice_config in self.slices)
            if total_agents != self.num_agents_per_env:
                raise ValueError(
                    f"Sum of slice agent_count ({total_agents}) must equal "
                    f"num_agents_per_env ({self.num_agents_per_env})"
                )
            # Auto-compute env_ratio from agent_count so downstream code that reads
            # env_ratio (e.g. _allocate_slice_counts, schedulers) continues to work.
            for slice_config in self.slices:
                slice_config.env_ratio = slice_config.agent_count / self.num_agents_per_env

        # Loss names must be globally unique across slices.
        all_loss_names: list[str] = []
        for slice_config in self.slices:
            all_loss_names.extend(slice_config.losses)
        if len(set(all_loss_names)) != len(all_loss_names):
            raise ValueError(f"Duplicate loss name(s) across slices: {all_loss_names}")

        return self

    def validate_references(self, *, policy_assets: Mapping[str, Any], losses: Any) -> None:
        """Validate policy/loss references against available config objects.

        Args:
            policy_assets: mapping of policy-asset names (as used by TrainTool.policy_assets)
            losses: typically `TrainerConfig.losses` (LossesConfig)
        """

        available_policies = set(policy_assets.keys())
        available_losses = _available_loss_keys(losses)

        missing: list[str] = []
        for slice_config in self.slices:
            missing_policies = [
                policy_name for policy_name in slice_config.policies if policy_name not in available_policies
            ]
            if missing_policies:
                missing.append(
                    f"slice '{slice_config.name}' references missing policy asset(s): {missing_policies} "
                    f"(available: {sorted(available_policies)})"
                )

            missing_losses = [loss_name for loss_name in slice_config.losses if loss_name not in available_losses]
            if missing_losses:
                missing.append(
                    f"slice '{slice_config.name}' references missing loss key(s): {missing_losses} "
                    f"(available: {sorted(available_losses)})"
                )

        if missing:
            raise ValueError("Invalid TrajectoryIsolationConfig references:\n- " + "\n- ".join(missing))


def default_trajectory_isolation_config() -> TrajectoryIsolationConfig:
    return TrajectoryIsolationConfig(
        slices=[
            TrajectoryIsolationSliceConfig(
                name="default",
                env_ratio=1.0,
                policies=["learner0"],
                losses=["ppo_actor", "ppo_critic"],
            )
        ]
    )


def _available_loss_keys(losses: Any) -> set[str]:
    if losses is None:
        return set()
    return {str(name) for name, _cfg in losses}


@dataclass(frozen=True)
class TrajectoryIsolationSliceRuntime:
    """runtime-derived slice information. the object is meant to live for an epoch.

    Depends on:
    - scheduled/annealed ratios (which change the config and can change epoch-to-epoch)
    - device / env batch sizing
    - self._rand_assignments
    """

    cfg: TrajectoryIsolationSliceConfig
    lower: float
    upper: float
    env_mask: torch.Tensor  # bool tensor aligned with env batch dimension

    @property
    def name(self) -> str:
        return self.cfg.name

    def _split_rollout_td_per_slice(
        self,
        *,
        td: TensorDict,
        training_env_id: Any,
        context: Any,
    ) -> tuple[TensorDict | None, torch.Tensor | None]:
        """Prepare the per-slice TensorDict view and mask for a rollout step."""
        if self.env_mask.numel() == 0 or not bool(self.env_mask.any()):
            # This slice no longer has any envs assigned to it.
            return None, None

        env_indices = torch.arange(training_env_id.start, training_env_id.stop, device=td.device)
        slice_mask = self.env_mask[env_indices]
        if not bool(slice_mask.any()):
            return None, None

        base_td = td[slice_mask]
        _set_sequence_metadata(base_td, batch_size=base_td.batch_size.numel(), time_steps=1)
        slice_td = TensorDict({}, batch_size=base_td.batch_size, device=base_td.device)
        for policy_name in self.cfg.policies:
            slice_td.set(policy_name, base_td.clone())

        return slice_td, slice_mask

    def _run_loss_rollout_preprocesses(self, *, slice_td: TensorDict, context: Any) -> None:
        """Run loss preprocessors for the per-slice TensorDict."""
        context.current_slice_cfg = self.cfg
        for loss_key in self.cfg.losses:
            loss = context.losses[loss_key]
            loss.rollout_preprocess(slice_td, context)
        context.current_slice_cfg = None

    def _run_loss_rollout_postprocesses(self, *, slice_td: TensorDict, context: Any) -> None:
        """Run loss postprocessors for the per-slice TensorDict."""
        context.current_slice_cfg = self.cfg
        for loss_key in self.cfg.losses:
            loss = context.losses[loss_key]
            loss.rollout_postprocess(slice_td, context)
        context.current_slice_cfg = None


@dataclass(frozen=True)
class RolloutPolicyBatch:
    policy_name: str
    stitched_td: TensorDict
    slices: list[TrajectoryIsolationSliceRuntime]
    split_sizes: list[int]


class TrajectoryIsolator(TrainerComponent):
    """Runtime controller for trajectory isolation."""

    def __init__(
        self,
        config: TrajectoryIsolationConfig | None = None,
        *,
        rules: list[ScheduleRule] | None = None,
    ) -> None:
        super().__init__(epoch_interval=1, step_interval=0)
        self.config = config
        config_rules = list(config.rules or [])
        if rules is None:
            self.rules = list(config_rules)
        else:
            self.rules = list(rules)

        # Keep random assignments stable across epochs to preserve env->slice continuity.
        # Initialized in `register()` once context/device/env are available.
        self._rand_assignments: torch.Tensor | None = None

        # Derived per-epoch runtime slices (do not mutate config objects).
        self._slice_plan: list[TrajectoryIsolationSliceRuntime] = []

        # Precomputed per-epoch values (updated in update_slice_ids).
        self._all_policies: set[str] = set()
        self._policy_to_slices: dict[str, list[TrajectoryIsolationSliceRuntime]] = {}
        self._training_phase_primary_policy_slices: dict[str, list[TrajectoryIsolationSliceRuntime]] = {}
        self._training_phase_policy_specs: dict[str, Any] = {}
        self._training_phase_policy_slice_counts: dict[str, dict[str, int]] = {}

        # Latest per-slice TensorDict views created during rollout prep (ephemeral).
        self._slice_tds_rollout_step: dict[str, TensorDict] = {}
        self._slice_row_indices_sorted: dict[str, torch.Tensor] = {}
        self._slice_masks_rollout_step: dict[str, torch.Tensor] = {}

    def register(self, context) -> None:  # type: ignore[override]
        super().register(context)
        context.trajectory_isolator = self
        self.apply_rules()
        self.update_slice_ids(context=self.context)

    def apply_rules(self) -> None:
        """For Scheduler-driven rules."""
        if not self.rules:
            return
        for rule in self.rules:
            rule.apply(obj=self.config, ctx=self.context)

    # ----------------- Trainer callbacks -----------------
    def on_rollout_start(self) -> None:
        """Reset policy memory once per rollout phase."""
        for policy_name in self._all_policies:
            self.context.policy_assets.get(policy_name).reset_memory()

    def on_epoch_end(self, epoch: int) -> None:  # type: ignore[override]
        self.apply_rules()
        self.update_slice_ids(context=self.context)

    @property
    def slice_plan(self) -> list[TrajectoryIsolationSliceRuntime]:
        """Latest per-epoch slice runtime plan."""
        return self._slice_plan

    @property
    def latest_slice_tds(self) -> dict[str, TensorDict]:
        """Most recently prepared per-slice TensorDict views (ephemeral)."""
        return self._slice_tds_rollout_step

    @property
    def training_phase_primary_policy_slices(self) -> dict[str, list[TrajectoryIsolationSliceRuntime]]:
        return self._training_phase_primary_policy_slices

    @property
    def training_phase_policy_specs(self) -> dict[str, Any]:
        return self._training_phase_policy_specs

    @property
    def training_phase_policy_slice_counts(self) -> dict[str, dict[str, int]]:
        return self._training_phase_policy_slice_counts

    def reward_centering_initial_means(self) -> torch.Tensor:
        runtime_slices = self.slice_plan

        total_agents = int(self.context.experience.total_agents)
        device = self.context.device
        means = torch.empty((total_agents,), device=device, dtype=torch.float32)
        assigned = torch.zeros((total_agents,), device=device, dtype=torch.bool)

        for runtime_slice in runtime_slices:
            slice_mask = runtime_slice.env_mask
            if slice_mask.numel() == 0 or not bool(slice_mask.any()):
                continue
            means[slice_mask] = float(runtime_slice.cfg.advantage.reward_centering.initial_reward_mean)
            assigned |= slice_mask

        if not bool(assigned.all()):
            raise RuntimeError("Reward-centering defaults not assigned for all agents.")

        return means

    def sample_slice_minibatch(
        self,
        *,
        experience: "Experience",
        runtime_slice: TrajectoryIsolationSliceRuntime,
        count: int,
        mb_idx: int,
        advantages: torch.Tensor,
    ) -> TensorDict:
        row_indices = self._slice_row_indices(experience, runtime_slice)
        ordered_indices = self._sorted_slice_row_indices(experience, runtime_slice)
        return experience.sample_from_indices(
            indices=row_indices,
            ordered_indices=ordered_indices,
            count=count,
            mb_idx=mb_idx,
            advantages=advantages,
            sampling_config=runtime_slice.cfg.sampling,
            epoch=self.context.epoch,
            total_timesteps=self.context.config.total_timesteps,
            batch_size=self.context.config.batch_size,
        )

    def _ensure_rand_assignments(self) -> None:
        # Only valid after register().
        # keep rand_assignments around: as we update every epoch, we want to try to keep the same trajectories
        # assigned to the same policy as much as possible to support state tracking for policy memory units.
        batch_size = int(self.context.experience.total_agents)
        device = self.context.device
        if self._rand_assignments is None:
            self._rand_assignments = torch.rand(batch_size, device=device)
            return
        if self._rand_assignments.numel() != batch_size:
            # Env sizing changed; reinitialize.
            self._rand_assignments = torch.rand(batch_size, device=device)
            logger.warning(
                "Rand assignments reinitialized at epoch %s due to batch sizing change",
                getattr(self.context, "epoch", None),
            )

    def update_slice_ids(self, context: Any) -> None:
        """Recompute the per-epoch slice plan from the current config.

        Slices are allocated **in definition order**: the first slice in the config
        receives the first batch of trajectories, the second slice receives the next
        batch, and so on.  This ordering guarantee holds for both slicing methods.

        For ``env_ratio`` mode, schedulers may update env_ratio each epoch, so we
        recompute every epoch.  For ``agent_count`` mode, assignment is deterministic
        and based on within-environment agent position.
        """
        self._slice_row_indices_sorted = {}

        if self.config.slicing_method == "agent_count":
            # agent_count assignment is deterministic—reuse the existing plan unless
            # this is the first call or the batch size changed (e.g. env resize).
            batch_size = int(self.context.experience.total_agents)
            if self._slice_plan and self._slice_plan[0].env_mask.numel() == batch_size:
                plan = self._slice_plan
            else:
                plan = self._build_plan_agent_count()
        else:
            plan = self._build_plan_env_ratio(context)

        self._slice_plan = plan

        # Precompute values that depend only on slice_plan (used multiple times per epoch).
        self._all_policies = {
            policy_name for runtime_slice in self._slice_plan for policy_name in runtime_slice.cfg.policies
        }
        self._policy_to_slices = {}
        for policy_name in self._all_policies:
            self._policy_to_slices[policy_name] = [
                runtime_slice for runtime_slice in self._slice_plan if policy_name in runtime_slice.cfg.policies
            ]

        self._training_phase_primary_policy_slices = {}
        for runtime_slice in self._slice_plan:
            self._training_phase_primary_policy_slices.setdefault(runtime_slice.cfg.primary_policy, []).append(
                runtime_slice
            )

        self._training_phase_policy_specs = {
            policy_name: self.context.policy_assets.get(policy_name).get_agent_experience_spec()
            for policy_name in self._training_phase_primary_policy_slices
        }
        self._training_phase_policy_slice_counts = {
            policy_name: self._allocate_slice_counts(
                self._training_phase_primary_policy_slices[policy_name],
                self.context.experience.minibatch_segments,
            )
            for policy_name in self._training_phase_primary_policy_slices
        }

    def _build_plan_env_ratio(self, context: Any) -> list[TrajectoryIsolationSliceRuntime]:
        """Build slice plan using random assignment proportional to env_ratio.

        Random assignments are stable across epochs to preserve env-to-slice continuity.
        """
        self._ensure_rand_assignments()

        total_ratio = sum(float(slice_cfg.env_ratio) for slice_cfg in self.config.slices)
        if any(float(slice_cfg.env_ratio) < 0.0 for slice_cfg in self.config.slices):
            raise ValueError("Slice env_ratio must be >= 0.0")
        if total_ratio <= 0.0:
            raise ValueError(f"Sum of slice env_ratio must be > 0.0 (got {total_ratio}) at epoch {context.epoch}")
        if abs(total_ratio - 1.0) > 0.05:
            raise ValueError(
                f"Sum of slice env_ratio must be within 0.05 of 1.0 (got {total_ratio}) at epoch {context.epoch}"
            )
        ratio_scale = 1.0 / total_ratio  # leaving a buffer of +/- 0.05 to deal with scheduler imprecision

        plan: list[TrajectoryIsolationSliceRuntime] = []
        lower = 0.0
        for slice_cfg in self.config.slices:
            upper = lower + float(slice_cfg.env_ratio) * ratio_scale
            env_mask = (self._rand_assignments >= lower) & (self._rand_assignments < upper)
            env_mask = env_mask.to(device=self.context.device)
            if bool(env_mask.any()):
                plan.append(
                    TrajectoryIsolationSliceRuntime(
                        cfg=slice_cfg,
                        lower=float(lower),
                        upper=float(upper),
                        env_mask=env_mask,
                    )
                )
            lower = upper

        return plan

    def _build_plan_agent_count(self) -> list[TrajectoryIsolationSliceRuntime]:
        """Build slice plan using deterministic within-environment agent assignment.

        Environment observations are contiguous: the first ``num_agents_per_env``
        elements belong to env 0, the next to env 1, and so on.  Within each
        environment, slices are carved out **in definition order**—the first slice's
        ``agent_count`` agents come first, followed by the second slice's, etc.
        This guarantees that slice allocation order matches config definition order.
        """
        num_agents_per_env = self.config.num_agents_per_env
        batch_size = int(self.context.experience.total_agents)
        device = self.context.device

        if batch_size % num_agents_per_env != 0:
            raise ValueError(
                f"total_agents ({batch_size}) must be divisible by "
                f"num_agents_per_env ({num_agents_per_env}) for slicing by agent count."
            )

        # within_env_index[i] gives agent i's position inside its environment (0-indexed).
        agent_indices = torch.arange(batch_size, device=device)
        within_env_index = agent_indices % num_agents_per_env

        plan: list[TrajectoryIsolationSliceRuntime] = []
        offset = 0
        for slice_cfg in self.config.slices:
            count = slice_cfg.agent_count
            env_mask = (within_env_index >= offset) & (within_env_index < offset + count)
            if bool(env_mask.any()):
                plan.append(
                    TrajectoryIsolationSliceRuntime(
                        cfg=slice_cfg,
                        lower=float(offset / num_agents_per_env),
                        upper=float((offset + count) / num_agents_per_env),
                        env_mask=env_mask,
                    )
                )
            offset += count

        return plan

    # ----------------- Rollout Methods -----------------
    def prepare_rollout_slices(self, rollout_td: TensorDict) -> None:
        """Create per-slice, policy-keyed TensorDicts for active envs."""
        self._slice_tds_rollout_step = {}
        self._slice_masks_rollout_step = {}

        for runtime_slice in self._slice_plan:
            slice_td, slice_mask = runtime_slice._split_rollout_td_per_slice(
                td=rollout_td,
                training_env_id=self.context.training_env_id,
                context=self.context,
            )
            if slice_td is None or slice_mask is None:
                continue

            runtime_slice._run_loss_rollout_preprocesses(slice_td=slice_td, context=self.context)
            self._slice_tds_rollout_step[runtime_slice.name] = slice_td
            self._slice_masks_rollout_step[runtime_slice.name] = slice_mask

    def build_rollout_policy_batches(self) -> list[RolloutPolicyBatch]:
        """Create stitched policy batches for rollout inference."""
        batches: list[RolloutPolicyBatch] = []
        for policy_name in self._all_policies:
            slices_with_policy: list[TrajectoryIsolationSliceRuntime] = []
            tds_with_policy: list[TensorDict] = []
            for runtime_slice in self._policy_to_slices[policy_name]:
                if runtime_slice.name not in self._slice_tds_rollout_step:
                    continue
                slices_with_policy.append(runtime_slice)
                tds_with_policy.append(self._slice_tds_rollout_step[runtime_slice.name][policy_name])
            if not slices_with_policy:
                continue

            stitched_td = torch.cat(tds_with_policy, dim=0)
            _set_sequence_metadata(stitched_td, batch_size=stitched_td.batch_size.numel(), time_steps=1)
            split_sizes = [td.shape[0] for td in tds_with_policy]
            batches.append(
                RolloutPolicyBatch(
                    policy_name=policy_name,
                    stitched_td=stitched_td,
                    slices=slices_with_policy,
                    split_sizes=split_sizes,
                )
            )
        return batches

    def apply_rollout_policy_batch(self, batch: RolloutPolicyBatch) -> None:
        """Split a stitched policy TensorDict back into slice-specific TensorDicts."""
        split_tds = batch.stitched_td.split(batch.split_sizes, dim=0)
        for runtime_slice, updated_td in zip(batch.slices, split_tds, strict=True):
            _set_sequence_metadata(updated_td, batch_size=updated_td.batch_size.numel(), time_steps=1)
            self._slice_tds_rollout_step[runtime_slice.name].set(batch.policy_name, updated_td)

    def finalize_rollout_slices(self) -> None:
        """Apply loss postprocesses and select primary-policy outputs per slice."""
        for runtime_slice in self._slice_plan:
            if runtime_slice.name not in self._slice_tds_rollout_step:
                continue
            rollout_slice_td = self._slice_tds_rollout_step[runtime_slice.name]
            runtime_slice._run_loss_rollout_postprocesses(slice_td=rollout_slice_td, context=self.context)
            primary_policy_output_td = rollout_slice_td[runtime_slice.cfg.primary_policy]
            self._slice_tds_rollout_step[runtime_slice.name] = primary_policy_output_td

    def writeback_rollout_tds(self, rollout_td: TensorDict) -> None:
        """Write slice outputs back into the outer rollout TensorDict."""
        for runtime_slice in self._slice_plan:
            if runtime_slice.name in self._slice_tds_rollout_step:
                mask = self._slice_masks_rollout_step[runtime_slice.name]
                slice_td = self._slice_tds_rollout_step[runtime_slice.name]
                rollout_slice_td = rollout_td[mask]
                rollout_td[mask] = _pad_slice_td_like(slice_td, rollout_slice_td)

    def _slice_row_indices(
        self, experience: "Experience", runtime_slice: TrajectoryIsolationSliceRuntime
    ) -> torch.Tensor:
        env_ids = experience.buffer["training_env_ids"][:, 0, 0].to(
            dtype=torch.long,
            device=experience.device,
        )

        slice_env_ids = torch.nonzero(runtime_slice.env_mask, as_tuple=False).flatten()
        if slice_env_ids.numel() == 0:
            return torch.empty((0,), device=experience.device, dtype=torch.long)
        if slice_env_ids.device != experience.device:
            slice_env_ids = slice_env_ids.to(device=experience.device)

        mask = torch.isin(env_ids, slice_env_ids)
        return torch.nonzero(mask, as_tuple=False).flatten().to(dtype=torch.long)

    def _sorted_slice_row_indices(
        self, experience: "Experience", runtime_slice: TrajectoryIsolationSliceRuntime
    ) -> torch.Tensor:
        cached = self._slice_row_indices_sorted.get(runtime_slice.name)
        if cached is not None:
            return cached
        row_indices = self._slice_row_indices(experience, runtime_slice)
        ordered = torch.sort(row_indices).values
        self._slice_row_indices_sorted[runtime_slice.name] = ordered
        return ordered

    def _allocate_slice_counts(
        self, slices: list[TrajectoryIsolationSliceRuntime], minibatch_segments: int
    ) -> dict[str, int]:
        raw_counts = {
            runtime_slice.name: float(minibatch_segments) * float(runtime_slice.cfg.env_ratio)
            for runtime_slice in slices
        }
        total_target = int(round(sum(raw_counts.values())))
        counts = {name: int(math.floor(raw)) for name, raw in raw_counts.items()}
        remainder = total_target - sum(counts.values())

        if remainder > 0:
            sorted_slices = sorted(raw_counts.items(), key=lambda item: item[1] - math.floor(item[1]), reverse=True)
            for name, _raw in sorted_slices[:remainder]:
                counts[name] += 1

        return counts

    # ----------------- Evaluator/Simulation Methods -----------------
    def build_eval_plan(self, *args: Any, **kwargs: Any) -> None:
        """Hook called from the evaluator to plan per-slice evaluations.

        This will eventually return a plan describing per-slice policy specs and episode allocations.
        """

        _ = (args, kwargs)
        return None
