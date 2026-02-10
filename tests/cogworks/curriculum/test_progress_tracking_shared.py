import numpy as np
import pytest

from metta.cogworks.curriculum.progress_tracking import BidirectionalEmaTracker, sigmoid_normalized_distribution
from metta.cogworks.curriculum.regret_learning_progress_algorithm import (
    RegretLearningProgressAlgorithm,
    RegretLearningProgressConfig,
)


def test_bidirectional_ema_tracker_updates_only_one_task():
    fast: dict[int, float] = {}
    slow: dict[int, float] = {}
    tracker = BidirectionalEmaTracker(fast=fast, slow=slow, ema_timescale=0.5, slow_timescale_factor=0.2)

    tracker.update(1, 1.0)
    tracker.update(2, 2.0)

    fast_2_before = fast[2]
    slow_2_before = slow[2]

    tracker.update(1, 0.0)

    assert fast[2] == fast_2_before
    assert slow[2] == slow_2_before


def test_regret_learning_progress_updates_do_not_couple_tasks():
    cfg = RegretLearningProgressConfig(
        optimal_value=1.0,
        regret_ema_timescale=0.5,
        use_bidirectional=True,
        memory=10,
    )
    algo = RegretLearningProgressAlgorithm(num_tasks=10, hypers=cfg)

    # Seed both tasks with at least 2 samples so the bidirectional path is active.
    algo.update_task_performance(1, 0.0)  # regret=1.0
    algo.update_task_performance(1, 0.0)
    algo.update_task_performance(2, 0.5)  # regret=0.5
    algo.update_task_performance(2, 0.5)

    fast_2_before = algo._r_fast_by_task[2]
    slow_2_before = algo._r_slow_by_task[2]

    algo.update_task_performance(1, 0.0)

    assert algo._r_fast_by_task[2] == fast_2_before
    assert algo._r_slow_by_task[2] == slow_2_before


def test_regret_learning_progress_respects_min_samples_for_lp_in_bidirectional_mode() -> None:
    cfg = RegretLearningProgressConfig(
        optimal_value=1.0,
        regret_ema_timescale=0.5,
        use_bidirectional=True,
        memory=10,
        min_samples_for_lp=3,
        exploration_bonus=0.123,
    )
    algo = RegretLearningProgressAlgorithm(num_tasks=10, hypers=cfg)

    algo.update_task_performance(1, 0.0)  # regret=1.0
    algo.update_task_performance(1, 1.0)  # regret=0.0
    assert algo._raw_bidirectional_score(1) == cfg.exploration_bonus

    algo.update_task_performance(1, 0.0)
    assert algo._raw_bidirectional_score(1) != cfg.exploration_bonus


def test_regret_learning_progress_legacy_checkpoint_length_mismatch_raises() -> None:
    cfg = RegretLearningProgressConfig(
        optimal_value=1.0,
        regret_ema_timescale=0.5,
        use_bidirectional=True,
        memory=10,
    )
    algo = RegretLearningProgressAlgorithm(num_tasks=10, hypers=cfg)

    state = {
        "regret_outcomes": {},
        "task_ids": [1, 2, 3],
        "r_fast": [0.1, 0.2],
        "r_slow": [0.1, 0.2, 0.3],
    }

    with pytest.raises(ValueError, match="mismatched lengths"):
        algo._load_extra_state(state)


def test_sigmoid_normalized_distribution_does_not_center_for_small_task_sets() -> None:
    # Legacy behavior: when the positive subvector has <=2 entries, do not mean-center it.
    raw = np.array([0.0, 1.0, 2.0], dtype=float)
    out = sigmoid_normalized_distribution(raw)

    sub = np.array([1.0, 2.0], dtype=float)
    sub = 1 / (1 + np.exp(-np.clip(sub, -500, 500)))
    sub = sub / float(np.sum(sub))

    expected = np.array([0.0, sub[0], sub[1]], dtype=float)
    assert np.allclose(out, expected)


def test_sigmoid_normalized_distribution_centers_and_scales_for_larger_task_sets() -> None:
    raw = np.array([1.0, 2.0, 3.0], dtype=float)
    out = sigmoid_normalized_distribution(raw)

    sub = raw.copy()
    std = np.std(sub)
    assert std > 0
    sub = (sub - np.mean(sub)) / std
    sub = 1 / (1 + np.exp(-np.clip(sub, -500, 500)))
    sub = sub / float(np.sum(sub))

    assert np.allclose(out, sub)
