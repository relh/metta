"""Replay experience buffer for RL training with strict row ownership.

.. note:: **For coding agents (LLMs) — read this first.**

   This module is a common source of confusion when AI coding
   assistants modify the training loop. The invariants here are subtle and
   violating them produces bugs that are silent or delayed (off-policy drift,
   mixed agent_slot_ids, corrupt recurrent state). Read the architecture notes
   below before making ANY change to this file.

Architecture Overview
=====================

The replay buffer (``Experience``) sits at the center of a chain of
components during rollout. Understanding how they interact is essential.

Rollout data flow (per iteration of the rollout loop in ``core.py``)::

    ┌─────────────────────────────────────────────────────────────────┐
    │  1. env.get_observations()                                      │
    │     PufferLib vecenv.recv() returns ONE ready group of agents    │
    │     as a contiguous slice (training_env_id).                    │
    │                                                                 │
    │  2. Build TensorDict (td)                                       │
    │     Observations, rewards, dones, agent_slot_ids, row_id,       │
    │     t_in_row are assembled. row_id and t_in_row come from       │
    │     this Experience buffer.                                     │
    │                                                                 │
    │  3. Policy forward (trajectory isolator → Cortex)               │
    │     Cortex advances recurrent state for these agents.           │
    │     This is irreversible — state is mutated in place.           │
    │                                                                 │
    │  4. experience.store(td, training_env_id)                       │
    │     Writes the transition into the replay buffer row for each   │
    │     agent in the slice.                                         │
    │                                                                 │
    │  5. env.send_actions()                                          │
    │     Ships computed actions back to PufferLib, which advances    │
    │     the underlying C++ environments.                            │
    └─────────────────────────────────────────────────────────────────┘

Steps 1–5 repeat until ``experience.ready_for_training`` is True
(all agent rows are full).

Critical invariant: ghost progression
======================================

**Ghost progression** occurs when steps 1–3 and 5 execute for agents whose
replay rows are already full (``_done[agent] == True``). When this happens:

- The environment advances (step 5) — transitions are generated but have
  nowhere to go in the replay buffer.
- Cortex recurrent state advances (step 3) — the hidden state drifts from
  what is recorded in replay. During training, Cortex loads its initial
  row state from a cache captured at ``t_in_row == 0``. If rollout state
  advanced beyond what replay records, the training-time sequence and the
  rollout-time sequence diverge (off-policy recurrent drift).
- The transition data is lost — the buffer cannot accept it.

The current code raises ``RuntimeError`` when done agents reach store(),
making ghost progression visible. The real fix is **backpressure** in the
rollout loop: defer recv/forward/send for agent groups whose rows are
full, so done agents never reach store() in the first place.

Why rows must NEVER wrap or get reassigned
==========================================

Each agent slot owns exactly one row for the entire rollout
(``segments == total_agents``). Earlier designs used ring-buffer modulo
logic to reassign rows. Under async rollout (``async_factor > 1``), one
env group can complete its rows faster than another. With ring-buffer
reassignment, the fast group's new row can overwrite a slow group's
in-progress row, producing sequences where ``agent_slot_ids`` change
across timesteps within a single BPTT window. Cortex enforces::

    ValueError("agent_slot_ids must stay constant across timesteps
                within each sequence")

Strict row ownership eliminates this class of bug entirely.

PufferLib double buffering and async groups
============================================

PufferLib's vectorized environment uses **double buffering** when
``async_factor >= 2`` (the default). Two groups of environments run in
parallel: while one group is being stepped (C++ simulation), the other
group's observations are being processed by the policy.

On **CUDA**, data transfers between CPU and GPU use ``non_blocking=True``,
so the GPU can overlap computation with the next H2D transfer. On **MPS**
(Apple Silicon), ``non_blocking=True`` causes race conditions and
bool→float32 NaN bugs, so transfers are blocking (see ``core.py``
lines 153-164 for the MPS workaround).

The double buffering means ``recv()`` can return either group on each
call. Under pressure (one group faster than the other), the faster group
may be returned repeatedly while the slower group is still simulating.
This is the source of asymmetric row-fill rates and the need for
backpressure.

Cortex recurrent state (two pathways)
======================================

Cortex maintains **two** state stores:

1. **Rollout state** (``_rollout_store_leaves`` / ``_rollout_current_state``):
   Updated every ``forward()`` call during rollout (TT=1). This is the
   live recurrent memory of the agent.

2. **Row-start state** (``_row_store_leaves``): Snapshot of rollout state
   captured when ``t_in_row == 0`` for each row. During training (TT>1),
   this is loaded as the initial hidden state for each BPTT sequence.

If an agent is ghost-progressed (stepped without recording in replay),
its rollout state advances past what row-start state was captured for,
creating a mismatch between the state the policy "remembers" and the
state training optimizes from.

What NOT to do (common AI-agent mistakes)
==========================================

1. **Do NOT add silent filtering** of done agents in ``store()``.
   The old ``active_mask = ~done_mask; data_td = data_td[active_mask]``
   pattern hides ghost progression. The RuntimeError is intentional.

2. **Do NOT add row wrapping / modulo reassignment.** This was the
   original corruption source. One row per agent per rollout, period.

3. **Do NOT add try/except around store().** If store raises, the
   rollout loop has a bug. Catching the error hides it.

4. **Do NOT "fix" the RuntimeError by making store() accept done agents.**
   The fix belongs upstream in the rollout loop (backpressure gate).

5. **Do NOT assume all agents in a recv() group are at the same
   t_in_row.** Async batching means agents within a contiguous slice
   can be at different offsets. This is fine as long as none are done.

See also
========

- ``metta/rl/training/core.py`` — rollout loop (where backpressure
  should be implemented)
- ``metta/rl/training/training_environment.py`` — PufferLib wrapper,
  async_factor, double buffering
- ``agent/src/metta/agent/components/cortex.py`` — recurrent state
  management, row-start caching
- ``tests/test_experience_async_store.py`` — tests for these invariants
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List

import torch
from tensordict import TensorDict
from torch import Tensor
from torchrl.data import Composite, UnboundedContinuous, UnboundedDiscrete

from metta.common.util.collections import duplicates
from metta.rl.training.batch import calculate_prioritized_sampling_params


class Experience:
    """Segmented tensor storage for RL experience with strict row ownership.

    Each agent slot owns exactly one replay row for the duration of a rollout.
    Rows are never reassigned or wrapped. See module docstring for full
    architecture context and invariant documentation.
    """

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
        if total_agents != self.segments:
            expected_batch_size = total_agents * bptt_horizon
            raise ValueError(
                "This trainer requires a 1:1 mapping between agent slots and replay rows.\n"
                f"Got segments={self.segments} (batch_size // bptt_horizon = {batch_size} // {bptt_horizon}) "
                f"but total_agents={total_agents}.\n"
                f"Please set trainer.batch_size = total_agents * bptt_horizon = {expected_batch_size}."
            )

        spec = experience_spec.expand(self.segments, self.bptt_horizon).to(self.device)
        self.buffer = spec.zero()

        # Row-aligned tracking (per-agent position within its row). With segments == total_agents,
        # each agent owns exactly one row for the entire rollout.
        self.t_in_row = torch.zeros(total_agents, device=self.device, dtype=torch.int64)
        self._done = torch.zeros(total_agents, device=self.device, dtype=torch.bool)

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
        self.row_slot_ids = self._range_tensor

        # TODO: restore precomputation of sequential indices

        # Keys to use when writing into the buffer; defaults to all spec keys. Scheduler updates per loss gate activity.
        self._store_keys: List[Any] = list(self.buffer.keys(include_nested=True, leaves_only=True))
        self._store_buffer = self.buffer.select(*self._store_keys)

    @property
    def ready_for_training(self) -> bool:
        """Check if buffer has enough data for training."""
        return self.full_rows >= self.segments

    def store(self, data_td: TensorDict, env_id: slice, *, prefiltered: bool = False) -> None:
        """Store a batch of experience.

        Raises if called for agents whose segments are already full. This catches
        "ghost progression" — the environment and policy state advancing while
        experience is silently dropped.
        """
        assert isinstance(env_id, slice), (
            f"TypeError: env_id expected to be a slice for segmented storage. Got {type(env_id).__name__} instead."
        )
        env_ids = self._range_tensor[env_id]
        done_mask = self._done[env_id]
        if bool(done_mask.any()):
            done_ids = env_ids[done_mask].tolist()
            raise RuntimeError(
                f"Ghost progression detected: store() called for agents whose replay segments are already full.\n"
                f"  env_id slice: {env_id}\n"
                f"  done agent ids: {done_ids}\n"
                f"  full_rows: {self.full_rows} / {self.segments}\n"
                f"  t_in_row (done agents): {self.t_in_row[env_ids[done_mask]].tolist()}\n"
                f"  ready_for_training: {self.ready_for_training}\n"
                f"The rollout loop is stepping environments and advancing policy state for agents\n"
                f"that have already filled their replay rows. This means env transitions and\n"
                f"recurrent state updates are happening with no record in the experience buffer.\n"
                f"The rollout loop must implement backpressure to defer these agents."
            )

        # Scheduler updates these keys based on the active losses for the epoch.
        if self._store_keys:
            row_ids = self.row_slot_ids[env_ids]
            t_in_row = self.t_in_row[env_ids]
            if prefiltered:
                # Fast path used by rollout: td is already projected to store keys.
                td_keys = set(data_td.keys(include_nested=True, leaves_only=True))
                missing = [key for key in self._store_keys if key not in td_keys]
                if missing:
                    raise KeyError(f"Prefiltered store td is missing required keys: {missing}")
                self._store_buffer.update_at_(data_td, (row_ids, t_in_row))
            else:
                self._store_buffer.update_at_(data_td.select(*self._store_keys), (row_ids, t_in_row))
        else:
            raise ValueError("No store keys set. set_store_keys() was likely used incorrectly.")

        self.t_in_row[env_ids] += 1

        completed = (t_in_row + 1) >= self.bptt_horizon
        if not bool(completed.any()):
            return

        completed_env_ids = env_ids[completed]
        self.full_rows += int(completed_env_ids.numel())

        self.t_in_row[completed_env_ids] = 0
        self._done[completed_env_ids] = True

    def reset_for_rollout(self) -> None:
        """Reset tracking variables for a new rollout."""
        self.full_rows = 0
        self.t_in_row.zero_()
        self._done.zero_()

    def update(self, indices: Tensor, data_td: TensorDict) -> None:
        """Update buffer with new data for given indices."""
        self.buffer[indices].update(data_td)

    def reset_importance_sampling_ratios(self) -> None:
        """Reset the importance sampling ratio to 1.0."""
        if "ratio" in self.buffer:
            self.buffer["ratio"].fill_(1.0)

    def stats(self) -> Dict[str, float]:
        """Get mean values of all tracked buffers."""
        stats = {
            "rewards": self.buffer["rewards"].mean().item(),
            "dones": self.buffer["dones"].mean().item(),
            "truncateds": self.buffer["truncateds"].mean().item(),
        }
        # Only include values if they exist (not all losses use value networks)
        if "values" in self.buffer:
            stats["values"] = self.buffer["values"].mean().item()
        if "ratio" in self.buffer:
            stats["ratio"] = self.buffer["ratio"].mean().item()
        if "act_log_prob" in self.buffer:
            stats["act_log_prob"] = self.buffer["act_log_prob"].mean().item()

        # Add episode length stats for active episodes
        active_episodes = self.t_in_row > 0
        if active_episodes.any():
            stats["t_in_row"] = self.t_in_row[active_episodes].float().mean().item()
        else:
            stats["t_in_row"] = 0.0

        # Add action statistics based on action space type
        if "actions" in self.buffer:
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
        self._store_buffer = self.buffer.select(*self._store_keys)

    def required_store_keys(self) -> List[Any]:
        """Keys that should always be written into the experience buffer when present."""
        all_keys = set(self.buffer.keys(include_nested=True, leaves_only=True))
        return [key for key in self._REQUIRED_STORE_KEYS if key in all_keys]

    def reset_store_keys(self) -> None:
        """Reset store keys so that all spec keys are written on store."""
        self._store_keys = list(self.buffer.keys(include_nested=True, leaves_only=True))
        self._store_buffer = self.buffer.select(*self._store_keys)

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
        device = self.device
        sampled_idx, prio_weights = self.sample_indices_and_weights(
            indices=indices,
            ordered_indices=ordered_indices,
            count=count,
            mb_idx=mb_idx,
            advantages=advantages,
            sampling_config=sampling_config,
            epoch=epoch,
            total_timesteps=total_timesteps,
            batch_size=batch_size,
        )

        bptt_horizon = self.bptt_horizon
        if sampled_idx.numel() == 0:
            shared_loss_mb_data = TensorDict({}, batch_size=(0, bptt_horizon), device=device)
            shared_loss_mb_data["sampled_mb"] = self.buffer[sampled_idx].clone()
            shared_loss_mb_data["indices"] = sampled_idx[:, None].expand(-1, bptt_horizon)
            shared_loss_mb_data["advantages"] = torch.empty((0, bptt_horizon), device=device, dtype=advantages.dtype)
            shared_loss_mb_data["prio_weights"] = prio_weights
            return shared_loss_mb_data

        minibatch = self.buffer[sampled_idx].clone()
        shared_loss_mb_data = TensorDict({}, batch_size=minibatch.batch_size, device=device)
        shared_loss_mb_data["prio_weights"] = prio_weights
        shared_loss_mb_data["sampled_mb"] = minibatch
        shared_loss_mb_data["indices"] = sampled_idx[:, None].expand(-1, bptt_horizon)
        shared_loss_mb_data["advantages"] = advantages[sampled_idx]
        return shared_loss_mb_data

    def sample_indices_and_weights(
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
    ) -> tuple[Tensor, Tensor]:
        """Sample row indices (and importance sampling weights) without cloning the replay buffer.

        The trainer uses this to assemble one minibatch per policy (clone/gather once) and then slice by offsets,
        avoiding per-slice minibatch cloning and per-policy cat/split churn.
        """
        bptt_horizon = self.bptt_horizon
        device = self.device

        if count <= 0 or indices.numel() == 0:
            empty_idx = torch.empty((0,), device=device, dtype=torch.long)
            prio_weights = torch.empty((0, bptt_horizon), device=device, dtype=torch.float32)
            return empty_idx, prio_weights

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

        return sampled_idx, prio_weights

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
