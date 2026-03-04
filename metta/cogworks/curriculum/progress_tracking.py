"""Shared helpers for curriculum progress tracking.

This module centralizes a small amount of logic that multiple curriculum algorithms
need (bidirectional fast/slow EMA updates and score normalization).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import numpy as np


@dataclass
class BidirectionalEmaTracker:
    """Per-task fast/slow EMA tracker that updates in O(1) per observation.

    The tracker mutates the provided `fast`/`slow` dicts in-place so algorithms can
    preserve checkpoint field names when refactoring.
    """

    fast: Dict[int, float]
    slow: Dict[int, float]
    ema_timescale: float
    slow_timescale_factor: float = 0.2

    def update(self, task_id: int, value: float) -> None:
        if task_id not in self.fast:
            self.fast[task_id] = value
            self.slow[task_id] = value
            return

        alpha_fast = self.ema_timescale
        alpha_slow = self.ema_timescale * self.slow_timescale_factor

        self.fast[task_id] = value * alpha_fast + self.fast[task_id] * (1.0 - alpha_fast)
        self.slow[task_id] = value * alpha_slow + self.slow[task_id] * (1.0 - alpha_slow)

    def get(self, task_id: int) -> Optional[Tuple[float, float]]:
        fast = self.fast.get(task_id)
        slow = self.slow.get(task_id)
        if fast is None or slow is None:
            return None
        return fast, slow

    def remove(self, task_id: int) -> None:
        self.fast.pop(task_id, None)
        self.slow.pop(task_id, None)


def sigmoid_normalized_distribution(raw_scores: np.ndarray) -> np.ndarray:
    """Normalize raw (non-negative) scores into a distribution.

    Shared between LearningProgress and RegretLearningProgress: drop zero-mass tasks,
    z-score, sigmoid, and renormalize.
    """
    if raw_scores.size == 0:
        return raw_scores

    positive_mask = raw_scores > 0
    if not np.any(positive_mask):
        return np.zeros_like(raw_scores)

    sub = raw_scores[positive_mask]
    if sub.size > 2:
        std = np.std(sub)
        sub = (sub - np.mean(sub)) / std if std > 0 else sub - np.mean(sub)

    sub = 1 / (1 + np.exp(-np.clip(sub, -500, 500)))

    total = float(np.sum(sub))
    sub = sub / total if total > 0 else np.ones_like(sub) / len(sub)

    out = np.zeros_like(raw_scores, dtype=float)
    out[positive_mask] = sub
    return out


__all__ = ["BidirectionalEmaTracker", "sigmoid_normalized_distribution"]
