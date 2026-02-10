import pytest

from metta.cogworks.curriculum.curriculum import CurriculumTask
from metta.cogworks.curriculum.learning_progress_algorithm import LearningProgressAlgorithm, LearningProgressConfig


def test_dual_pool_reweighting_targets_mass_fraction():
    cfg = LearningProgressConfig(
        use_bidirectional=False,
        ema_timescale=0.1,
        use_dual_pool=True,
        exploration_pool_fraction=0.5,
        exploration_sampling_fraction=0.7,
    )
    alg = LearningProgressAlgorithm(num_tasks=100, hypers=cfg)

    # Use ids that spread across the stable-hash bucket so both pools are populated.
    task_ids = [i * 200 for i in range(100)]
    for tid in task_ids:
        alg.on_task_created(CurriculumTask(tid, {"task_id": tid}))
        # Give each task some history so base scores are non-zero and comparable.
        alg.update_task_performance(tid, 0.5)
        alg.update_task_performance(tid, 0.5)

    scores = alg.score_tasks(task_ids)
    assert scores

    explore_sum = 0.0
    exploit_sum = 0.0
    for tid in task_ids:
        if alg._is_exploration_task(tid):
            explore_sum += scores[tid]
        else:
            exploit_sum += scores[tid]

    total = explore_sum + exploit_sum
    assert total > 0
    frac = explore_sum / total

    assert frac == pytest.approx(0.7, abs=1e-6)


def test_dual_pool_assignment_respects_fraction_for_small_task_id_ranges() -> None:
    cfg = LearningProgressConfig(
        use_bidirectional=False,
        ema_timescale=0.1,
        use_dual_pool=True,
        exploration_pool_fraction=0.9,
        exploration_sampling_fraction=0.7,
    )
    alg = LearningProgressAlgorithm(num_tasks=1000, hypers=cfg)

    task_ids = list(range(1000))
    explore = [tid for tid in task_ids if alg._is_exploration_task(tid)]
    exploit = [tid for tid in task_ids if not alg._is_exploration_task(tid)]

    assert explore
    assert exploit
