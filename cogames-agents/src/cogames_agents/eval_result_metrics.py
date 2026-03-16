from __future__ import annotations

import json
from typing import Any

_ALIGNED_JUNCTION_HELD_KEYS = (
    "cogs/aligned.junction.held",
    "aligned.junction.held",
    "junction.held",
)
_ALIGNED_JUNCTION_GAINED_KEYS = (
    "cogs/aligned.junction.gained",
    "aligned.junction.gained",
    "junction.gained",
)


def mission_summary_from_result(result_data: dict[str, Any]) -> dict[str, Any]:
    missions = result_data.get("missions", [])
    if not missions:
        return {}
    mission = missions[0]
    summary = mission.get("mission_summary", mission)
    return summary if isinstance(summary, dict) else {}


def parse_eval_result_text(text: str) -> dict[str, Any]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        json_start = text.find("{")
        if json_start < 0:
            raise
        data = json.loads(text[json_start:])
    return data if isinstance(data, dict) else {}


def first_policy_summary(summary: dict[str, Any]) -> dict[str, Any]:
    policy_summaries = summary.get("policy_summaries", [])
    if not policy_summaries:
        return {}
    policy_summary = policy_summaries[0]
    return policy_summary if isinstance(policy_summary, dict) else {}


def average_policy_reward(summary: dict[str, Any], policy_index: int = 0) -> float | None:
    rewards_by_episode = summary.get("per_episode_per_policy_avg_rewards", {})
    reward_values: list[float] = []

    if isinstance(rewards_by_episode, dict):
        for episode_rewards in rewards_by_episode.values():
            if isinstance(episode_rewards, list):
                if policy_index < len(episode_rewards) and episode_rewards[policy_index] is not None:
                    reward_values.append(float(episode_rewards[policy_index]))
            elif episode_rewards is not None and policy_index == 0:
                reward_values.append(float(episode_rewards))

    if reward_values:
        return sum(reward_values) / len(reward_values)

    policy_summary = first_policy_summary(summary)
    agent_metrics = policy_summary.get("avg_agent_metrics", {})
    reward = agent_metrics.get("reward") if isinstance(agent_metrics, dict) else None
    return float(reward) if reward is not None else None


def _first_numeric_value(stats: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        value = stats.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return None


def extract_cogsguard_eval_metrics(result_data: dict[str, Any]) -> dict[str, float | None]:
    summary = mission_summary_from_result(result_data)
    game_stats = summary.get("avg_game_stats", {})
    policy_summary = first_policy_summary(summary)
    agent_metrics = policy_summary.get("avg_agent_metrics", {})

    if not isinstance(game_stats, dict):
        game_stats = {}
    if not isinstance(agent_metrics, dict):
        agent_metrics = {}

    aligned_junction_held = _first_numeric_value(game_stats, _ALIGNED_JUNCTION_HELD_KEYS)
    aligned_junction_gained = _first_numeric_value(game_stats, _ALIGNED_JUNCTION_GAINED_KEYS)

    return {
        "aligned.junction.held": 0.0 if aligned_junction_held is None else aligned_junction_held,
        "aligned.junction.gained": 0.0 if aligned_junction_gained is None else aligned_junction_gained,
        "heart.gained": float(agent_metrics["heart.gained"]) if "heart.gained" in agent_metrics else None,
        "heart.lost": float(agent_metrics["heart.lost"]) if "heart.lost" in agent_metrics else None,
        "reward": average_policy_reward(summary),
        "action_timeouts": float(policy_summary["action_timeouts"]) if "action_timeouts" in policy_summary else None,
    }
