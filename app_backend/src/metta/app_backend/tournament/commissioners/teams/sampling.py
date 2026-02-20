from __future__ import annotations

import random
from uuid import UUID


def _weighted_sample_without_replacement(
    policy_ids: list[UUID],
    weights: list[float],
    k: int,
) -> list[UUID]:
    available = list(range(len(policy_ids)))
    selected: list[UUID] = []
    remaining_weights = list(weights)

    for _ in range(k):
        total = sum(remaining_weights[i] for i in available)
        if total == 0:
            pick = random.choice(available)
        else:
            r = random.random() * total
            cumulative = 0.0
            pick = available[-1]
            for i in available:
                cumulative += remaining_weights[i]
                if cumulative >= r:
                    pick = i
                    break
        selected.append(policy_ids[pick])
        available.remove(pick)

    return selected


def sample_teams(
    policy_scores: dict[UUID, float],
    team_size: int,
    num_teams: int,
    min_teams_per_policy: int,
) -> list[list[UUID]]:
    policy_ids = list(policy_scores.keys())
    if len(policy_ids) < team_size:
        raise ValueError(f"Need at least {team_size} policies for {team_size}-policy teams, got {len(policy_ids)}")

    scores = [max(policy_scores[pid], 0.0) for pid in policy_ids]
    total = sum(scores)
    if total == 0:
        weights = [1.0 / len(policy_ids)] * len(policy_ids)
    else:
        weights = [s / total for s in scores]

    teams: list[list[UUID]] = []
    policy_counts: dict[UUID, int] = {pid: 0 for pid in policy_ids}

    for _ in range(num_teams):
        team = _weighted_sample_without_replacement(policy_ids, weights, team_size)
        teams.append(team)
        for pid in team:
            policy_counts[pid] += 1

    for pid in policy_ids:
        while policy_counts[pid] < min_teams_per_policy:
            remaining = [p for p in policy_ids if p != pid]
            remaining_weights = [weights[policy_ids.index(p)] for p in remaining]
            other = _weighted_sample_without_replacement(remaining, remaining_weights, team_size - 1)
            team = [pid] + other
            random.shuffle(team)
            teams.append(team)
            for p in team:
                policy_counts[p] += 1

    return teams
