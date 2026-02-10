from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class TaskGraph:
    difficulties: tuple[float, ...]
    prereqs: tuple[tuple[int, ...], ...]

    @property
    def num_tasks(self) -> int:
        return len(self.difficulties)

    def validate(self) -> None:
        if len(self.prereqs) != self.num_tasks:
            raise ValueError("prereqs length must match difficulties length")

        for task_id, prereq_ids in enumerate(self.prereqs):
            if len(prereq_ids) != len(set(prereq_ids)):
                raise ValueError(f"duplicate prereqs for task {task_id}")
            for prereq_id in prereq_ids:
                if prereq_id < 0 or prereq_id >= self.num_tasks:
                    raise ValueError(f"invalid prereq {prereq_id} for task {task_id}")
                if prereq_id >= task_id:
                    raise ValueError(f"prereq {prereq_id} must be < task_id {task_id} (DAG invariant)")


def generate_random_task_graph(
    *,
    num_tasks: int,
    max_prereqs: int,
    prereq_prob: float,
    rng: random.Random,
) -> TaskGraph:
    if num_tasks <= 0:
        raise ValueError("num_tasks must be > 0")
    if max_prereqs < 0:
        raise ValueError("max_prereqs must be >= 0")
    if not (0.0 <= prereq_prob <= 1.0):
        raise ValueError("prereq_prob must be in [0, 1]")

    difficulties: list[float] = [rng.random() for _ in range(num_tasks)]
    prereqs: list[tuple[int, ...]] = []

    for task_id in range(num_tasks):
        if task_id == 0 or max_prereqs == 0:
            prereqs.append(())
            continue

        candidates = [i for i in range(task_id) if rng.random() < prereq_prob]
        if not candidates:
            prereqs.append(())
            continue

        rng.shuffle(candidates)
        chosen = tuple(sorted(candidates[:max_prereqs]))
        prereqs.append(chosen)

    graph = TaskGraph(difficulties=tuple(difficulties), prereqs=tuple(prereqs))
    graph.validate()
    return graph
