"""Tests for Experience replay buffer async store invariants.

.. note:: **For coding agents (LLMs) — read this before modifying.**

   These tests encode hard invariants for the replay buffer. They exist
   because AI coding agents frequently misunderstand the replay buffer's
   contract and introduce bugs by:

   - Adding silent filtering of done agents in ``store()``
   - Adding row wrapping / ring-buffer reassignment
   - Catching RuntimeError from ``store()`` instead of fixing the caller
   - Assuming all agents in a ``recv()`` group share the same ``t_in_row``

   If a test here fails after your change, the change is almost certainly
   wrong. Do NOT weaken the test to make it pass. See the module docstring
   in ``metta/rl/training/experience.py`` for the full architecture context.

Background: the rollout chain
==============================

During rollout, ``core.py`` runs a tight loop:

1. ``env.get_observations()`` — PufferLib ``recv()`` returns ONE ready
   group of agents as a contiguous slice. With ``async_factor >= 2``
   (default), two groups alternate via double buffering. On CUDA, data
   transfers use ``non_blocking=True`` for overlap; on MPS, transfers
   are blocking to avoid race conditions and NaN bugs.

2. **Policy forward** — Cortex advances recurrent state for every agent
   in the slice. This is irreversible; hidden state is mutated in place.

3. ``experience.store(td, env_id)`` — writes the transition into each
   agent's replay row at its current ``t_in_row`` offset.

4. ``env.send_actions()`` — ships actions to PufferLib, advancing the
   underlying C++ environments.

Steps 1–4 repeat until ``experience.ready_for_training`` (all rows full).

Ghost progression
-----------------

If a group's rows are all full but the rollout loop keeps stepping that
group (because ``recv()`` returned it), steps 1–2 and 4 execute with
nowhere to record the transition. This is **ghost progression**:

- Environment state advances with no record in replay.
- Cortex recurrent state drifts from what was captured at row-start
  (``t_in_row == 0``), creating off-policy recurrent drift during
  training.
- The transition data is discarded.

``store()`` raises ``RuntimeError`` when it detects done agents in the
batch. The correct fix is **backpressure** in the rollout loop — defer
``recv()``/forward/send for groups whose rows are full — NOT silent
filtering or try/except in the buffer.

Row ownership
-------------

Each agent slot owns exactly one row (``segments == total_agents``).
Rows are NEVER reassigned or wrapped within a rollout. An earlier
ring-buffer design caused corruption where ``agent_slot_ids`` changed
across timesteps within a BPTT window, triggering Cortex's::

    ValueError("agent_slot_ids must stay constant across timesteps ...")

Strict ownership eliminates that class of bug.

Mixed ``t_in_row`` offsets (async batches)
-------------------------------------------

Agents within the same ``recv()`` slice CAN be at different ``t_in_row``
offsets — this is normal under async double buffering. What matters is
that no agent in the slice has ``_done == True``. Mixed offsets are fine;
mixed done/active is ghost progression.
"""

import pytest
import torch
from tensordict import TensorDict
from torchrl.data import Composite, UnboundedContinuous, UnboundedDiscrete

from metta.rl.training.experience import Experience

_SPEC = Composite(
    {
        "reward_baseline": UnboundedContinuous(shape=torch.Size([]), dtype=torch.float32),
        "agent_slot_ids": UnboundedDiscrete(shape=torch.Size([1]), dtype=torch.int64),
        "rewards": UnboundedContinuous(shape=torch.Size([]), dtype=torch.float32),
    }
)


def _make_experience(total_agents: int, bptt_horizon: int) -> Experience:
    batch_size = total_agents * bptt_horizon
    return Experience(
        total_agents=total_agents,
        batch_size=batch_size,
        bptt_horizon=bptt_horizon,
        minibatch_size=batch_size,
        max_minibatch_size=batch_size,
        experience_spec=_SPEC,
        device="cpu",
    )


def _make_step_td(start: int, stop: int) -> TensorDict:
    n = stop - start
    agent_ids = torch.arange(start, stop, dtype=torch.int64)
    return TensorDict(
        {
            "reward_baseline": torch.zeros(n, dtype=torch.float32),
            "agent_slot_ids": agent_ids.view(n, 1),
            "rewards": torch.ones(n, dtype=torch.float32),
        },
        batch_size=[n],
    )


class TestGhostProgressionDetection:
    """store() must raise RuntimeError when ANY agent in the batch has _done == True.

    This is the ghost-progression invariant. If done agents reach store(), the
    rollout loop failed to apply backpressure — it stepped environments and
    advanced policy/recurrent state for agents that have no room in replay.

    The fix belongs in core.py (defer the group before policy forward), NOT in
    store() (do NOT add silent filtering or try/except).
    """

    def test_all_agents_done(self) -> None:
        """All rows full → any subsequent store must raise."""
        exp = _make_experience(total_agents=4, bptt_horizon=2)
        exp.reset_for_rollout()

        # Fill all rows: 4 agents × 2 timesteps.
        exp.store(_make_step_td(0, 4), slice(0, 4))  # t_in_row 0→1
        exp.store(_make_step_td(0, 4), slice(0, 4))  # t_in_row 1→2, all done

        assert exp.ready_for_training

        # Ghost progression: rollout loop kept stepping after all rows filled.
        with pytest.raises(RuntimeError, match="Ghost progression detected"):
            exp.store(_make_step_td(0, 4), slice(0, 4))

    def test_mixed_done_and_active_agents(self) -> None:
        """A slice containing even one done agent is ghost progression.

        This is the scenario that confuses AI agents most: the old code silently
        filtered to active-only, hiding the fact that Cortex recurrent state and
        env state already advanced for the done agents in steps 1-2 of the
        rollout loop (before store() was even called).
        """
        exp = _make_experience(total_agents=4, bptt_horizon=2)
        exp.reset_for_rollout()

        # Only agents 0-1 complete their rows.
        exp.store(_make_step_td(0, 2), slice(0, 2))  # agents 0-1: t=0→1
        exp.store(_make_step_td(0, 2), slice(0, 2))  # agents 0-1: t=1→2, done

        assert exp.full_rows == 2

        # A wider slice(0,4) includes done agents 0-1 alongside active 2-3.
        # This means the rollout loop stepped agents 0-1 (env + Cortex forward)
        # even though their rows are full. The data for 2-3 is legitimate, but
        # the damage to 0-1's recurrent state is already done by the time we
        # reach store(). Must raise.
        with pytest.raises(RuntimeError, match="Ghost progression detected"):
            exp.store(_make_step_td(0, 4), slice(0, 4))


class TestBackpressureRolloutPattern:
    """Correct async rollout: caller restricts store() to active agents only.

    These tests simulate what the rollout loop should do once backpressure is
    implemented: when recv() returns a group containing agents whose rows are
    full, defer those agents (skip policy forward and action send) and only
    store for the active ones via separate slices.
    """

    def test_two_groups_sequential_completion(self) -> None:
        """Group A finishes first, then only group B is stepped.

        This models async_factor=2 double buffering where group A (agents 0-1)
        cycles faster than group B (agents 2-3). Once A is done, backpressure
        ensures only B is stepped until it also finishes.
        """
        exp = _make_experience(total_agents=4, bptt_horizon=2)
        exp.reset_for_rollout()

        # Group A completes.
        exp.store(_make_step_td(0, 2), slice(0, 2))  # A: t=0→1
        exp.store(_make_step_td(0, 2), slice(0, 2))  # A: t=1→2, done

        assert exp.full_rows == 2
        assert not exp.ready_for_training

        # Backpressure: only group B from here.
        exp.store(_make_step_td(2, 4), slice(2, 4))  # B: t=0→1
        exp.store(_make_step_td(2, 4), slice(2, 4))  # B: t=1→2, done

        assert exp.full_rows == 4
        assert exp.ready_for_training

        # Row integrity: each row's agent_slot_ids are constant across timesteps.
        # This is what Cortex validates during training (the ValueError that
        # originally exposed the ring-buffer corruption bug).
        agent_slot_ids = exp.buffer["agent_slot_ids"][:, :, 0]
        assert bool((agent_slot_ids == agent_slot_ids[:, :1]).all())

    def test_mixed_t_in_row_without_done_agents(self) -> None:
        """Agents at different t_in_row offsets within a batch is normal async.

        With async_factor >= 2, recv() can return a group where some agents have
        been stepped more times than others (different t_in_row). This is fine —
        the key invariant is that none of them are done. Different offsets within
        the same slice do NOT constitute ghost progression.

        Uses bptt_horizon=3 to create room for offset divergence before any
        agent completes.
        """
        exp = _make_experience(total_agents=4, bptt_horizon=3)
        exp.reset_for_rollout()

        # Advance agents 0-1 by one extra step (simulates group A being faster).
        exp.store(_make_step_td(0, 2), slice(0, 2))  # 0-1 at t=1, 2-3 at t=0

        # Full slice: agents 0-1 at t=1, agents 2-3 at t=0 — mixed offsets, no done.
        exp.store(_make_step_td(0, 4), slice(0, 4))  # 0-1→t=2, 2-3→t=1

        # Again: 0-1 will complete (t=3 == bptt_horizon), 2-3 at t=2.
        # At entry, no agent is done yet, so this is not ghost progression.
        # The completion happens *during* this store call.
        exp.store(_make_step_td(0, 4), slice(0, 4))  # 0-1 done, 2-3→t=2

        assert exp.full_rows == 2

        # Backpressure: only finish group B.
        exp.store(_make_step_td(2, 4), slice(2, 4))  # 2-3 done

        assert exp.ready_for_training
        assert exp.full_rows == 4
