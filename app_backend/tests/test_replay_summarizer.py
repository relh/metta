"""Tests for the replay behavioral summarizer."""

from __future__ import annotations

import json
import zlib

from metta.app_backend.replay.summarizer import (
    ReplaySummary,
    _classify_distribution,
    _classify_noop_pattern,
    _classify_reward_shape,
    _walk_sparse_action,
    _walk_sparse_bool,
    _walk_sparse_reward,
    parse_replay,
    select_replay_episodes,
    summarize_replay,
)

# === parse_replay ===


def test_parse_replay():
    data = {"version": 4, "objects": []}
    compressed = zlib.compress(json.dumps(data).encode())
    result = parse_replay(compressed)
    assert result == data


# === _walk_sparse_bool ===


def test_walk_sparse_bool_empty():
    assert _walk_sparse_bool([], 1000) == [0.0, 0.0, 0.0, 0.0]


def test_walk_sparse_bool_always_true():
    pairs = [[0, True]]
    result = _walk_sparse_bool(pairs, 1000)
    assert all(abs(r - 1.0) < 0.01 for r in result)


def test_walk_sparse_bool_first_half_only():
    # Frozen from step 0-500 out of 1000 steps
    pairs = [[0, True], [500, False]]
    result = _walk_sparse_bool(pairs, 1000)
    # Q1 (0-250): fully frozen = 1.0
    # Q2 (250-500): fully frozen = 1.0
    # Q3 (500-750): not frozen = 0.0
    # Q4 (750-1000): not frozen = 0.0
    assert abs(result[0] - 1.0) < 0.01
    assert abs(result[1] - 1.0) < 0.01
    assert abs(result[2] - 0.0) < 0.01
    assert abs(result[3] - 0.0) < 0.01


def test_walk_sparse_bool_last_quarter():
    # Frozen only in Q4
    pairs = [[0, False], [750, True]]
    result = _walk_sparse_bool(pairs, 1000)
    assert abs(result[0] - 0.0) < 0.01
    assert abs(result[1] - 0.0) < 0.01
    assert abs(result[2] - 0.0) < 0.01
    assert abs(result[3] - 1.0) < 0.01


def test_walk_sparse_bool_partial_overlap():
    # Frozen from step 200-800 out of 1000 steps
    pairs = [[0, False], [200, True], [800, False]]
    result = _walk_sparse_bool(pairs, 1000)
    # Q1 (0-250): 50/250 = 0.2
    # Q2 (250-500): 250/250 = 1.0
    # Q3 (500-750): 250/250 = 1.0
    # Q4 (750-1000): 50/250 = 0.2
    assert abs(result[0] - 0.2) < 0.01
    assert abs(result[1] - 1.0) < 0.01
    assert abs(result[2] - 1.0) < 0.01
    assert abs(result[3] - 0.2) < 0.01


def test_walk_sparse_bool_zero_steps():
    assert _walk_sparse_bool([[0, True]], 0) == [0.0, 0.0, 0.0, 0.0]


# === _walk_sparse_reward ===


def test_walk_sparse_reward_empty():
    assert _walk_sparse_reward([], 1000) == [0.0, 0.0, 0.0, 0.0]


def test_walk_sparse_reward_linear():
    # Reward increases evenly: +1 each quarter
    pairs = [[0, 0], [125, 1], [375, 2], [625, 3], [875, 4]]
    result = _walk_sparse_reward(pairs, 1000)
    assert all(abs(r - 1.0) < 0.01 for r in result)


def test_walk_sparse_reward_frontloaded():
    # All reward in Q1
    pairs = [[0, 0], [100, 10]]
    result = _walk_sparse_reward(pairs, 1000)
    assert abs(result[0] - 10.0) < 0.01
    assert abs(result[1] - 0.0) < 0.01
    assert abs(result[2] - 0.0) < 0.01
    assert abs(result[3] - 0.0) < 0.01


def test_walk_sparse_reward_backloaded():
    # All reward in Q4
    pairs = [[0, 0], [900, 10]]
    result = _walk_sparse_reward(pairs, 1000)
    assert abs(result[0] - 0.0) < 0.01
    assert abs(result[3] - 10.0) < 0.01


# === _walk_sparse_action ===


def test_walk_sparse_action_all_noops():
    pairs = [[i * 10, 0] for i in range(100)]
    result = _walk_sparse_action(pairs, 1000, noop_id=0)
    assert all(abs(r - 1.0) < 0.01 for r in result)


def test_walk_sparse_action_no_noops():
    pairs = [[i * 10, 1] for i in range(100)]  # action_id=1 (move)
    result = _walk_sparse_action(pairs, 1000, noop_id=0)
    assert all(abs(r - 0.0) < 0.01 for r in result)


def test_walk_sparse_action_mixed():
    # Q1: 5 noops out of 10, Q2-Q4: no noops
    pairs = []
    for i in range(10):
        pairs.append([i * 25, 0 if i < 5 else 1])  # Q1
    for i in range(10):
        pairs.append([250 + i * 25, 1])  # Q2
    result = _walk_sparse_action(pairs, 1000, noop_id=0)
    assert abs(result[0] - 0.5) < 0.01
    assert abs(result[1] - 0.0) < 0.01


# === _classify_distribution ===


def test_classify_distribution_none():
    assert _classify_distribution([0.0, 0.0, 0.0, 0.0]) == "none"


def test_classify_distribution_early_heavy():
    assert _classify_distribution([0.5, 0.3, 0.1, 0.0]) == "early_heavy"


def test_classify_distribution_late_heavy():
    assert _classify_distribution([0.0, 0.1, 0.3, 0.5]) == "late_heavy"


def test_classify_distribution_distributed():
    assert _classify_distribution([0.25, 0.25, 0.25, 0.25]) == "distributed"


# === _classify_reward_shape ===


def test_classify_reward_shape_flat():
    assert _classify_reward_shape([0.0, 0.0, 0.0, 0.0]) == "flat"


def test_classify_reward_shape_frontloaded():
    assert _classify_reward_shape([5.0, 3.0, 1.0, 0.0]) == "frontloaded"


def test_classify_reward_shape_backloaded():
    assert _classify_reward_shape([0.0, 1.0, 3.0, 5.0]) == "backloaded"


def test_classify_reward_shape_linear():
    assert _classify_reward_shape([2.5, 2.5, 2.5, 2.5]) == "linear"


# === _classify_noop_pattern ===


def test_classify_noop_pattern_none():
    assert _classify_noop_pattern([0.0, 0.0, 0.0, 0.0]) == "none"


def test_classify_noop_pattern_clustered():
    assert _classify_noop_pattern([0.8, 0.1, 0.0, 0.0]) == "clustered"


def test_classify_noop_pattern_distributed():
    assert _classify_noop_pattern([0.15, 0.15, 0.15, 0.15]) == "distributed"


# === summarize_replay ===


def _make_synthetic_replay(num_steps: int = 1000, num_agents: int = 2) -> dict:
    """Create a minimal synthetic replay for testing."""
    objects = []
    for agent_idx in range(num_agents):
        obj = {
            "type_name": "agent",
            "agent_id": agent_idx,
            "frozen": [[0, False], [400, True], [600, False]],
            "current_reward": [[0, 0], [200, 2.0], [500, 5.0], [800, 8.0]],
            "action_id": [[i * 10, 0 if i % 3 == 0 else 1] for i in range(100)],
        }
        objects.append(obj)
    # Add some wall objects
    for _ in range(5):
        objects.append({"type_name": "wall"})

    return {
        "version": 4,
        "max_steps": num_steps,
        "num_agents": num_agents,
        "objects": objects,
        "action_names": ["noop", "move", "change_vibe"],
    }


def test_summarize_replay_basic():
    replay = _make_synthetic_replay()
    result = summarize_replay(replay, agent_indices=[0, 1], episode_idx=0, reward=8.0, reason="best")

    assert isinstance(result, ReplaySummary)
    assert result.episode_idx == 0
    assert result.selection_reason == "best"
    assert result.reward == 8.0
    assert result.steps == 1000
    assert len(result.freeze_by_quarter) == 4
    assert len(result.reward_by_quarter) == 4
    assert len(result.noop_by_quarter) == 4
    assert result.freeze_distribution in ("early_heavy", "late_heavy", "distributed", "none")
    assert result.reward_shape in ("frontloaded", "linear", "backloaded", "flat")
    assert result.noop_pattern in ("clustered", "distributed", "none")


def test_summarize_replay_single_agent():
    replay = _make_synthetic_replay(num_agents=4)
    result = summarize_replay(replay, agent_indices=[0], episode_idx=1, reward=3.0, reason="worst")

    assert result is not None
    assert result.episode_idx == 1
    assert result.selection_reason == "worst"


def test_summarize_replay_empty_objects():
    replay = {"version": 4, "max_steps": 1000, "objects": []}
    result = summarize_replay(replay, agent_indices=[0], episode_idx=0, reward=0.0, reason="worst")
    assert result is None


def test_summarize_replay_zero_steps():
    replay = {"version": 4, "max_steps": 0, "objects": [{"type_name": "agent"}]}
    result = summarize_replay(replay, agent_indices=[0], episode_idx=0, reward=0.0, reason="worst")
    assert result is None


# === select_replay_episodes ===


def test_select_replay_episodes_no_replays():
    episodes = [{"reward": 1.0, "replay_url": None}, {"reward": 2.0}]
    assert select_replay_episodes(episodes) == []


def test_select_replay_episodes_one_replay():
    episodes = [
        {"reward": 1.0, "replay_url": "https://example.com/a.json.z"},
        {"reward": 2.0, "replay_url": None},
    ]
    result = select_replay_episodes(episodes)
    assert len(result) == 1
    assert result[0]["reason"] == "worst"


def test_select_replay_episodes_three_replays():
    episodes = [
        {"reward": 1.0, "replay_url": "https://example.com/a.json.z"},
        {"reward": 5.0, "replay_url": "https://example.com/b.json.z"},
        {"reward": 3.0, "replay_url": "https://example.com/c.json.z"},
    ]
    result = select_replay_episodes(episodes)
    assert len(result) == 3
    reasons = {r["reason"] for r in result}
    assert "worst" in reasons
    assert "best" in reasons
    assert "median" in reasons


def test_select_replay_episodes_all_have_urls():
    episodes = [{"reward": float(i), "replay_url": f"https://example.com/{i}.json.z"} for i in range(10)]
    result = select_replay_episodes(episodes, max_n=3)
    assert len(result) == 3
    # Worst should be reward=0, best should be reward=9
    worst = next(r for r in result if r["reason"] == "worst")
    best = next(r for r in result if r["reason"] == "best")
    assert worst["reward"] == 0.0
    assert best["reward"] == 9.0


def test_select_replay_episodes_two_replays():
    episodes = [
        {"reward": 1.0, "replay_url": "https://example.com/a.json.z"},
        {"reward": 5.0, "replay_url": "https://example.com/b.json.z"},
    ]
    result = select_replay_episodes(episodes)
    assert len(result) == 2
    reasons = {r["reason"] for r in result}
    assert "worst" in reasons
    assert "best" in reasons
