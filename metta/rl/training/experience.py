from __future__ import annotations

from typing import Any, Dict, Iterable, List

import torch
from tensordict import TensorDict
from torch import Tensor
from torchrl.data import Composite, UnboundedContinuous, UnboundedDiscrete

from metta.common.util.collections import duplicates
from metta.rl.training.batch import calculate_prioritized_sampling_params


class Experience:
    """Segmented tensor storage for RL experience with BPTT support."""

    _REQUIRED_STORE_KEYS = ("reward_baseline", "agent_slot_ids")

    def __init__(
        self,
        total_agents: int,
        batch_size: int,
        bptt_horizon: int,
        minibatch_size: int,
        max_minibatch_size: int,
        experience_spec: Composite,
        device: torch.device | str,
    ):
        """Initialize experience buffer with segmented storage."""
        all_keys = list(experience_spec.keys(include_nested=True, leaves_only=True))
        if duplicate_keys := duplicates(all_keys):
            raise ValueError(f"Duplicate keys found in experience_spec: {[str(d) for d in duplicate_keys]}")

        # Store parameters
        self.total_agents = total_agents
        self.batch_size: int = batch_size
        self.bptt_horizon: int = bptt_horizon
        self.device = device if isinstance(device, torch.device) else torch.device(device)

        # Calculate segments
        self.segments = batch_size // bptt_horizon
        if total_agents > self.segments:
            mini_batch_size = total_agents * bptt_horizon
            raise ValueError(
                f"batch_size ({batch_size}) is too small for {total_agents} agents.\n"
                f"Segments = batch_size // bptt_horizon = {batch_size} // {bptt_horizon} = {self.segments}\n"
                f"But we need segments >= total_agents ({total_agents}).\n"
                f"Please set trainer.batch_size >= {mini_batch_size} in your configuration."
            )

        spec = experience_spec.expand(self.segments, self.bptt_horizon).to(self.device)
        self.buffer = spec.zero()

        # Row-aligned tracking (per-agent row slot id and position within row)
        self.t_in_row = torch.zeros(total_agents, device=self.device, dtype=torch.int64)
        self.t_in_row_cpu = torch.zeros(total_agents, device="cpu", dtype=torch.int64)
        self.row_slot_ids = torch.arange(total_agents, device=self.device, dtype=torch.int64) % self.segments
        self.free_idx = total_agents % self.segments

        # Minibatch configuration
        self.minibatch_size: int = min(minibatch_size, max_minibatch_size)
        self.accumulate_minibatches = max(1, minibatch_size // max_minibatch_size)

        minibatch_segments = self.minibatch_size / bptt_horizon
        self.minibatch_segments: int = int(minibatch_segments)
        if self.minibatch_segments != minibatch_segments:
            raise ValueError(f"minibatch_size {self.minibatch_size} must be divisible by bptt_horizon {bptt_horizon}")

        # Tracking for rollout completion
        self.full_rows = 0

        # Calculate num_minibatches
        num_minibatches = self.segments / self.minibatch_segments
        self.num_minibatches: int = int(num_minibatches)
        if self.num_minibatches != num_minibatches:
            raise ValueError(
                f"Configuration error: segments ({self.segments}) must be divisible by "
                f"minibatch_segments ({self.minibatch_segments}).\n"
                f"segments = batch_size // bptt_horizon = {batch_size} // {bptt_horizon} = {self.segments}\n"
                f"minibatch_segments = minibatch_size // bptt_horizon = "
                f"{self.minibatch_size} // {bptt_horizon} = {self.minibatch_segments}\n"
                f"Please adjust trainer.minibatch_size in your configuration to ensure divisibility."
            )

        self._range_tensor = torch.arange(total_agents, device=self.device, dtype=torch.int64)

        # TODO: restore precomputation of sequential indices

        # Keys to use when writing into the buffer; defaults to all spec keys. Scheduler updates per loss gate activity.
        self._store_keys: List[Any] = list(self.buffer.keys(include_nested=True, leaves_only=True))

    def _check_for_duplicate_keys(self, experience_spec: Composite) -> None:
        """Check for duplicate keys in the experience spec."""
        all_keys = list(experience_spec.keys(include_nested=True, leaves_only=True))
        if duplicate_keys := duplicates(all_keys):
            raise ValueError(f"Duplicate keys found in experience_spec: {[str(d) for d in duplicate_keys]}")

    @property
    def ready_for_training(self) -> bool:
        """Check if buffer has enough data for training."""
        return self.full_rows >= self.segments

    def store(self, data_td: TensorDict, env_id: slice) -> None:
        """Store a batch of experience."""
        assert isinstance(env_id, slice), (
            f"TypeError: env_id expected to be a slice for segmented storage. Got {type(env_id).__name__} instead."
        )
        t_in_row_val = int(self.t_in_row_cpu[env_id.start].item())
        row_ids = self.row_slot_ids[env_id]

        # Scheduler updates these keys based on the active losses for the epoch.
        if self._store_keys:
            self.buffer.update_at_(data_td.select(*self._store_keys), (row_ids, t_in_row_val))
        else:
            raise ValueError("No store keys set. set_store_keys() was likely used incorrectly.")

        self.t_in_row[env_id] += 1
        self.t_in_row_cpu[env_id] += 1

        if t_in_row_val + 1 >= self.bptt_horizon:
            self._reset_completed_episodes(env_id)

    def _reset_completed_episodes(self, env_id) -> None:
        """Reset episode tracking for completed episodes."""
        num_full = env_id.stop - env_id.start
        self.row_slot_ids[env_id] = (self.free_idx + self._range_tensor[:num_full]) % self.segments
        self.t_in_row[env_id] = 0
        self.t_in_row_cpu[env_id] = 0
        self.free_idx = (self.free_idx + num_full) % self.segments
        self.full_rows += num_full

    def reset_for_rollout(self) -> None:
        """Reset tracking variables for a new rollout."""
        self.full_rows = 0
        self.free_idx = self.total_agents % self.segments
        self.row_slot_ids = self._range_tensor % self.segments
        self.t_in_row.zero_()
        self.t_in_row_cpu.zero_()

    def update(self, indices: Tensor, data_td: TensorDict) -> None:
        """Update buffer with new data for given indices."""
        self.buffer[indices].update(data_td)

    def reset_importance_sampling_ratios(self) -> None:
        """Reset the importance sampling ratio to 1.0."""
        if "ratio" in self.buffer.keys():
            self.buffer["ratio"].fill_(1.0)

    def stats(self) -> Dict[str, float]:
        """Get mean values of all tracked buffers."""
        stats = {
            "rewards": self.buffer["rewards"].mean().item(),
            "dones": self.buffer["dones"].mean().item(),
            "truncateds": self.buffer["truncateds"].mean().item(),
        }
        # Only include values if they exist (not all losses use value networks)
        if "values" in self.buffer.keys():
            stats["values"] = self.buffer["values"].mean().item()
        if "ratio" in self.buffer.keys():
            stats["ratio"] = self.buffer["ratio"].mean().item()
        if "act_log_prob" in self.buffer.keys():
            stats["act_log_prob"] = self.buffer["act_log_prob"].mean().item()

        # Add episode length stats for active episodes
        active_episodes = self.t_in_row > 0
        if active_episodes.any():
            stats["t_in_row"] = self.t_in_row[active_episodes].float().mean().item()
        else:
            stats["t_in_row"] = 0.0

        # Add action statistics based on action space type
        if "actions" in self.buffer.keys():
            actions = self.buffer["actions"]
            if actions.dtype in [torch.int32, torch.int64]:
                # For discrete actions, we can add distribution info
                stats["actions_mean"] = actions.float().mean().item()
                stats["actions_std"] = actions.float().std().item()

        return stats

    # ----------------- Dynamic store key management -----------------
    @property
    def store_keys(self) -> List[Any]:
        """Return the list of keys that will be written on the next store call."""
        return list(self._store_keys)

    def set_store_keys(self, keys: Iterable[Any]) -> None:
        """Restrict which keys are written when storing experience. Otherwise, the buffer will throw an error if it
        looks for keys that are not in the tensor dict when calling store().
        """
        all_keys = set(self.buffer.keys(include_nested=True, leaves_only=True))
        missing = [k for k in keys if k not in all_keys]
        if missing:
            raise KeyError(f"Attempted to set unknown experience keys: {missing}")
        required = self.required_store_keys()
        missing_required = [k for k in required if k not in keys]
        if missing_required:
            raise ValueError(f"Attempted to drop required experience keys: {missing_required}")
        self._store_keys = list(keys)

    def required_store_keys(self) -> List[Any]:
        """Keys that should always be written into the experience buffer when present."""
        all_keys = set(self.buffer.keys(include_nested=True, leaves_only=True))
        return [key for key in self._REQUIRED_STORE_KEYS if key in all_keys]

    def reset_store_keys(self) -> None:
        """Reset store keys so that all spec keys are written on store."""
        self._store_keys = list(self.buffer.keys(include_nested=True, leaves_only=True))

    def sample_from_indices(
        self,
        *,
        indices: Tensor,
        ordered_indices: Tensor | None = None,
        count: int,
        mb_idx: int,
        advantages: Tensor,
        sampling_config: Any,
        epoch: int,
        total_timesteps: int,
        batch_size: int,
    ) -> TensorDict:
        bptt_horizon = self.bptt_horizon
        device = self.device

        if count <= 0 or indices.numel() == 0:
            empty_idx = torch.empty((0,), device=device, dtype=torch.long)
            shared_loss_mb_data = TensorDict({}, batch_size=(0, bptt_horizon), device=device)
            shared_loss_mb_data["sampled_mb"] = self.buffer[empty_idx].clone()
            shared_loss_mb_data["indices"] = empty_idx[:, None].expand(-1, bptt_horizon)
            shared_loss_mb_data["advantages"] = torch.empty((0, bptt_horizon), device=device, dtype=advantages.dtype)
            shared_loss_mb_data["prio_weights"] = torch.empty((0, bptt_horizon), device=device, dtype=torch.float32)
            return shared_loss_mb_data

        indices = indices.to(device=device, dtype=torch.long)
        total = indices.numel()

        if sampling_config.method == "prioritized":
            prio_alpha = sampling_config.prio_alpha
            if prio_alpha <= 0.0:
                sampled_idx = self._sample_sequential_indices(indices, count, mb_idx)
                prio_weights = torch.ones((count, bptt_horizon), device=device, dtype=torch.float32)
            else:
                adv_subset = advantages[indices]
                adv_magnitude = adv_subset.abs().sum(dim=1)
                prio_vals = torch.nan_to_num(adv_magnitude**prio_alpha, 0, 0, 0)
                prio_probs = (prio_vals + 1e-6) / (prio_vals.sum() + 1e-6)
                beta = calculate_prioritized_sampling_params(
                    epoch=epoch,
                    total_timesteps=total_timesteps,
                    batch_size=batch_size,
                    prio_alpha=prio_alpha,
                    prio_beta0=sampling_config.prio_beta0,
                )
                all_is_weights = (total * prio_probs) ** -beta
                replace = count > total
                picked = torch.multinomial(prio_probs, count, replacement=replace)
                sampled_idx = indices[picked]
                prio_weights = all_is_weights[picked].reshape(-1, 1).expand(-1, bptt_horizon)
        else:
            sampled_idx = self._sample_sequential_indices(indices, count, mb_idx, ordered_indices)
            prio_weights = torch.ones((count, bptt_horizon), device=device, dtype=torch.float32)

        minibatch = self.buffer[sampled_idx].clone()
        shared_loss_mb_data = TensorDict({}, batch_size=minibatch.batch_size, device=device)
        shared_loss_mb_data["prio_weights"] = prio_weights
        shared_loss_mb_data["sampled_mb"] = minibatch
        shared_loss_mb_data["indices"] = sampled_idx[:, None].expand(-1, bptt_horizon)
        shared_loss_mb_data["advantages"] = advantages[sampled_idx]
        return shared_loss_mb_data

    def _sample_sequential_indices(
        self, indices: Tensor, count: int, mb_idx: int, ordered_indices: Tensor | None = None
    ) -> Tensor:
        if count <= 0 or indices.numel() == 0:
            return torch.empty((0,), device=indices.device, dtype=torch.long)

        order = ordered_indices if ordered_indices is not None else torch.sort(indices).values
        total = order.numel()
        start = (mb_idx * count) % total
        offset = torch.arange(count, device=order.device, dtype=torch.long)
        pick = (start + offset) % total
        return order[pick]

    @staticmethod
    def from_losses(
        total_agents: int,
        batch_size: int,
        bptt_horizon: int,
        minibatch_size: int,
        max_minibatch_size: int,
        policy_experience_spec: Composite,
        losses: Dict[str, Any],
        device: torch.device | str,
    ) -> "Experience":
        """Create experience buffer with merged specs from policy and losses."""

        # Merge all specs
        merged_spec_dict: dict = dict(policy_experience_spec.items())
        for loss in losses.values():
            spec = loss.get_experience_spec()
            merged_spec_dict.update(dict(spec.items()))

        merged_spec_dict.setdefault(
            "reward_baseline",
            UnboundedContinuous(shape=torch.Size([]), dtype=torch.float32),
        )
        merged_spec_dict.setdefault(
            "agent_slot_ids",
            UnboundedDiscrete(shape=torch.Size([1]), dtype=torch.int64),
        )

        # Create experience buffer
        experience = Experience(
            total_agents=total_agents,
            batch_size=batch_size,
            bptt_horizon=bptt_horizon,
            minibatch_size=minibatch_size,
            max_minibatch_size=max_minibatch_size,
            experience_spec=Composite(merged_spec_dict),
            device=device,
        )
        for loss in losses.values():
            loss.attach_replay_buffer(experience)
        return experience
