from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Protocol

from metta.cogworks.curriculum.sampling import sample_task_id_from_scores
from metta.cogworks.curriculum.synthetic_task_graph.dynamics import (
    DynamicsConfig,
    expected_competence_delta,
    practice_task,
)
from metta.cogworks.curriculum.synthetic_task_graph.graph import TaskGraph
from metta.cogworks.curriculum.types import CurriculumAlgorithm, CurriculumTask


class Sampler(Protocol):
    def select_task(self, graph: TaskGraph, competence: list[float], rng: random.Random) -> int: ...

    def observe(self, task_id: int, score: float) -> None: ...


@dataclass(frozen=True)
class SimulationResult:
    cumulative_score: float
    mean_competence: float
    task_counts: dict[int, int]
    scores: list[float]


class RandomSampler:
    def __init__(self) -> None:
        self._counts: dict[int, int] = {}

    def select_task(self, graph: TaskGraph, competence: list[float], rng: random.Random) -> int:
        task_id = rng.randrange(graph.num_tasks)
        self._counts[task_id] = self._counts.get(task_id, 0) + 1
        return task_id

    def observe(self, task_id: int, score: float) -> None:
        pass

    @property
    def task_counts(self) -> dict[int, int]:
        return dict(self._counts)


class GreedyOracleSampler:
    def __init__(self, config: DynamicsConfig) -> None:
        self._config = config
        self._counts: dict[int, int] = {}

    def select_task(self, graph: TaskGraph, competence: list[float], rng: random.Random) -> int:
        del rng
        best_task = 0
        best_delta = -1.0
        for task_id in range(graph.num_tasks):
            delta = expected_competence_delta(graph, competence, task_id, self._config)
            if delta > best_delta:
                best_task = task_id
                best_delta = delta
        self._counts[best_task] = self._counts.get(best_task, 0) + 1
        return best_task

    def observe(self, task_id: int, score: float) -> None:
        pass

    @property
    def task_counts(self) -> dict[int, int]:
        return dict(self._counts)


class CurriculumAlgorithmSampler:
    def __init__(self, *, algorithm: CurriculumAlgorithm, task_ids: list[int]) -> None:
        self._algorithm = algorithm
        self._task_ids = task_ids
        self._counts: dict[int, int] = {}

        for task_id in task_ids:
            self._algorithm.on_task_created(CurriculumTask(task_id, {"task_id": task_id}))

    def select_task(self, graph: TaskGraph, competence: list[float], rng: random.Random) -> int:
        del graph, competence
        scores = self._algorithm.score_tasks(self._task_ids)
        task_id = sample_task_id_from_scores(task_ids=self._task_ids, scores=scores, rng=rng)

        self._counts[task_id] = self._counts.get(task_id, 0) + 1
        return task_id

    def observe(self, task_id: int, score: float) -> None:
        self._algorithm.update_task_performance(task_id, score)

    @property
    def task_counts(self) -> dict[int, int]:
        return dict(self._counts)


def run_simulation(
    *,
    graph: TaskGraph,
    sampler: Sampler,
    config: DynamicsConfig,
    steps: int,
    seed: int,
) -> SimulationResult:
    if steps <= 0:
        raise ValueError("steps must be > 0")

    rng = random.Random(seed)
    competence: list[float] = [0.0] * graph.num_tasks

    scores: list[float] = []
    cumulative = 0.0

    for _step in range(steps):
        task_id = sampler.select_task(graph, competence, rng)
        competence, delta = practice_task(graph, competence, task_id, config)

        # Normalize to [0, 1] for curriculum algorithm compatibility.
        score = 0.0 if config.step_size <= 0 else min(1.0, max(0.0, delta / config.step_size))
        sampler.observe(task_id, score)

        scores.append(score)
        cumulative += score

    mean_comp = sum(competence) / len(competence) if competence else 0.0
    task_counts = getattr(sampler, "task_counts", {})
    return SimulationResult(
        cumulative_score=cumulative,
        mean_competence=mean_comp,
        task_counts=dict(task_counts),
        scores=scores,
    )
