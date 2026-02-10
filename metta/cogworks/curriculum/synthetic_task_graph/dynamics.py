from __future__ import annotations

from dataclasses import dataclass

from metta.cogworks.curriculum.synthetic_task_graph.graph import TaskGraph


@dataclass(frozen=True)
class DynamicsConfig:
    step_size: float = 0.1
    cross_task_decay: float = 0.001
    prereq_threshold: float = 0.2
    difficulty_exponent: float = 1.0


def _prereq_gate(graph: TaskGraph, competence: list[float], task_id: int, prereq_threshold: float) -> float:
    prereqs = graph.prereqs[task_id]
    if not prereqs:
        return 1.0

    prereq_competence = min(competence[p] for p in prereqs)
    if prereq_competence <= prereq_threshold:
        return 0.0

    # Linear ramp from threshold..1 into 0..1.
    return (prereq_competence - prereq_threshold) / (1.0 - prereq_threshold)


def expected_competence_delta(graph: TaskGraph, competence: list[float], task_id: int, config: DynamicsConfig) -> float:
    current = competence[task_id]
    if current >= 1.0:
        return 0.0

    gate = _prereq_gate(graph, competence, task_id, config.prereq_threshold)
    if gate <= 0.0:
        return 0.0

    difficulty = graph.difficulties[task_id]
    learn_scale = (1.0 - difficulty) ** config.difficulty_exponent
    raw_delta = config.step_size * gate * learn_scale * (1.0 - current)
    if raw_delta <= 0.0:
        return 0.0
    return min(1.0 - current, raw_delta)


def practice_task(
    graph: TaskGraph, competence: list[float], task_id: int, config: DynamicsConfig
) -> tuple[list[float], float]:
    new_competence = competence.copy()

    delta = expected_competence_delta(graph, competence, task_id, config)
    if delta > 0.0:
        new_competence[task_id] = min(1.0, new_competence[task_id] + delta)

    decay_multiplier = 1.0 - config.cross_task_decay
    if decay_multiplier < 0.0:
        decay_multiplier = 0.0

    for i in range(len(new_competence)):
        if i == task_id:
            continue
        new_competence[i] *= decay_multiplier

    return new_competence, delta
