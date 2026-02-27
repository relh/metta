from __future__ import annotations

import random
from uuid import UUID


def _weighted_sample_with_replacement(
    policy_ids: list[UUID],
    weights: list[float],
    k: int,
) -> list[UUID]:
    if sum(weights) == 0:
        return random.choices(policy_ids, k=k)
    return random.choices(policy_ids, weights=weights, k=k)


def sample_teams(
    policy_scores: dict[UUID, float],
    team_size: int,
    num_teams: int,
    min_teams_per_policy: int,
) -> list[list[UUID]]:
    policy_ids = list(policy_scores)
    if not policy_ids:
        raise ValueError("Need at least one policy to sample teams")

    scores = [max(policy_scores[pid], 0.0) for pid in policy_ids]
    total = sum(scores)
    if total == 0:
        weights = [1.0 / len(policy_ids)] * len(policy_ids)
    else:
        weights = [s / total for s in scores]

    teams: list[list[UUID]] = []
    policy_counts: dict[UUID, int] = {pid: 0 for pid in policy_ids}

    for _ in range(num_teams):
        team = _weighted_sample_with_replacement(policy_ids, weights, team_size)
        teams.append(team)
        for pid in set(team):
            policy_counts[pid] += 1

    for pid in policy_ids:
        while policy_counts[pid] < min_teams_per_policy:
            team = _weighted_sample_with_replacement(policy_ids, weights, team_size)
            if pid not in team:
                team[random.randrange(team_size)] = pid
            teams.append(team)
            for p in set(team):
                policy_counts[p] += 1

    return teams
