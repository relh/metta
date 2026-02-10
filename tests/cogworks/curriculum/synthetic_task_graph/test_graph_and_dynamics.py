import random

import pytest

from metta.cogworks.curriculum.synthetic_task_graph.dynamics import (
    DynamicsConfig,
    expected_competence_delta,
    practice_task,
)
from metta.cogworks.curriculum.synthetic_task_graph.graph import TaskGraph, generate_random_task_graph


def test_generate_random_task_graph_is_dag():
    rng = random.Random(0)
    graph = generate_random_task_graph(num_tasks=50, max_prereqs=4, prereq_prob=0.3, rng=rng)

    assert graph.num_tasks == 50
    for task_id, prereq_ids in enumerate(graph.prereqs):
        for prereq_id in prereq_ids:
            assert prereq_id < task_id


def test_practice_task_monotonic_with_repeated_practice_single_task():
    graph = TaskGraph(difficulties=(0.0,), prereqs=((),))
    graph.validate()

    config = DynamicsConfig(step_size=0.2, cross_task_decay=0.0, prereq_threshold=0.2)
    competence = [0.0]

    last = competence[0]
    for _ in range(20):
        competence, delta = practice_task(graph, competence, 0, config)
        assert delta >= 0.0
        assert competence[0] >= last
        last = competence[0]

    assert competence[0] > 0.0
    assert competence[0] <= 1.0


def test_prereq_gating_blocks_learning_until_threshold():
    graph = TaskGraph(difficulties=(0.0, 0.0), prereqs=((), (0,)))
    graph.validate()

    config = DynamicsConfig(step_size=0.2, cross_task_decay=0.0, prereq_threshold=0.5)
    competence = [0.0, 0.0]

    # Cannot learn task 1 while prereq competence is below threshold.
    competence2, delta = practice_task(graph, competence, 1, config)
    assert competence2 == competence
    assert delta == 0.0

    # Raise prereq competence above threshold by practicing task 0.
    for _ in range(10):
        competence, _delta0 = practice_task(graph, competence, 0, config)
        if competence[0] > config.prereq_threshold:
            break

    assert competence[0] > config.prereq_threshold

    # Now task 1 should start learning.
    competence2, delta = practice_task(graph, competence, 1, config)
    assert delta > 0.0
    assert competence2[1] > competence[1]


@pytest.mark.parametrize("difficulty", [0.0, 0.5, 0.9])
def test_expected_delta_is_bounded_by_step_size(difficulty: float):
    graph = TaskGraph(difficulties=(difficulty,), prereqs=((),))
    graph.validate()
    config = DynamicsConfig(step_size=0.1, cross_task_decay=0.0)

    competence = [0.0]
    delta = expected_competence_delta(graph, competence, 0, config)
    assert 0.0 <= delta <= config.step_size
