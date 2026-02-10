from __future__ import annotations

from metta.cogworks.curriculum.regret_learning_progress_algorithm import (
    RegretLearningProgressAlgorithm,
    RegretLearningProgressConfig,
)


def test_bidirectional_regret_ema_updates_are_per_task() -> None:
    algo = RegretLearningProgressAlgorithm(
        num_tasks=100,
        hypers=RegretLearningProgressConfig(use_bidirectional=True, regret_ema_timescale=0.5),
    )

    task_a = 1
    task_b = 2

    # Initialize task B EMAs.
    algo.update_task_performance(task_b, score=0.0)
    algo.update_task_performance(task_b, score=0.5)
    ema_before = algo._ema_tracker.get(task_b)
    assert ema_before is not None
    fast_before, slow_before = ema_before

    # Update task A multiple times; task B's stored EMA state should not change.
    for _ in range(10):
        algo.update_task_performance(task_a, score=0.0)

    ema_after = algo._ema_tracker.get(task_b)
    assert ema_after is not None
    fast_after, slow_after = ema_after

    assert fast_after == fast_before
    assert slow_after == slow_before
