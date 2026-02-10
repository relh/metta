from __future__ import annotations

import random
from collections.abc import Mapping, Sequence


def sample_task_id_from_scores(
    *,
    task_ids: Sequence[int],
    scores: Mapping[int, float] | None,
    rng: random.Random,
) -> int:
    if not task_ids:
        raise ValueError("task_ids must be non-empty")

    if not scores:
        return rng.choice(task_ids)

    weights = [max(float(scores.get(task_id, 0.0)), 0.0) for task_id in task_ids]
    total = sum(weights)
    if total <= 0.0:
        return rng.choice(task_ids)

    return rng.choices(list(task_ids), weights=weights, k=1)[0]
