"""Regret-based learning progress curriculum algorithm."""

from typing import Any, Dict, List

import numpy as np

from metta.cogworks.curriculum.progress_tracking import (
    BidirectionalEmaTracker,
    sigmoid_normalized_distribution,
)

from .curriculum import CurriculumAlgorithmConfig, CurriculumTask
from .regret_algorithm_base import RegretAlgorithmBase


class RegretLearningProgressConfig(CurriculumAlgorithmConfig):
    """Configuration for regret learning progress."""

    type: str = "regret_learning_progress"

    optimal_value: float = 1.0
    regret_ema_timescale: float = 0.001
    use_bidirectional: bool = True
    exploration_bonus: float = 0.1
    progress_smoothing: float = 0.05
    invert_regret_progress: bool = True
    min_samples_for_lp: int = 2
    memory: int = 25
    max_memory_tasks: int = 1000
    max_slice_axes: int = 3
    enable_detailed_slice_logging: bool = False

    def algorithm_type(self) -> str:
        return "regret_learning_progress"

    def create(self, num_tasks: int) -> "RegretLearningProgressAlgorithm":
        return RegretLearningProgressAlgorithm(num_tasks, self)


class RegretLearningProgressAlgorithm(RegretAlgorithmBase):
    """Prioritize tasks where regret decreases fastest."""

    def __init__(self, num_tasks: int, hypers: RegretLearningProgressConfig):
        super().__init__(num_tasks, hypers, use_task_tracker=True)
        self.hypers: RegretLearningProgressConfig = hypers

        if hypers.use_bidirectional:
            self._init_bidirectional_regret_tracking()

    def _init_bidirectional_regret_tracking(self):
        """Initialize bidirectional regret tracking."""
        self._regret_outcomes: Dict[int, List[float]] = {}
        self._r_fast_by_task: Dict[int, float] = {}
        self._r_slow_by_task: Dict[int, float] = {}
        self._ema_tracker = BidirectionalEmaTracker(
            fast=self._r_fast_by_task,
            slow=self._r_slow_by_task,
            ema_timescale=self.hypers.regret_ema_timescale,
            slow_timescale_factor=0.2,
        )

    def score_tasks(self, task_ids: List[int]) -> Dict[int, float]:
        if not self.hypers.use_bidirectional:
            return super().score_tasks(task_ids)
        if not task_ids:
            return {}

        raw = np.array([self._raw_bidirectional_score(task_id) for task_id in task_ids], dtype=float)
        dist = sigmoid_normalized_distribution(raw)
        return {task_id: float(score) for task_id, score in zip(task_ids, dist, strict=True)}

    def _score_task(self, task_id: int) -> float:
        """Calculate regret learning progress score for a task."""
        if self.hypers.use_bidirectional:
            # score_tasks() handles normalization and avoids global cached distributions.
            return self._raw_bidirectional_score(task_id)

        if task_id in self._cache_valid_tasks and task_id in self._score_cache:
            return self._score_cache[task_id]

        task_stats = self.task_tracker.get_task_stats(task_id)

        if not task_stats or task_stats["completion_count"] < self.hypers.min_samples_for_lp:
            score = self.hypers.exploration_bonus
        else:
            regret_progress = self.regret_tracker.get_regret_progress(task_id)
            if regret_progress is None:
                score = self.hypers.exploration_bonus
            else:
                score = max(0.0, -regret_progress) if self.hypers.invert_regret_progress else abs(regret_progress)
                score += self._exploration_boost(task_stats["completion_count"])

        self._score_cache[task_id] = score
        self._cache_valid_tasks.add(task_id)
        return score

    def _raw_bidirectional_score(self, task_id: int) -> float:
        task_stats = self.task_tracker.get_task_stats(task_id)
        if not task_stats or task_stats["completion_count"] < self.hypers.min_samples_for_lp:
            return self.hypers.exploration_bonus

        if task_id not in self._regret_outcomes or len(self._regret_outcomes[task_id]) < 2:
            return self.hypers.exploration_bonus

        ema = self._ema_tracker.get(task_id)
        if ema is None:
            return self.hypers.exploration_bonus
        fast, slow = ema

        regret_lp = slow - fast
        lp = abs(regret_lp)
        if self.hypers.invert_regret_progress:
            lp += max(regret_lp, 0.0) * 0.2
        return lp

    def _get_task_stats(self, task_id: int):
        return self.task_tracker.get_task_stats(task_id)

    def _get_tracked_task_ids(self):
        return self.task_tracker.get_all_tracked_tasks()

    def _eviction_fraction(self) -> float:
        return 0.4

    def _after_task_evicted(self, task_id: int) -> None:
        if self.hypers.use_bidirectional:
            self._regret_outcomes.pop(task_id, None)
            self._ema_tracker.remove(task_id)
            self._invalidate_score_cache()

    def _after_update_task_performance(self, task_id: int, score: float) -> None:
        if not self.hypers.use_bidirectional:
            return

        regret = self.regret_tracker.compute_regret(score)
        self._regret_outcomes.setdefault(task_id, []).append(regret)
        self._regret_outcomes[task_id] = self._regret_outcomes[task_id][-self.hypers.memory :]
        mean_regret = float(np.mean(self._regret_outcomes[task_id])) if self._regret_outcomes[task_id] else 0.0
        self._ema_tracker.update(task_id, mean_regret)
        self._invalidate_score_cache()

    def _after_task_created(self, task: CurriculumTask) -> None:
        if self.hypers.use_bidirectional:
            self._invalidate_score_cache()

    def _detailed_stats_prefix(self) -> str:
        return "regret_lp"

    def _get_detailed_stats(self) -> Dict[str, float]:
        """Get detailed regret learning progress statistics."""
        if not self._regret_outcomes:
            return {
                "num_tracked_tasks": 0.0,
                "mean_regret_lp": 0.0,
                "num_decreasing_regret": 0.0,
                "num_increasing_regret": 0.0,
            }

        stats = {
            "num_tracked_tasks": float(len(self._regret_outcomes)),
        }

        regret_changes: list[float] = []
        for task_id in self._regret_outcomes.keys():
            ema = self._ema_tracker.get(task_id)
            if ema is None:
                continue
            fast, slow = ema
            regret_changes.append(slow - fast)

        if regret_changes:
            changes_arr = np.asarray(regret_changes, dtype=float)
            stats["mean_regret_lp"] = float(np.mean(changes_arr))
            stats["num_decreasing_regret"] = float(np.sum(changes_arr > 0))
            stats["num_increasing_regret"] = float(np.sum(changes_arr < 0))
        else:
            stats["mean_regret_lp"] = 0.0
            stats["num_decreasing_regret"] = 0.0
            stats["num_increasing_regret"] = 0.0

        return stats

    def _get_extra_state(self) -> Dict[str, Any]:
        if not self.hypers.use_bidirectional:
            return {}
        return {
            "regret_outcomes": {k: v for k, v in self._regret_outcomes.items()},
            "r_fast_by_task": dict(self._r_fast_by_task),
            "r_slow_by_task": dict(self._r_slow_by_task),
        }

    def _load_extra_state(self, state: Dict[str, Any]) -> None:
        if "regret_outcomes" not in state:
            return
        self._regret_outcomes = state["regret_outcomes"]
        if "r_fast_by_task" in state and "r_slow_by_task" in state:
            self._r_fast_by_task = dict(state["r_fast_by_task"] or {})
            self._r_slow_by_task = dict(state["r_slow_by_task"] or {})
        else:
            # Legacy checkpoints stored arrays aligned to `task_ids`.
            task_ids = state.get("task_ids", [])
            r_fast = state.get("r_fast")
            r_slow = state.get("r_slow")
            if isinstance(task_ids, list) and isinstance(r_fast, list) and isinstance(r_slow, list):
                if len(task_ids) != len(r_fast) or len(task_ids) != len(r_slow):
                    raise ValueError(
                        "Legacy checkpoint state has mismatched lengths for "
                        f"task_ids={len(task_ids)} r_fast={len(r_fast)} r_slow={len(r_slow)}"
                    )
                self._r_fast_by_task = {tid: float(val) for tid, val in zip(task_ids, r_fast, strict=True)}
                self._r_slow_by_task = {tid: float(val) for tid, val in zip(task_ids, r_slow, strict=True)}
            else:
                self._r_fast_by_task = {}
                self._r_slow_by_task = {}

        self._ema_tracker = BidirectionalEmaTracker(
            fast=self._r_fast_by_task,
            slow=self._r_slow_by_task,
            ema_timescale=self.hypers.regret_ema_timescale,
            slow_timescale_factor=0.2,
        )
