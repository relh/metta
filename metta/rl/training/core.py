import logging
from typing import Any, Optional

import numpy as np
import torch
from cortex.consistent_dropout import reset_consistent_dropout
from pydantic import ConfigDict
from tensordict import NonTensorData, TensorDict
from torch import Tensor

from metta.rl.advantage import compute_advantage
from metta.rl.loss.loss import Loss
from metta.rl.loss.ppo_actor import PPOActor
from metta.rl.training import ComponentContext, Experience, TrainingEnvironment
from metta.rl.training.trajectory_isolation import TrajectoryIsolator
from metta.rl.utils import add_dummy_loss_for_unused_params, ensure_sequence_metadata, forward_policy_for_training
from mettagrid.base_config import Config
from mettagrid.util.dict_utils import unroll_nested_dict

logger = logging.getLogger(__name__)
_PER_AGENT_INFO_ROWS_KEY = "_per_agent_infos"
_MISSING = object()


def _collect_requested_env_info_keys(*, losses: dict[str, Loss], context: ComponentContext) -> set[str]:
    requested_keys: set[str] = set()
    for loss in losses.values():
        if not loss._loss_gate_allows("rollout", context):
            continue
        required_fn = getattr(loss, "required_env_info_keys", None)
        if required_fn is None:
            continue
        required = required_fn()
        if required:
            requested_keys.update(str(key) for key in required)
    return requested_keys


def _resolve_missing_env_info_scalar_default(*, losses: dict[str, Loss], context: ComponentContext) -> float | None:
    defaults: list[float | None] = []
    for loss in losses.values():
        if not loss._loss_gate_allows("rollout", context):
            continue
        required_fn = getattr(loss, "required_env_info_keys", None)
        if required_fn is None:
            continue
        required = required_fn()
        if not required:
            continue
        defaults.append(loss.env_info_missing_scalar_default())

    if not defaults:
        return None
    if all(value is None for value in defaults):
        return None
    if any(value is None for value in defaults):
        raise RuntimeError(
            "Conflicting env_info missing-key handling across active losses. "
            "Either all losses must use strict missing-key checks or all must define a numeric default."
        )

    numeric_defaults = [float(value) for value in defaults if value is not None]
    first_default = numeric_defaults[0]
    for value in numeric_defaults[1:]:
        if value != first_default:
            raise RuntimeError(
                f"Conflicting env_info missing-key defaults across active losses: {sorted(set(numeric_defaults))}"
            )
    return first_default


def _partition_requested_env_info_keys(
    requested_keys: set[str],
) -> tuple[tuple[str, ...], tuple[str, ...], str]:
    requested_sorted = tuple(sorted(str(key) for key in requested_keys))
    requested_agent_keys = tuple(key for key in requested_sorted if key.startswith("agent/"))
    requested_env_keys = tuple(key for key in requested_sorted if not key.startswith("agent/"))
    requested_keys_desc = str(list(requested_sorted))
    return requested_env_keys, requested_agent_keys, requested_keys_desc


def _normalize_info_rows(info: Any) -> list[dict[str, Any]]:
    if info is None:
        return []
    if isinstance(info, dict):
        return [info]
    if isinstance(info, list):
        return list(info)
    raise RuntimeError(f"Unexpected vecenv info payload type: {type(info).__name__}")


def _flatten_env_info_row(info_row: dict[str, Any]) -> dict[str, Any]:
    flattened: dict[str, Any] = {}
    for key, value in unroll_nested_dict(info_row):
        if key == _PER_AGENT_INFO_ROWS_KEY:
            continue
        flattened[key] = value
    return flattened


def _lookup_env_info_value(row: dict[str, Any], key: str) -> Any:
    if key in row:
        return row[key]
    if key.startswith("env_"):
        raw_key = key[len("env_") :]
        if raw_key in row:
            return row[raw_key]
    elif "/" in key:
        root, remainder = key.split("/", 1)
        env_key = f"env_{root}/{remainder}"
        if env_key in row:
            return row[env_key]
    return _MISSING


def _coerce_env_info_scalar(*, value: Any, key: str, row_index: int) -> float:
    if torch.is_tensor(value):
        tensor_value = value.detach()
        if tensor_value.numel() != 1:
            raise RuntimeError(
                f"env_info[{row_index}]['{key}'] must be scalar-like, got tensor shape {tuple(tensor_value.shape)}"
            )
        return float(tensor_value.item())
    if isinstance(value, np.ndarray):
        if value.size != 1:
            raise RuntimeError(f"env_info[{row_index}]['{key}'] must be scalar-like, got array shape {value.shape}")
        return float(value.item())
    if isinstance(value, np.generic):
        return float(value.item())
    if isinstance(value, (int, float, bool)):
        return float(value)
    raise RuntimeError(f"env_info[{row_index}]['{key}'] must be numeric scalar, got {type(value).__name__}: {value!r}")


def _tensorize_requested_env_info(
    *,
    info_rows: list[dict[str, Any]],
    requested_keys: set[str] | None = None,
    requested_env_keys: tuple[str, ...] | None = None,
    requested_agent_keys: tuple[str, ...] | None = None,
    requested_keys_desc: str | None = None,
    missing_scalar_default: float | None = None,
    batch_size: int,
    num_env_rows: int,
    agents_per_env: int,
    device: torch.device,
) -> TensorDict:
    if requested_env_keys is None or requested_agent_keys is None or requested_keys_desc is None:
        if requested_keys is None:
            raise RuntimeError("Expected requested_keys or pre-partitioned env/agent key tuples")
        requested_env_keys, requested_agent_keys, requested_keys_desc = _partition_requested_env_info_keys(
            requested_keys
        )

    row_count = len(info_rows)
    if row_count <= 0:
        raise RuntimeError(f"Requested env_info keys {requested_keys_desc} require non-empty info rows")

    per_agent_aligned = row_count == batch_size
    per_env_aligned = row_count == num_env_rows

    if per_env_aligned:
        expected_batch = num_env_rows * agents_per_env
        if batch_size != expected_batch:
            raise RuntimeError(
                f"Requested env_info keys {requested_keys_desc} expected rollout batch to match "
                f"num_env_rows*agents_per_env ({num_env_rows}*{agents_per_env}={expected_batch}), "
                f"got batch_size={batch_size}"
            )
    elif row_count == 1 and num_env_rows > 1:
        raise RuntimeError(
            f"Requested env_info keys {requested_keys_desc} received a single aggregated info row "
            f"for a multi-env batch (num_env_rows={num_env_rows}). Per-env alignment is required."
        )
    elif not per_agent_aligned:
        raise RuntimeError(
            f"Requested env_info keys {requested_keys_desc} expected per-agent ({batch_size}) "
            f"or per-environment ({num_env_rows}) info rows, got {row_count}"
        )

    flattened_env_rows: list[dict[str, Any]] = []
    for row_index, info_row in enumerate(info_rows):
        if not isinstance(info_row, dict):
            raise RuntimeError(f"env_info row {row_index} must be dict, got {type(info_row).__name__}")
        flattened_env_rows.append(_flatten_env_info_row(info_row))

    flattened_agent_rows: list[dict[str, Any]] = []
    if requested_agent_keys:
        has_embedded_per_agent_infos = per_agent_aligned and all(
            isinstance(info_row, dict) and _PER_AGENT_INFO_ROWS_KEY in info_row for info_row in info_rows
        )
        if per_agent_aligned and not has_embedded_per_agent_infos:
            flattened_agent_rows = flattened_env_rows
        else:
            for row_index, info_row in enumerate(info_rows):
                per_agent_infos = info_row.get(_PER_AGENT_INFO_ROWS_KEY)
                if per_agent_infos is None:
                    raise RuntimeError(
                        f"Requested agent info keys {list(requested_agent_keys)} require key "
                        f"'{_PER_AGENT_INFO_ROWS_KEY}' in env info row {row_index}"
                    )
                if isinstance(per_agent_infos, list):
                    ordered_agent_rows = per_agent_infos
                elif isinstance(per_agent_infos, dict):
                    ordered_agent_rows = [
                        per_agent_infos.get(agent_index, per_agent_infos.get(str(agent_index), _MISSING))
                        for agent_index in range(agents_per_env)
                    ]
                    missing_idx = next(
                        (idx for idx, value in enumerate(ordered_agent_rows) if value is _MISSING),
                        None,
                    )
                    if missing_idx is not None:
                        raise RuntimeError(
                            f"env_info row {row_index} '{_PER_AGENT_INFO_ROWS_KEY}' missing agent index {missing_idx}"
                        )
                else:
                    raise RuntimeError(
                        f"env_info row {row_index} '{_PER_AGENT_INFO_ROWS_KEY}' must be list or dict, "
                        f"got {type(per_agent_infos).__name__}"
                    )
                if len(ordered_agent_rows) != agents_per_env:
                    raise RuntimeError(
                        f"env_info row {row_index} '{_PER_AGENT_INFO_ROWS_KEY}' must contain {agents_per_env} "
                        f"entries, got {len(ordered_agent_rows)}"
                    )
                for agent_offset, agent_row in enumerate(ordered_agent_rows):
                    if not isinstance(agent_row, dict):
                        raise RuntimeError(
                            f"agent info row {row_index}:{agent_offset} must be dict, got {type(agent_row).__name__}"
                        )
                    flattened_agent_rows.append(_flatten_env_info_row(agent_row))

        if len(flattened_agent_rows) != batch_size:
            raise RuntimeError(
                f"Requested agent info keys {list(requested_agent_keys)} expected {batch_size} flattened "
                f"agent rows, got {len(flattened_agent_rows)}"
            )

    env_info_td = TensorDict({}, batch_size=[batch_size], device=device)
    for key in requested_env_keys:
        values: list[float] = []
        for row_index, row in enumerate(flattened_env_rows):
            value = _lookup_env_info_value(row, key)
            if value is _MISSING:
                if missing_scalar_default is None:
                    raise RuntimeError(f"Missing requested env info key '{key}' in info row {row_index}")
                values.append(float(missing_scalar_default))
                continue
            values.append(_coerce_env_info_scalar(value=value, key=key, row_index=row_index))
        value_tensor = torch.tensor(values, dtype=torch.float32, device=device)
        if per_env_aligned and not per_agent_aligned:
            value_tensor = value_tensor.repeat_interleave(agents_per_env)
        env_info_td[key] = value_tensor

    for key in requested_agent_keys:
        agent_key = key[len("agent/") :]
        if not agent_key:
            raise RuntimeError("Requested agent info key 'agent/' is invalid; include a key suffix")
        values = []
        for row_index, row in enumerate(flattened_agent_rows):
            if agent_key not in row:
                if missing_scalar_default is None:
                    raise RuntimeError(f"Missing requested agent info key '{key}' in agent row {row_index}")
                values.append(float(missing_scalar_default))
                continue
            values.append(_coerce_env_info_scalar(value=row[agent_key], key=key, row_index=row_index))
        env_info_td[key] = torch.tensor(values, dtype=torch.float32, device=device)
    return env_info_td


class _PinnedCudaToCpuStager:
    """Copy CUDA tensors into a small pool of pinned CPU buffers.

    This avoids `tensor.cpu()` allocating pageable CPU storage, and can reduce
    GPU->CPU handoff time when the consumer requires a NumPy array.
    """

    def __init__(self, *, num_slots: int = 2):
        if num_slots < 1:
            raise ValueError(f"num_slots must be >= 1, got {num_slots}")
        self._slot = 0
        self._bufs: list[Tensor | None] = [None] * num_slots
        self._events: list[torch.cuda.Event | None] = [None] * num_slots

    def to_numpy_ready_cpu(self, x: Tensor) -> tuple[Tensor, torch.cuda.Event]:
        if x.device.type != "cuda":
            raise ValueError(f"Expected CUDA tensor, got device={x.device!r}")

        slot = self._slot
        self._slot = (self._slot + 1) % len(self._bufs)

        ev = self._events[slot]
        if ev is None:
            ev = torch.cuda.Event()
            self._events[slot] = ev
        else:
            # Ensure previous in-flight D2H copy into this buffer is done.
            if not ev.query():
                ev.synchronize()

        buf = self._bufs[slot]
        if buf is None or buf.shape != x.shape or buf.dtype != x.dtype:
            buf = torch.empty(x.shape, dtype=x.dtype, device="cpu", pin_memory=True)
            self._bufs[slot] = buf

        buf.copy_(x, non_blocking=True)
        ev.record()
        return buf, ev


class RolloutResult(Config):
    """Results from a rollout phase."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    raw_infos: list[dict[str, Any]]
    agent_steps: int
    training_env_id: slice


class CoreTrainingLoop:
    """Handles the core training loop with rollout and training phases."""

    def __init__(
        self,
        experience: Experience,
        losses: dict[str, Loss],
        device: torch.device,
        context: ComponentContext,
        trajectory_isolator: TrajectoryIsolator,
        cuda_teacher=None,
    ):
        """Initialize core training loop.

        Args:
            experience: Experience buffer for storing rollouts
            losses: Dictionary of loss instances to use
            device: Device to run on
            cuda_teacher: Optional CudaTeacherRunner for trainer-side teacher actions
        """
        self.experience = experience
        self.losses = losses
        self.device = device
        self.accumulate_minibatches = experience.accumulate_minibatches
        self.context = context
        self.cuda_teacher = cuda_teacher
        self.last_action = torch.zeros(
            experience.total_agents,
            1,
            dtype=torch.int32,
            device=device,
        )
        # Cache environment indices to avoid reallocating per rollout batch
        self._env_index_cache = experience._range_tensor.to(device=device)
        self._reward_centering_beta_by_agent = torch.empty((0,), device=device, dtype=torch.float32)
        self.trajectory_isolator = trajectory_isolator
        self._rollout_transfer_stream: torch.cuda.Stream | None = (
            torch.cuda.Stream(device=device) if device.type == "cuda" else None
        )
        self._action_send_stager: _PinnedCudaToCpuStager | None = (
            _PinnedCudaToCpuStager() if device.type == "cuda" else None
        )

    def _validate_trajectory_slices_for_epoch(self) -> None:
        runtime_slices = self.trajectory_isolator.slice_plan
        if not runtime_slices:
            raise RuntimeError("Trajectory isolation slice plan is empty for this epoch.")
        if not self.trajectory_isolator.training_phase_primary_policy_slices:
            raise RuntimeError("Trajectory isolation has no policies configured for this epoch.")
        # Skip row-level validation until after first epoch, ie until the replay buffer has real env ids.
        if self.experience.full_rows == 0 and int(self.experience.t_in_row.max().item()) == 0:
            return
        for runtime_slice in runtime_slices:
            row_indices = self.trajectory_isolator._slice_row_indices(self.experience, runtime_slice)
            if row_indices.numel() == 0:
                raise RuntimeError(
                    f"Trajectory isolation slice '{runtime_slice.name}' has no assigned rows for this epoch."
                )

    def _prepare_reward_centering_betas(self) -> None:
        runtime_slices = self.trajectory_isolator.slice_plan
        betas = torch.empty((self.experience.total_agents,), device=self.device, dtype=torch.float32)
        assigned = torch.zeros((self.experience.total_agents,), device=self.device, dtype=torch.bool)
        for runtime_slice in runtime_slices:
            slice_mask = runtime_slice.env_mask
            if slice_mask.device != self.device:
                slice_mask = slice_mask.to(device=self.device, dtype=torch.bool)
            if not bool(slice_mask.any()):
                continue
            betas[slice_mask] = float(runtime_slice.cfg.advantage.reward_centering.beta)
            assigned |= slice_mask

        assert bool(assigned.all()), "Reward-centering beta not assigned for all agents."
        self._reward_centering_beta_by_agent = betas

    def rollout_phase(
        self,
        env: TrainingEnvironment,
        context: ComponentContext,
    ) -> RolloutResult:
        """Perform rollout phase to collect experience.

        Args:
            env: Vectorized environment to collect from
            context: Shared trainer context providing rollout state

        Returns:
            RolloutResult with collected info
        """
        self._validate_trajectory_slices_for_epoch()
        raw_infos: list[dict[str, Any]] = []
        self.experience.reset_for_rollout()

        # Reset consistent dropout masks so fresh masks are generated for this rollout.
        # These masks will be cached and reused during the training phase to reduce
        # gradient variance (see: Hausknecht & Wagener, 2022).
        for policy in context.policy_assets.policies.values():
            reset_consistent_dropout(policy)

        # Notify losses of rollout start
        for loss in self.losses.values():
            loss.on_rollout_start(context)
        self.trajectory_isolator.on_rollout_start()
        self._prepare_reward_centering_betas()
        requested_env_info_keys = _collect_requested_env_info_keys(losses=self.losses, context=context)
        missing_env_info_scalar_default = _resolve_missing_env_info_scalar_default(losses=self.losses, context=context)
        requested_env_keys: tuple[str, ...] = ()
        requested_agent_keys: tuple[str, ...] = ()
        requested_keys_desc = "[]"
        if requested_env_info_keys:
            requested_env_keys, requested_agent_keys, requested_keys_desc = _partition_requested_env_info_keys(
                requested_env_info_keys
            )
            agents_per_env = int(env.policy_env_info.num_agents)
            if agents_per_env <= 0:
                raise RuntimeError(f"Invalid agents_per_env={agents_per_env}; must be positive")
        else:
            agents_per_env = 0

        # Get buffer for storing experience
        buffer_step = self.experience.buffer[self.experience.row_slot_ids, self.experience.t_in_row - 1]
        store_keys = self.experience.store_keys
        if store_keys:
            buffer_step = buffer_step.select(*store_keys)

        total_steps = 0
        last_env_id: slice | None = None

        while not self.experience.ready_for_training:
            # Get observation from environment
            with context.stopwatch("_rollout.env_wait"):
                o, r, d, t, ta, info, training_env_id, _, num_steps = env.get_observations()
            last_env_id = training_env_id
            info_rows = _normalize_info_rows(info)
            # Prepare data for policy
            with context.stopwatch("_rollout.td_prep"):
                td = buffer_step[training_env_id].clone()
                target_device = td.device
                assert target_device is not None
                all_inputs_pinned_cpu = all(x.device.type == "cpu" and x.is_pinned() for x in (o, r, d, t, ta))
                transfer_stream = (
                    self._rollout_transfer_stream if target_device.type == "cuda" and all_inputs_pinned_cpu else None
                )
                if transfer_stream is not None:
                    # Launch transfers on a dedicated stream so they can overlap with
                    # other GPU work enqueued on the default stream (clone/indexing/etc.).
                    with torch.cuda.stream(transfer_stream):
                        env_obs = o.to(device=target_device, non_blocking=True)
                        rewards = r.to(device=target_device, non_blocking=True)
                        dones = d.to(device=target_device, dtype=torch.float32, non_blocking=True)
                        truncateds = t.to(device=target_device, dtype=torch.float32, non_blocking=True)
                        teacher_actions = ta.to(device=target_device, dtype=torch.long, non_blocking=True)
                else:
                    env_obs = o.to(device=target_device, non_blocking=True)
                    rewards = r.to(device=target_device, non_blocking=True)
                agent_ids = self._env_index_cache[training_env_id]
                td["agent_slot_ids"] = agent_ids.unsqueeze(1)

                avg_reward = context.state.avg_reward
                baseline = avg_reward[agent_ids]

                # CRITICAL FIX for MPS: Convert dtype BEFORE moving to device, and use blocking transfer
                # MPS has two bugs:
                # 1. bool->float32 conversion during .to(device=mps, dtype=float32) produces NaN
                # 2. non_blocking=True causes race conditions with uninitialized data
                # Solution: Convert dtype on CPU first, then use blocking transfer to MPS
                if target_device.type == "mps":
                    dones = d.to(dtype=torch.float32).to(device=target_device, non_blocking=False)
                    truncateds = t.to(dtype=torch.float32).to(device=target_device, non_blocking=False)
                    teacher_actions = ta.to(device=target_device, dtype=torch.long, non_blocking=False)
                elif transfer_stream is None:
                    # On CUDA/CPU, combined conversion is safe and faster
                    dones = d.to(device=target_device, dtype=torch.float32, non_blocking=True)
                    truncateds = t.to(device=target_device, dtype=torch.float32, non_blocking=True)
                    teacher_actions = ta.to(device=target_device, dtype=torch.long, non_blocking=True)

                if self.cuda_teacher is not None:
                    obs_gpu = o.to(device=self.device, non_blocking=True)
                    ta_gpu = torch.empty(o.shape[0], device=self.device, dtype=torch.long)
                    # CUDA teacher state must reset on any episode boundary, including time-limit truncations.
                    episode_reset_mask_gpu = torch.logical_or(d, t).to(
                        device=self.device, dtype=torch.bool, non_blocking=True
                    )
                    self.cuda_teacher.step_batch(obs_gpu, ta_gpu, episode_reset_mask_gpu)
                    teacher_actions = ta_gpu.to(device=target_device, dtype=torch.long, non_blocking=True)

                if transfer_stream is not None:
                    current_stream = torch.cuda.current_stream(device=target_device)
                    current_stream.wait_stream(transfer_stream)
                    env_obs.record_stream(current_stream)
                    rewards.record_stream(current_stream)
                    dones.record_stream(current_stream)
                    truncateds.record_stream(current_stream)
                    teacher_actions.record_stream(current_stream)

                td["env_obs"] = env_obs
                td["rewards"] = rewards
                rewards_f32 = td["rewards"].to(dtype=torch.float32)
                # Default behavior: initialize each agent's baseline from its first observed reward.
                uninitialized = torch.isnan(baseline)
                if bool(uninitialized.any()):
                    baseline = torch.where(uninitialized, rewards_f32, baseline)
                td["reward_baseline"] = baseline
                td["dones"] = dones
                td["truncateds"] = truncateds
                td["teacher_actions"] = teacher_actions
                # Row-aligned state: provide row slot id and position within row
                row_ids = self.experience.row_slot_ids[training_env_id]
                t_in_row = self.experience.t_in_row[training_env_id]
                td["row_id"] = row_ids
                td["t_in_row"] = t_in_row
                self.add_last_action_to_td(td)

                if requested_env_info_keys:
                    batch_size = int(td.batch_size[0])
                    if batch_size % agents_per_env != 0:
                        raise RuntimeError(
                            f"Rollout batch_size={batch_size} must be divisible by agents_per_env={agents_per_env} "
                            "to align per-environment info rows"
                        )
                    num_env_rows = batch_size // agents_per_env
                    td["env_info"] = _tensorize_requested_env_info(
                        info_rows=info_rows,
                        requested_env_keys=requested_env_keys,
                        requested_agent_keys=requested_agent_keys,
                        requested_keys_desc=requested_keys_desc,
                        missing_scalar_default=missing_env_info_scalar_default,
                        batch_size=batch_size,
                        num_env_rows=num_env_rows,
                        agents_per_env=agents_per_env,
                        device=target_device,
                    )

                ensure_sequence_metadata(td, batch_size=td.batch_size.numel(), time_steps=1)

            # Allow losses to mutate td (policy inference, bookkeeping, etc.)
            with context.stopwatch("_rollout.inference"):
                context.training_env_id = training_env_id
                self.trajectory_isolator.prepare_rollout_slices(rollout_td=td)
                policy_batches = self.trajectory_isolator.build_rollout_policy_batches()
                for batch in policy_batches:
                    policy = context.policy_assets.get(batch.policy_name)
                    with torch.no_grad():
                        policy.forward(batch.stitched_td)
                    self.trajectory_isolator.apply_rollout_policy_batch(batch)
                self.trajectory_isolator.finalize_rollout_slices()
                self.trajectory_isolator.writeback_rollout_tds(rollout_td=td)
                # Some rollout postprocessors mutate rewards in-place (e.g. intrinsic shaping).
                # Keep baseline init and EMA updates aligned to the finalized rewards.
                rewards_f32 = td["rewards"].to(dtype=torch.float32)
                if bool(uninitialized.any()):
                    baseline = torch.where(uninitialized, rewards_f32, baseline)
                    td["reward_baseline"] = baseline
                self.experience.store(data_td=td, env_id=training_env_id)

            avg_reward = context.state.avg_reward
            betas = self._reward_centering_beta_by_agent[agent_ids]
            with torch.no_grad():
                avg_reward[agent_ids] = baseline + betas * (rewards_f32 - baseline)
            context.state.avg_reward = avg_reward

            assert "actions" in td, "No loss performed inference - at least one loss must generate actions"
            td_actions: Tensor = td["actions"]
            raw_actions = td_actions.detach()
            if raw_actions.dim() != 1:
                raise ValueError(
                    "Policies must emit a single discrete action id per agent; "
                    f"received tensor of shape {tuple(raw_actions.shape)}"
                )
            raw_vibe_actions: Optional[Tensor] = None
            if "vibe_actions" in td:
                raw_vibe_actions = td["vibe_actions"].detach()
                if raw_vibe_actions.dim() != 1:
                    raise ValueError(
                        "Policies must emit a single vibe action id per agent; "
                        f"received tensor of shape {tuple(raw_vibe_actions.shape)}"
                    )
                if raw_vibe_actions.shape != raw_actions.shape:
                    raise ValueError(
                        "Core and vibe action tensors must share the same shape; "
                        f"got core={tuple(raw_actions.shape)} vibe={tuple(raw_vibe_actions.shape)}"
                    )

            actions_column = raw_actions.view(-1, 1)

            if self.last_action.device != actions_column.device:
                self.last_action = self.last_action.to(device=actions_column.device)

            if self.last_action.dtype != actions_column.dtype:
                actions_column = actions_column.to(dtype=self.last_action.dtype)

            target_buffer = self.last_action[training_env_id]
            if target_buffer.shape != actions_column.shape:
                td_actions2: Tensor = td["actions"]
                msg = "last_action buffer shape mismatch: target=%s actions=%s raw=%s" % (
                    target_buffer.shape,
                    actions_column.shape,
                    tuple(td_actions2.shape),
                )
                logger.error(msg, exc_info=True)
                raise RuntimeError(msg)

            target_buffer.copy_(actions_column)

            # Ship actions to the environment
            with context.stopwatch("_rollout.send"):
                td_actions3: Tensor = td["actions"]
                td_vibe_actions3: Optional[Tensor] = td["vibe_actions"] if "vibe_actions" in td else None
                if td_vibe_actions3 is not None:
                    num_vibe_actions = len(env.policy_env_info.vibe_action_names)
                    if num_vibe_actions <= 0:
                        td_vibe_actions3 = None
                if td_actions3.device.type == "cuda":
                    assert self._action_send_stager is not None
                    cpu_actions, ev = self._action_send_stager.to_numpy_ready_cpu(td_actions3)
                    ev.synchronize()
                    td_actions3 = cpu_actions
                if td_vibe_actions3 is not None and td_vibe_actions3.device.type == "cuda":
                    assert self._action_send_stager is not None
                    cpu_vibe_actions, ev = self._action_send_stager.to_numpy_ready_cpu(td_vibe_actions3)
                    ev.synchronize()
                    td_vibe_actions3 = cpu_vibe_actions
                core_actions_np = td_actions3.cpu().numpy()
                if td_vibe_actions3 is None:
                    env.send_actions(core_actions_np)
                else:
                    env.send_actions(core_actions_np, td_vibe_actions3.cpu().numpy())

            # Rollout env-info used for tensorized cumulants can be per-step; that is too
            # expensive to aggregate into raw_infos. Keep stats reporting focused on
            # episode-end payloads (which always include 'attributes').
            if requested_env_info_keys:
                for row in info_rows:
                    if "attributes" in row:
                        raw_infos.append(row)
            else:
                for row in info_rows:
                    if row:
                        raw_infos.append(row)

            total_steps += num_steps

        context.training_env_id = last_env_id
        assert last_env_id is not None, "No rollout steps completed - last_env_id is None"
        return RolloutResult(raw_infos=raw_infos, agent_steps=total_steps, training_env_id=last_env_id)

    def training_phase(
        self,
        context: ComponentContext,
        update_epochs: int,
        max_grad_norm: float = 0.5,
    ) -> tuple[dict[str, float], int]:
        """Perform training phase on collected experience.

        Args:
            context: Shared trainer context providing training state
            update_epochs: Number of epochs to train for
            max_grad_norm: Maximum gradient norm for clipping

        Returns:
            Dictionary of loss statistics
        """
        primary_policy_slices = self.trajectory_isolator.training_phase_primary_policy_slices
        policy_specs = self.trajectory_isolator.training_phase_policy_specs
        policy_slice_counts = self.trajectory_isolator.training_phase_policy_slice_counts
        distributed_world_size = self.context.distributed.get_world_size()
        distributed_sync_period = max(1, self.accumulate_minibatches * 8)
        cuda_sync_after_optimizer_step = bool(getattr(self.context.config, "cuda_sync_after_optimizer_step", False))

        self.experience.reset_importance_sampling_ratios()

        for loss in self.losses.values():
            loss.zero_loss_tracker()

        epochs_trained = 0

        for _ in range(update_epochs):
            if "values" in self.experience.buffer:
                base_values = self.experience.buffer["values"]
                if base_values.dim() > 2:
                    base_values = base_values.mean(dim=-1)
                advantages_full = torch.zeros_like(base_values, dtype=torch.float32)

                for runtime_slice in self.trajectory_isolator.slice_plan:
                    row_indices = self.trajectory_isolator._slice_row_indices(self.experience, runtime_slice)
                    slice_advantage_cfg = runtime_slice.cfg.advantage

                    values_for_adv = base_values[row_indices]
                    centered_rewards = (
                        self.experience.buffer["rewards"][row_indices]
                        - self.experience.buffer["reward_baseline"][row_indices]
                    )
                    dones = self.experience.buffer["dones"][row_indices]

                    advantages = compute_advantage(
                        values_for_adv,
                        centered_rewards,
                        dones,
                        torch.ones_like(values_for_adv),
                        torch.zeros_like(values_for_adv, device=self.device),
                        slice_advantage_cfg.gamma,
                        slice_advantage_cfg.gae_lambda,
                        self.device,
                        slice_advantage_cfg.vtrace_rho_clip,
                        slice_advantage_cfg.vtrace_c_clip,
                    )
                    advantages_full[row_indices] = advantages
            else:
                # Value-free setups still need a tensor shaped like the buffer for sampling.
                advantages_full = torch.zeros(
                    self.experience.buffer.batch_size,
                    device=self.device,
                    dtype=torch.float32,
                )
            self.experience.buffer["advantages_full"] = advantages_full

            stop_update_epoch = False
            for mb_idx in range(self.experience.num_minibatches):
                if mb_idx % self.accumulate_minibatches == 0:
                    for policy_name in primary_policy_slices:
                        policy = context.policy_assets.get(policy_name)
                        optimizer = getattr(policy, "optimizer", None)
                        if optimizer is not None:
                            optimizer.zero_grad(set_to_none=True)

                stop_update_epoch_mb = False

                for policy_name, slices_with_policy in primary_policy_slices.items():
                    policy = context.policy_assets.get(policy_name)
                    policy_optimizer = getattr(policy, "optimizer", None)
                    if policy_optimizer is None:
                        continue

                    # Sample indices per slice, then clone/gather once per policy and slice via offsets.
                    # This avoids per-slice sampled_mb clones and per-policy cat/split churn.
                    bptt_horizon = int(self.experience.bptt_horizon)
                    slice_samples: list[tuple[Any, int]] = []
                    sampled_idx_chunks: list[torch.Tensor] = []
                    prio_weights_chunks: list[torch.Tensor] = []

                    for runtime_slice in slices_with_policy:
                        count = int(policy_slice_counts[policy_name].get(runtime_slice.name, 0))
                        if count <= 0:
                            continue
                        row_indices = self.trajectory_isolator._slice_row_indices(self.experience, runtime_slice)
                        ordered_indices = self.trajectory_isolator._sorted_slice_row_indices(
                            self.experience, runtime_slice
                        )
                        sampled_idx, prio_weights = self.experience.sample_indices_and_weights(
                            indices=row_indices,
                            ordered_indices=ordered_indices,
                            count=count,
                            mb_idx=mb_idx,
                            advantages=advantages_full,
                            sampling_config=runtime_slice.cfg.sampling,
                            epoch=self.context.epoch,
                            total_timesteps=self.context.config.total_timesteps,
                            batch_size=self.context.config.batch_size,
                        )
                        if sampled_idx.numel() == 0:
                            continue
                        slice_samples.append((runtime_slice, count))
                        sampled_idx_chunks.append(sampled_idx)
                        prio_weights_chunks.append(prio_weights)

                    if not slice_samples:
                        continue

                    if len(sampled_idx_chunks) == 1:
                        policy_sampled_idx = sampled_idx_chunks[0]
                        policy_prio_weights = prio_weights_chunks[0]
                    else:
                        policy_sampled_idx = torch.cat(sampled_idx_chunks, dim=0)
                        policy_prio_weights = torch.cat(prio_weights_chunks, dim=0)

                    # Clone once for the policy to preserve "no views into replay buffer" invariants.
                    policy_sampled_mb = self.experience.buffer[policy_sampled_idx].clone()
                    policy_td = forward_policy_for_training(policy, policy_sampled_mb, policy_specs[policy_name])

                    policy_indices_bt = policy_sampled_idx[:, None].expand(-1, bptt_horizon)
                    policy_advantages = advantages_full[policy_sampled_idx]

                    used_keys: set[str] = set()
                    total_loss = torch.tensor(0.0, dtype=torch.float32, device=self.device)
                    offset = 0
                    for runtime_slice, count in slice_samples:
                        context.current_slice_cfg = runtime_slice.cfg

                        mb_view = policy_sampled_mb[offset : offset + count]
                        td_view = policy_td[offset : offset + count]
                        mb_data = TensorDict({}, batch_size=(count, bptt_horizon), device=self.device)
                        mb_data["sampled_mb"] = mb_view
                        mb_data["policy_td"] = td_view
                        mb_data["indices"] = policy_indices_bt[offset : offset + count]
                        mb_data["advantages"] = policy_advantages[offset : offset + count]
                        mb_data["prio_weights"] = policy_prio_weights[offset : offset + count]
                        if mb_idx == 0:
                            mb_data["advantages_full"] = NonTensorData(advantages_full)

                        ppo_log_prob_keys = tuple(
                            self.losses[loss_key].cfg.log_prob_key
                            for loss_key in runtime_slice.cfg.losses
                            if isinstance(self.losses[loss_key], PPOActor)
                        )
                        for log_prob_keys in (ppo_log_prob_keys, ("act_log_prob",)):
                            combined_logratio = None
                            for log_prob_key in log_prob_keys:
                                if log_prob_key not in mb_view or log_prob_key not in td_view:
                                    continue
                                old_logprob = mb_view[log_prob_key]
                                logratio = td_view[log_prob_key].reshape(old_logprob.shape) - old_logprob
                                combined_logratio = (
                                    logratio if combined_logratio is None else combined_logratio + logratio
                                )
                            if combined_logratio is not None:
                                break
                        if combined_logratio is not None:
                            mb_data["importance_sampling_ratio"] = torch.clamp(combined_logratio, -10, 10).exp()

                        for loss_key in runtime_slice.cfg.losses:
                            loss_obj = self.losses[loss_key]
                            if loss_obj._loss_gate_allows("train", context):
                                used_keys.update(loss_obj.policy_output_keys(td_view))
                            loss_val, mb_data, loss_requests_stop = loss_obj.train(mb_data, context, mb_idx)
                            total_loss = total_loss + loss_val
                            stop_update_epoch_mb = stop_update_epoch_mb or loss_requests_stop

                        context.current_slice_cfg = None
                        offset += count

                    # Synchronize early-stop decision across all ranks so no rank
                    # skips backward() while another calls it (DDP all-reduce deadlock).
                    if distributed_world_size > 1:
                        stop_flag = torch.tensor(int(stop_update_epoch_mb), device=self.device)
                        torch.distributed.all_reduce(stop_flag, op=torch.distributed.ReduceOp.MAX)
                        stop_update_epoch_mb = stop_flag.item() > 0

                    if stop_update_epoch_mb:
                        stop_update_epoch = True
                        break

                    # Ensure all policy outputs participate in the graph even if some heads
                    # aren't used by the active losses (e.g., BC-only runs). This avoids
                    # DDP unused-parameter errors without relying on find_unused_parameters.
                    total_loss = add_dummy_loss_for_unused_params(total_loss, td=policy_td, used_keys=used_keys)

                    total_loss.backward()

                    # Optimizer step with gradient accumulation
                    if (mb_idx + 1) % self.accumulate_minibatches == 0:
                        # Get max_grad_norm from first loss that has it
                        actual_max_grad_norm = max_grad_norm
                        for loss_obj in self.losses.values():
                            if hasattr(loss_obj.cfg, "max_grad_norm"):
                                actual_max_grad_norm = loss_obj.cfg.max_grad_norm
                                break

                        torch.nn.utils.clip_grad_norm_(policy.parameters(), actual_max_grad_norm)
                        policy_optimizer.step()
                        if (
                            cuda_sync_after_optimizer_step
                            and self.device.type == "cuda"
                            and (distributed_world_size == 1 or (mb_idx + 1) % distributed_sync_period == 0)
                        ):
                            torch.cuda.synchronize()

                # Notify losses of minibatch end
                if stop_update_epoch:
                    break

                for loss_obj in self.losses.values():
                    loss_obj.on_mb_end(context, mb_idx)

            epochs_trained += 1
            if stop_update_epoch:
                break

        # Notify losses of training phase end
        for loss_obj in self.losses.values():
            loss_obj.on_train_phase_end(context)

        # Collect statistics from all losses
        losses_stats = {}
        for loss_name, loss_obj in self.losses.items():
            scoped = {f"{loss_name}/{key}": value for key, value in loss_obj.stats().items()}
            losses_stats.update(scoped)

        return losses_stats, epochs_trained

    def on_epoch_start(self, context: ComponentContext | None = None) -> None:
        """Called at the start of each epoch.

        Args:
            context: Shared trainer context providing epoch state
        """
        for loss in self.losses.values():
            loss.on_epoch_start(context)

    def add_last_action_to_td(self, td: TensorDict) -> None:
        agent_slot_ids: Tensor = td["agent_slot_ids"]
        agent_slot_ids = agent_slot_ids.squeeze(-1)

        if self.last_action.device != td.device:
            self.last_action = self.last_action.to(device=td.device)

        td["last_actions"] = self.last_action[agent_slot_ids].detach()
