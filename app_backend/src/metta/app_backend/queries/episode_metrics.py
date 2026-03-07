from uuid import UUID

from metta.app_backend.config import DEFAULT_EPISODE_AGENT_METRIC_ALLOWLIST

ALLOWED_EPISODE_AGENT_METRICS: set[str] = set(DEFAULT_EPISODE_AGENT_METRIC_ALLOWLIST)


def filter_agent_metrics(
    agent_metrics: list[tuple[int, str, float]],
) -> list[tuple[int, str, float]]:
    return [(aid, name, val) for aid, name, val in agent_metrics if name in ALLOWED_EPISODE_AGENT_METRICS]


def aggregate_policy_agent_counts(agent_policy_map: dict[int, UUID]) -> dict[UUID, int]:
    counts: dict[UUID, int] = {}
    for pv_id in agent_policy_map.values():
        counts[pv_id] = counts.get(pv_id, 0) + 1
    return counts


def aggregate_policy_metrics(
    agent_metrics: list[tuple[int, str, float]],
    agent_policy_map: dict[int, UUID],
) -> dict[UUID, dict[str, float]]:
    result: dict[UUID, dict[str, float]] = {}
    for agent_id, metric_name, metric_value in agent_metrics:
        if agent_id not in agent_policy_map:
            continue
        pv_id = agent_policy_map[agent_id]
        m = result.setdefault(pv_id, {})
        m[metric_name] = m.get(metric_name, 0.0) + float(metric_value)
    return result
