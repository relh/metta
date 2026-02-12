"""Tests for regret learning progress curriculum algorithm."""

import random

import pytest

from metta.cogworks.curriculum.curriculum import CurriculumTask
from metta.cogworks.curriculum.regret_learning_progress_algorithm import (
    RegretLearningProgressAlgorithm,
    RegretLearningProgressConfig,
)


def _register_task(algorithm: RegretLearningProgressAlgorithm, task_id: int) -> int:
    algorithm.on_task_created(CurriculumTask(task_id, {"task_id": task_id}))
    return task_id


def _create_tasks(
    algorithm: RegretLearningProgressAlgorithm,
    count: int,
    rng: random.Random,
) -> list[int]:
    task_ids: list[int] = []
    for _index in range(count):
        task_id = rng.randint(0, 1_000_000)
        task_ids.append(_register_task(algorithm, task_id))
    return task_ids


class TestRegretLearningProgressBidirectional:
    def test_updates_only_completed_task_ema(self, random_seed):
        config = RegretLearningProgressConfig(
            use_bidirectional=True,
            regret_ema_timescale=0.5,
            memory=10,
            min_samples_for_lp=2,
        )
        algorithm = RegretLearningProgressAlgorithm(num_tasks=2, hypers=config)

        rng = random.Random(random_seed)
        task1_id, task2_id = _create_tasks(algorithm, 2, rng)

        # Seed both tasks with >=2 samples so their EMAs exist and are "live".
        algorithm.update_task_performance(task1_id, 0.2)
        algorithm.update_task_performance(task1_id, 0.4)
        algorithm.update_task_performance(task2_id, 0.3)
        algorithm.update_task_performance(task2_id, 0.6)

        assert task1_id in algorithm._r_fast_by_task
        assert task1_id in algorithm._r_slow_by_task
        assert task2_id in algorithm._r_fast_by_task
        assert task2_id in algorithm._r_slow_by_task

        before_fast_task2 = algorithm._r_fast_by_task[task2_id]
        before_slow_task2 = algorithm._r_slow_by_task[task2_id]
        before_fast_task1 = algorithm._r_fast_by_task[task1_id]
        before_slow_task1 = algorithm._r_slow_by_task[task1_id]

        # Update only task1; task2's EMA state must not change.
        algorithm.update_task_performance(task1_id, 0.9)

        after_fast_task2 = algorithm._r_fast_by_task[task2_id]
        after_slow_task2 = algorithm._r_slow_by_task[task2_id]
        after_fast_task1 = algorithm._r_fast_by_task[task1_id]
        after_slow_task1 = algorithm._r_slow_by_task[task1_id]

        assert after_fast_task2 == pytest.approx(before_fast_task2)
        assert after_slow_task2 == pytest.approx(before_slow_task2)

        # Sanity: task1 should have moved.
        moved_fast = after_fast_task1 != pytest.approx(before_fast_task1)
        moved_slow = after_slow_task1 != pytest.approx(before_slow_task1)
        assert moved_fast or moved_slow

    def test_scoring_runs_with_bidirectional_distribution(self, random_seed):
        config = RegretLearningProgressConfig(
            use_bidirectional=True,
            regret_ema_timescale=0.25,
            memory=10,
            min_samples_for_lp=2,
        )
        algorithm = RegretLearningProgressAlgorithm(num_tasks=3, hypers=config)

        rng = random.Random(random_seed)
        task_ids = _create_tasks(algorithm, 3, rng)

        for _ in range(3):
            algorithm.update_task_performance(task_ids[0], 0.1)
            algorithm.update_task_performance(task_ids[1], 0.5)
            algorithm.update_task_performance(task_ids[2], 0.9)

        scores = algorithm.score_tasks(task_ids)
        assert set(scores.keys()) == set(task_ids)
        assert all(score >= 0 for score in scores.values())
