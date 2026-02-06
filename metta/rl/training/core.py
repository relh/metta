import logging
from typing import Any

import torch
from cortex.consistent_dropout import reset_consistent_dropout
from pydantic import ConfigDict
from tensordict import NonTensorData, TensorDict
from torch import Tensor

from metta.rl.advantage import compute_advantage
from metta.rl.loss.loss import Loss
from metta.rl.training import ComponentContext, Experience, TrainingEnvironment
from metta.rl.training.trajectory_isolation import TrajectoryIsolator
from metta.rl.utils import add_dummy_loss_for_unused_params, ensure_sequence_metadata, forward_policy_for_training
from mettagrid.base_config import Config

logger = logging.getLogger(__name__)


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
    ):
        """Initialize core training loop.

        Args:
            experience: Experience buffer for storing rollouts
            losses: Dictionary of loss instances to use
            device: Device to run on
        """
        self.experience = experience
        self.losses = losses
        self.device = device
        self.accumulate_minibatches = experience.accumulate_minibatches
        self.context = context
        self.last_action = torch.zeros(
            experience.total_agents,
            1,
            dtype=torch.int32,
            device=device,
        )
        # Cache environment indices to avoid reallocating per rollout batch
        self._env_index_cache = experience._range_tensor.to(device=device)
        self.trajectory_isolator = trajectory_isolator

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

    def _reward_centering_betas(self, *, agent_ids: torch.Tensor) -> torch.Tensor:
        runtime_slices = self.trajectory_isolator.slice_plan
        betas = torch.empty(agent_ids.shape, device=agent_ids.device, dtype=torch.float32)
        assigned = torch.zeros(agent_ids.shape, device=agent_ids.device, dtype=torch.bool)
        for runtime_slice in runtime_slices:
            slice_mask = runtime_slice.env_mask[agent_ids]
            if not bool(slice_mask.any()):
                continue
            betas[slice_mask] = float(runtime_slice.cfg.advantage.reward_centering.beta)
            assigned |= slice_mask

        assert bool(assigned.all()), "Reward-centering beta not assigned for all agents."

        return betas

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
        reset_consistent_dropout(self.policy)

        # Notify losses of rollout start
        for loss in self.losses.values():
            loss.on_rollout_start(context)
        self.trajectory_isolator.on_rollout_start()

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
            # Prepare data for policy
            with context.stopwatch("_rollout.td_prep"):
                td = buffer_step[training_env_id].clone()
                target_device = td.device
                assert target_device is not None
                td["env_obs"] = o.to(device=target_device, non_blocking=True)

                rewards = r.to(device=target_device, non_blocking=True)
                td["rewards"] = rewards
                agent_ids = self._env_index_cache[training_env_id]
                td["training_env_ids"] = agent_ids.unsqueeze(1)

                avg_reward = context.state.avg_reward
                baseline = avg_reward[agent_ids]
                td["reward_baseline"] = baseline

                # CRITICAL FIX for MPS: Convert dtype BEFORE moving to device, and use blocking transfer
                # MPS has two bugs:
                # 1. bool->float32 conversion during .to(device=mps, dtype=float32) produces NaN
                # 2. non_blocking=True causes race conditions with uninitialized data
                # Solution: Convert dtype on CPU first, then use blocking transfer to MPS
                if target_device.type == "mps":
                    td["dones"] = d.to(dtype=torch.float32).to(device=target_device, non_blocking=False)
                    td["truncateds"] = t.to(dtype=torch.float32).to(device=target_device, non_blocking=False)
                else:
                    # On CUDA/CPU, combined conversion is safe and faster
                    td["dones"] = d.to(device=target_device, dtype=torch.float32, non_blocking=True)
                    td["truncateds"] = t.to(device=target_device, dtype=torch.float32, non_blocking=True)
                td["teacher_actions"] = ta.to(device=target_device, dtype=torch.long, non_blocking=True)
                # Row-aligned state: provide row slot id and position within row
                row_ids = self.experience.row_slot_ids[training_env_id]
                t_in_row = self.experience.t_in_row[training_env_id]
                td["row_id"] = row_ids
                td["t_in_row"] = t_in_row
                self.add_last_action_to_td(td)

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
                self.experience.store(data_td=td, env_id=training_env_id)

            avg_reward = context.state.avg_reward
            betas = self._reward_centering_betas(agent_ids=agent_ids)
            with torch.no_grad():
                rewards_f32 = td["rewards"].to(dtype=torch.float32)
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
                env.send_actions(td_actions3.cpu().numpy())

            infos_list: list[dict[str, Any]] = list(info) if info else []
            if infos_list:
                raw_infos.extend(infos_list)

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

        self.experience.reset_importance_sampling_ratios()

        for loss in self.losses.values():
            loss.zero_loss_tracker()

        epochs_trained = 0

        for _ in range(update_epochs):
            if "values" in self.experience.buffer.keys():
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
            else:  # av is this redundant with the advantages_full zeros above?
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

                    slice_mb_data: list[tuple[Any, TensorDict]] = []
                    for runtime_slice in slices_with_policy:
                        count = policy_slice_counts[policy_name].get(runtime_slice.name, 0)
                        mb_data = self.trajectory_isolator.sample_slice_minibatch(
                            experience=self.experience,
                            runtime_slice=runtime_slice,
                            count=count,
                            mb_idx=mb_idx,
                            advantages=advantages_full,
                        )
                        if mb_idx == 0:
                            mb_data["advantages_full"] = NonTensorData(advantages_full)
                        slice_mb_data.append((runtime_slice, mb_data))

                    tds_for_policy = [mb["sampled_mb"] for _slice, mb in slice_mb_data]
                    total_segments = sum(int(td.batch_size[0]) for td in tds_for_policy)
                    if total_segments == 0:
                        continue

                    stitched_td = torch.cat(tds_for_policy, dim=0)
                    policy_td = forward_policy_for_training(policy, stitched_td, policy_specs[policy_name])

                    split_sizes = [int(td.batch_size[0]) for td in tds_for_policy]
                    split_policy_tds = policy_td.split(split_sizes, dim=0)

                    used_keys: set[str] = set()
                    total_loss = torch.tensor(0.0, dtype=torch.float32, device=self.device)
                    for (runtime_slice, mb_data), policy_split_td in zip(slice_mb_data, split_policy_tds, strict=True):
                        context.current_slice_cfg = runtime_slice.cfg
                        mb_data["policy_td"] = policy_split_td
                        sampled_mb = mb_data["sampled_mb"]
                        if "act_log_prob" in sampled_mb.keys() and "act_log_prob" in policy_split_td.keys():
                            old_logprob = sampled_mb["act_log_prob"]
                            new_logprob = policy_split_td["act_log_prob"].reshape(old_logprob.shape)
                            logratio = torch.clamp(new_logprob - old_logprob, -10, 10)
                            mb_data["importance_sampling_ratio"] = logratio.exp()

                        for loss_key in runtime_slice.cfg.losses:
                            loss_obj = self.losses[loss_key]
                            if loss_obj._loss_gate_allows("train", context):
                                used_keys.update(loss_obj.policy_output_keys(policy_split_td))
                            loss_val, mb_data, loss_requests_stop = loss_obj.train(mb_data, context, mb_idx)
                            total_loss = total_loss + loss_val
                            stop_update_epoch_mb = stop_update_epoch_mb or loss_requests_stop
                        context.current_slice_cfg = None

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

                        if self.device.type == "cuda":
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
        env_ids: Tensor = td["training_env_ids"]
        env_ids = env_ids.squeeze(-1)

        if self.last_action.device != td.device:
            self.last_action = self.last_action.to(device=td.device)

        td["last_actions"] = self.last_action[env_ids].detach()
