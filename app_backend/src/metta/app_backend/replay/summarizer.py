"""Replay behavioral summarizer — extract temporal signals from .json.z replay files.

Walks sparse time-series data directly (no dense expansion) to compute:
1. Freeze temporal distribution — when does freezing happen?
2. Reward accumulation shape — front-loaded, linear, or back-loaded?
3. Noop clustering — scattered (deliberate) or clustered (stuck)?
"""

from __future__ import annotations

import json
import zlib

from pydantic import BaseModel


class ReplaySummary(BaseModel):
    """Compact behavioral summary extracted from a replay file."""

    episode_idx: int
    selection_reason: str  # "worst", "best", "median"
    reward: float
    steps: int
    freeze_by_quarter: list[float]  # [Q1%, Q2%, Q3%, Q4%]
    freeze_distribution: str  # "early_heavy" | "late_heavy" | "distributed" | "none"
    reward_by_quarter: list[float]  # [Q1_reward, Q2, Q3, Q4]
    reward_shape: str  # "frontloaded" | "linear" | "backloaded" | "flat"
    noop_by_quarter: list[float]  # [Q1%, Q2%, Q3%, Q4%]
    noop_pattern: str  # "clustered" | "distributed" | "none"


def parse_replay(data: bytes) -> dict:
    """Decompress and parse a .json.z replay file."""
    return json.loads(zlib.decompress(data))


def _quarter_boundaries(num_steps: int) -> list[int]:
    """Return step boundaries for 4 quarters: [0, q1, q2, q3, num_steps]."""
    q = num_steps / 4
    return [0, int(q), int(2 * q), int(3 * q), num_steps]


def _walk_sparse_bool(pairs: list, num_steps: int) -> list[float]:
    """Compute % True per quarter from sparse [[step, bool], ...] pairs.

    Pairs are sorted by step. Each pair sets the value from that step until
    the next pair (or end of episode).
    """
    if not pairs or num_steps <= 0:
        return [0.0, 0.0, 0.0, 0.0]

    bounds = _quarter_boundaries(num_steps)
    true_ticks = [0.0, 0.0, 0.0, 0.0]

    for i, (start_step, value) in enumerate(pairs):
        if not value:
            continue
        end_step = pairs[i + 1][0] if i + 1 < len(pairs) else num_steps

        for q in range(4):
            q_start = bounds[q]
            q_end = bounds[q + 1]
            overlap_start = max(start_step, q_start)
            overlap_end = min(end_step, q_end)
            if overlap_start < overlap_end:
                true_ticks[q] += overlap_end - overlap_start

    quarter_len = num_steps / 4
    if quarter_len <= 0:
        return [0.0, 0.0, 0.0, 0.0]
    return [round(t / quarter_len, 4) for t in true_ticks]


def _walk_sparse_reward(pairs: list, num_steps: int) -> list[float]:
    """Compute reward accumulated per quarter from sparse [[step, value], ...].

    current_reward tracks instantaneous reward; changes indicate reward events.
    We sum the deltas (value changes) within each quarter.
    """
    if not pairs or num_steps <= 0:
        return [0.0, 0.0, 0.0, 0.0]

    bounds = _quarter_boundaries(num_steps)
    reward_per_q = [0.0, 0.0, 0.0, 0.0]

    prev_val = 0.0
    for step, value in pairs:
        delta = value - prev_val
        prev_val = value
        if delta == 0:
            continue
        for q in range(4):
            if bounds[q] <= step < bounds[q + 1]:
                reward_per_q[q] += delta
                break

    return [round(r, 4) for r in reward_per_q]


def _walk_sparse_action(pairs: list, num_steps: int, noop_id: int = 0) -> list[float]:
    """Compute noop % per quarter from sparse [[step, action_id], ...].

    Each pair represents the action taken at that step. We count how many
    actions in each quarter are noop_id vs total actions in that quarter.
    """
    if not pairs or num_steps <= 0:
        return [0.0, 0.0, 0.0, 0.0]

    bounds = _quarter_boundaries(num_steps)
    noop_count = [0, 0, 0, 0]
    total_count = [0, 0, 0, 0]

    for step, action_id in pairs:
        for q in range(4):
            if bounds[q] <= step < bounds[q + 1]:
                total_count[q] += 1
                if action_id == noop_id:
                    noop_count[q] += 1
                break

    return [round(noop_count[q] / total_count[q], 4) if total_count[q] > 0 else 0.0 for q in range(4)]


def _classify_distribution(quarters: list[float]) -> str:
    """Classify temporal distribution of a boolean signal."""
    total = sum(quarters)
    if total < 0.01:
        return "none"
    first_half = quarters[0] + quarters[1]
    second_half = quarters[2] + quarters[3]
    if first_half > total * 0.65:
        return "early_heavy"
    if second_half > total * 0.65:
        return "late_heavy"
    return "distributed"


def _classify_reward_shape(quarters: list[float]) -> str:
    """Classify reward accumulation shape."""
    total = sum(quarters)
    if total < 0.01:
        return "flat"
    first_half = quarters[0] + quarters[1]
    second_half = quarters[2] + quarters[3]
    if first_half > total * 0.65:
        return "frontloaded"
    if second_half > total * 0.65:
        return "backloaded"
    # Check linearity: each quarter should be roughly 25% of total
    expected = total / 4
    max_dev = max(abs(q - expected) for q in quarters)
    if max_dev < expected * 0.5:
        return "linear"
    return "frontloaded" if quarters[0] > quarters[3] else "backloaded"


def _classify_noop_pattern(quarters: list[float]) -> str:
    """Classify noop temporal pattern."""
    total = sum(quarters)
    if total < 0.02:
        return "none"
    # Clustered: one quarter has disproportionate noop rate
    max_q = max(quarters)
    if max_q > total * 0.5:
        return "clustered"
    return "distributed"


def summarize_replay(
    replay: dict,
    agent_indices: list[int],
    episode_idx: int,
    reward: float,
    reason: str,
) -> ReplaySummary | None:
    """Extract behavioral summary from a parsed replay for specified agents.

    Returns None if the replay lacks required data.
    """
    num_steps = replay.get("max_steps", 0)
    objects = replay.get("objects", [])
    if not objects or num_steps <= 0:
        return None

    # Collect sparse data across our agents
    all_frozen_pairs: list[list] = []
    all_reward_pairs: list[list] = []
    all_action_pairs: list[list] = []

    # Determine which object indices correspond to our agents
    agent_obj_indices = []
    agent_idx_counter = 0
    for obj_idx, obj in enumerate(objects):
        type_name = obj.get("type_name", "")
        if isinstance(type_name, list):
            type_name = type_name[0][1] if type_name else ""
        if type_name == "agent":
            if agent_idx_counter in agent_indices:
                agent_obj_indices.append(obj_idx)
            agent_idx_counter += 1

    for obj_idx in agent_obj_indices:
        obj = objects[obj_idx]

        frozen = obj.get("frozen", obj.get("is_frozen"))
        if isinstance(frozen, list):
            all_frozen_pairs.extend(frozen)

        reward_field = obj.get("current_reward")
        if isinstance(reward_field, list):
            all_reward_pairs.extend(reward_field)

        action_field = obj.get("action_id")
        if isinstance(action_field, list):
            all_action_pairs.extend(action_field)

    # Sort by step
    all_frozen_pairs.sort(key=lambda p: p[0])
    all_reward_pairs.sort(key=lambda p: p[0])
    all_action_pairs.sort(key=lambda p: p[0])

    # Determine noop action ID from replay metadata
    action_names = replay.get("action_names", [])
    noop_id = action_names.index("noop") if "noop" in action_names else 0

    freeze_by_q = _walk_sparse_bool(all_frozen_pairs, num_steps)
    reward_by_q = _walk_sparse_reward(all_reward_pairs, num_steps)
    noop_by_q = _walk_sparse_action(all_action_pairs, num_steps, noop_id)

    return ReplaySummary(
        episode_idx=episode_idx,
        selection_reason=reason,
        reward=reward,
        steps=num_steps,
        freeze_by_quarter=freeze_by_q,
        freeze_distribution=_classify_distribution(freeze_by_q),
        reward_by_quarter=reward_by_q,
        reward_shape=_classify_reward_shape(reward_by_q),
        noop_by_quarter=noop_by_q,
        noop_pattern=_classify_noop_pattern(noop_by_q),
    )


def select_replay_episodes(
    episodes: list[dict],
    max_n: int = 3,
) -> list[dict]:
    """Select up to max_n episodes for replay analysis.

    Picks worst, best, and median reward episodes that have a replay_url.
    Each dict in episodes must have 'reward' and 'replay_url' keys.
    Returns list of dicts with added 'reason' and 'index' keys.
    """
    with_replay = [(i, ep) for i, ep in enumerate(episodes) if ep.get("replay_url")]
    if not with_replay:
        return []

    sorted_by_reward = sorted(with_replay, key=lambda x: x[1]["reward"])

    selected: dict[int, dict] = {}

    # Worst
    idx, ep = sorted_by_reward[0]
    selected[idx] = {**ep, "reason": "worst", "index": idx}

    # Best
    if len(sorted_by_reward) > 1:
        idx, ep = sorted_by_reward[-1]
        if idx not in selected:
            selected[idx] = {**ep, "reason": "best", "index": idx}

    # Median
    if len(sorted_by_reward) > 2:
        mid = len(sorted_by_reward) // 2
        idx, ep = sorted_by_reward[mid]
        if idx not in selected:
            selected[idx] = {**ep, "reason": "median", "index": idx}

    return list(selected.values())[:max_n]
