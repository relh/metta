"""
Learning Progress Algorithm with integrated bidirectional scoring.

Provides intelligent task selection based on bidirectional learning progress analysis,
using fast and slow exponential moving averages to detect learning opportunities.
"""

import zlib
from typing import Any, Dict, List, Optional

import numpy as np

from metta.cogworks.curriculum.progress_tracking import (
    BidirectionalEmaTracker,
    sigmoid_normalized_distribution,
)
from metta.cogworks.curriculum.task_tracker import TaskTracker
from metta.cogworks.curriculum.types import (
    CurriculumAlgorithm,
    CurriculumAlgorithmConfig,
    CurriculumTask,
)

# Constants for bidirectional learning progress
DEFAULT_SUCCESS_RATE = 0.0
DEFAULT_WEIGHT = 1.0
RANDOM_BASELINE_CAP = 0.75


class LearningProgressConfig(CurriculumAlgorithmConfig):
    """Configuration for learning progress with bidirectional scoring as default."""

    type: str = "learning_progress"

    # Bidirectional learning progress settings (now default)
    use_bidirectional: bool = True
    ema_timescale: float = 0.001  # Timescale for fast EMA (sets low-frequency component)
    slow_timescale_factor: float = 0.2  # Factor applied to ema_timescale for slow EMA (width of frequency window)
    exploration_bonus: float = 0.1
    progress_smoothing: float = 0.05  # Prioritization rescaling factor for bidirectional reweighting
    lp_gain: float = 0.1  # Gain factor for performance bonus (z-score gain)

    # Dual-pool sampling (exploration vs exploitation).
    # Implementation note: pool membership is deterministic from task_id to avoid extra state/checkpointing.
    use_dual_pool: bool = False
    exploration_pool_fraction: float = 0.5
    exploration_sampling_fraction: float = 0.25

    # Task distribution and sampling
    rand_task_rate: float = 0.25
    sample_threshold: int = 10
    memory: int = 25

    # Normalization knobs (default values preserve current behavior)
    lp_score_temperature: float = 1.0
    z_score_amplification: float = 1.0
    early_progress_amplification: float = 1.0

    def algorithm_type(self) -> str:
        return "learning_progress"

    @classmethod
    def default(cls) -> "LearningProgressConfig":
        """Default learning progress preset (single-pool, bidirectional)."""
        return cls(
            use_bidirectional=True,
            ema_timescale=0.001,
            slow_timescale_factor=0.2,
            exploration_bonus=0.1,
            progress_smoothing=0.05,
            lp_gain=0.1,
        )

    def create(self, num_tasks: int) -> "LearningProgressAlgorithm":
        return LearningProgressAlgorithm(num_tasks, self)

    @classmethod
    def default_dual_pool(
        cls,
        *,
        exploration_pool_fraction: float = 0.5,
        exploration_sampling_fraction: float = 0.25,
    ) -> "LearningProgressConfig":
        cfg = cls.default()
        cfg.use_dual_pool = True
        cfg.exploration_pool_fraction = exploration_pool_fraction
        cfg.exploration_sampling_fraction = exploration_sampling_fraction
        return cfg


class LearningProgressAlgorithm(CurriculumAlgorithm):
    """
    Learning Progress Algorithm with integrated bidirectional scoring.

    Uses bidirectional learning progress by default, combining fast and slow
    exponential moving averages to detect learning opportunities and guide
    intelligent task selection.
    """

    def __init__(self, num_tasks: int, hypers: LearningProgressConfig):
        super().__init__(num_tasks, hypers)

        self.num_tasks = num_tasks
        self.hypers: LearningProgressConfig = hypers

        # Initialize task tracker; cap memory to the active task pool size.
        self.task_tracker = TaskTracker(max_memory_tasks=num_tasks)

        # Note: slice_analyzer is already initialized in parent class via StatsLogger

        # Initialize shared caches (used by both scoring methods)
        self._score_cache: Dict[int, float] = {}
        self._cache_valid_tasks: set[int] = set()

        # Initialize scoring method (bidirectional by default)
        if hypers.use_bidirectional:
            self._init_bidirectional_scoring()
        else:
            self._init_basic_scoring()

        # Cache for expensive statistics computation
        self._stats_cache: Dict[str, Any] = {}
        self._stats_cache_valid = False

    def get_base_stats(self) -> Dict[str, float]:
        """Get basic statistics that all algorithms must provide."""
        base_stats = {"num_tasks": self.num_tasks, **self.slice_analyzer.get_base_stats()}

        # Add task tracker stats with prefix for test compatibility
        tracker_stats = self.task_tracker.get_global_stats()
        for key, value in tracker_stats.items():
            base_stats[f"tracker/{key}"] = value

        if self.hypers.use_dual_pool:
            base_stats["pool/exploration_pool_fraction"] = float(self.hypers.exploration_pool_fraction)
            base_stats["pool/exploration_sampling_fraction"] = float(self.hypers.exploration_sampling_fraction)

        return base_stats

    def stats(self, prefix: str = "") -> Dict[str, float]:
        """Get all statistics with optional prefix. Always includes learning progress stats."""
        cache_key = prefix if prefix else "_default"

        if self._stats_cache_valid and cache_key in self._stats_cache:
            return self._stats_cache[cache_key]

        # Get base stats (required)
        stats = self.get_base_stats()

        # Always include learning progress stats (not just when detailed logging is enabled)
        if self.hypers.use_bidirectional:
            lp_stats = self._get_bidirectional_detailed_stats()
        else:
            lp_stats = self._get_basic_detailed_stats()

        # Add lp/ prefix to learning progress stats
        for key, value in lp_stats.items():
            stats[f"lp/{key}"] = value

        if self.enable_detailed_logging:
            detailed = self.get_detailed_stats()
            stats.update(detailed)

        # Add prefix to all keys
        if prefix:
            stats = {f"{prefix}{k}": v for k, v in stats.items()}

        # Cache result
        self._stats_cache[cache_key] = stats
        self._stats_cache_valid = True

        return stats

    def _init_bidirectional_scoring(self):
        """Initialize bidirectional EMA tracking (integrated from BidirectionalLearningProgressScorer)."""
        # Bidirectional learning progress tracking
        self._outcomes: Dict[int, List[float]] = {}
        self._counter: Dict[int, int] = {}

        # Per-task EMA dictionaries
        self._per_task_fast: Dict[int, float] = {}
        self._per_task_slow: Dict[int, float] = {}
        self._ema_tracker = BidirectionalEmaTracker(
            fast=self._per_task_fast,
            slow=self._per_task_slow,
            ema_timescale=self.hypers.ema_timescale,
            slow_timescale_factor=self.hypers.slow_timescale_factor,
        )

    def _init_basic_scoring(self):
        """Initialize basic EMA tracking (fallback method)."""
        # EMA tracking for each task: task_id -> (ema_score, ema_squared, num_samples)
        self._task_emas: Dict[int, tuple[float, float, int]] = {}

    def score_tasks(self, task_ids: List[int]) -> Dict[int, float]:
        """Score tasks using the configured method (bidirectional by default)."""
        if self.hypers.use_bidirectional:
            scores = self._score_tasks_bidirectional(task_ids)
        else:
            scores = self._score_tasks_basic(task_ids)

        # Mix in uniform random sampling mass without introducing nondeterminism.
        r = float(getattr(self.hypers, "rand_task_rate", 0.0))
        r = max(0.0, min(1.0, r))
        if r > 0.0 and scores:
            n = len(scores)
            clipped = {tid: max(0.0, float(s)) for tid, s in scores.items()}
            total = float(sum(clipped.values()))
            if total <= 0.0:
                # Fall back to uniform weights; Curriculum will normalize.
                scores = {tid: 1.0 for tid in clipped.keys()}
            else:
                uniform = 1.0 / n
                scores = {tid: (1.0 - r) * (clipped[tid] / total) + r * uniform for tid in clipped.keys()}

        if self.hypers.use_dual_pool:
            scores = self._apply_dual_pool_reweighting(scores)

        return scores

    def _is_exploration_task(self, task_id: int) -> bool:
        # Deterministic pool assignment based on a stable hash of task_id.
        frac = float(self.hypers.exploration_pool_fraction)
        frac = max(0.0, min(1.0, frac))
        threshold = int(frac * 10_000)
        bucket = zlib.crc32(str(task_id).encode("utf-8")) % 10_000
        return bucket < threshold

    def _apply_dual_pool_reweighting(self, scores: Dict[int, float]) -> Dict[int, float]:
        p = float(self.hypers.exploration_sampling_fraction)
        p = max(0.0, min(1.0, p))
        if p <= 0.0 or p >= 1.0 or not scores:
            return scores

        explore_sum = 0.0
        exploit_sum = 0.0
        for task_id, score in scores.items():
            if self._is_exploration_task(task_id):
                explore_sum += max(0.0, float(score))
            else:
                exploit_sum += max(0.0, float(score))

        if explore_sum <= 0.0 or exploit_sum <= 0.0:
            return scores

        # Choose a scale for exploration scores so normalized probability mass matches p.
        # Let exploit_scale = 1.0, explore_scale = s:
        #   p = (s*E) / (s*E + X) => s = p*X / ((1-p)*E)
        explore_scale = (p * exploit_sum) / max((1.0 - p) * explore_sum, 1e-12)

        out: Dict[int, float] = {}
        for task_id, score in scores.items():
            s = float(score)
            if self._is_exploration_task(task_id):
                out[task_id] = s * explore_scale
            else:
                out[task_id] = s
        total = float(sum(max(0.0, v) for v in out.values()))
        if total <= 0.0:
            return scores

        return {task_id: max(0.0, v) / total for task_id, v in out.items()}

    def _score_tasks_bidirectional(self, task_ids: List[int]) -> Dict[int, float]:
        """Score tasks using bidirectional learning progress with per-call normalization.

        Steps:
        1) compute per-task LP (abs gap + perf bonus) with optional smoothing on fast/slow
        2) drop non-progress tasks (lp <= 0) from the normalized mass
        3) standardize remaining scores, apply sigmoid, normalize
        """
        if not task_ids:
            return {}

        raw_scores = np.array([self._get_bidirectional_learning_progress_score(tid) for tid in task_ids], dtype=float)
        norm_scores = self._normalize_bidirectional_scores(raw_scores)
        return {tid: float(score) for tid, score in zip(task_ids, norm_scores, strict=True)}

    def _score_tasks_basic(self, task_ids: List[int]) -> Dict[int, float]:
        """Score tasks using basic EMA variance method."""
        scores = {}
        for task_id in task_ids:
            scores[task_id] = self._get_basic_learning_progress_score(task_id)
        return scores

    def _get_bidirectional_learning_progress_score(self, task_id: int) -> float:
        """Calculate bidirectional learning progress score for a task."""
        # Return cached score if valid
        if task_id in self._cache_valid_tasks and task_id in self._score_cache:
            return self._score_cache[task_id]

        # Check if we have enough data points (use outcomes length, not counter, since outcomes can be trimmed)
        if task_id not in self._per_task_fast or task_id not in self._outcomes or len(self._outcomes[task_id]) < 2:
            score = self.hypers.exploration_bonus
        else:
            fast = self._per_task_fast[task_id]
            slow = self._per_task_slow[task_id]

            # Apply the same progress smoothing used in distribution calc so the
            # bidirectional score honors the config knob.
            if self.hypers.progress_smoothing != 0.0:
                fast = float(self._reweight(fast))
                slow = float(self._reweight(slow))

            # Learning progress = |fast - slow|
            lp = abs(fast - slow)
            # Small bonus for above-baseline performance (controlled by lp_gain)
            perf_bonus = max(fast, 0) * self.hypers.lp_gain
            score = max(lp + perf_bonus, self.hypers.exploration_bonus)

        if task_id in self._outcomes and len(self._outcomes[task_id]) < self.hypers.sample_threshold:
            score *= self.hypers.early_progress_amplification

        # Cache the computed score
        self._score_cache[task_id] = score
        self._cache_valid_tasks.add(task_id)
        return score

    def _get_bidirectional_eviction_score(self, task_id: int) -> float:
        """Eviction-specific score without the exploration floor, so ties favor low-progress tasks."""
        # If we lack history, fall back to exploration bonus (allows eviction of cold tasks if needed)
        if task_id not in self._per_task_fast or task_id not in self._outcomes or len(self._outcomes[task_id]) < 2:
            return self.hypers.exploration_bonus

        fast = self._per_task_fast[task_id]
        slow = self._per_task_slow[task_id]

        if self.hypers.progress_smoothing != 0.0:
            fast = float(self._reweight(fast))
            slow = float(self._reweight(slow))

        lp = abs(fast - slow)
        perf_bonus = max(fast, 0) * self.hypers.lp_gain
        return lp + perf_bonus

    def _get_basic_learning_progress_score(self, task_id: int) -> float:
        """Calculate basic learning progress score using EMA variance."""
        # Return cached score if valid
        if task_id in self._cache_valid_tasks and task_id in self._score_cache:
            return self._score_cache[task_id]

        task_stats = self.task_tracker.get_task_stats(task_id)
        if not task_stats or task_stats["completion_count"] < 2:
            score = self.hypers.exploration_bonus
        elif task_id not in self._task_emas:
            score = self.hypers.exploration_bonus
        else:
            ema_score, ema_squared, num_samples = self._task_emas[task_id]

            # Calculate variance from EMA
            variance = max(0.0, ema_squared - ema_score * ema_score)
            std_dev = np.sqrt(variance)

            # Learning progress is approximated by variance in performance
            learning_progress = std_dev

            # Add exploration bonus for tasks with few samples
            if num_samples < 10:
                learning_progress += self.hypers.exploration_bonus * (10 - num_samples) / 10

            score = learning_progress

        # Cache the computed score
        self._score_cache[task_id] = score
        self._cache_valid_tasks.add(task_id)
        return score

    def recommend_eviction(self, task_ids: List[int]) -> Optional[int]:
        """Recommend which task to evict based on learning progress."""
        if not task_ids:
            return None

        if self.hypers.use_bidirectional:
            scores = {tid: self._get_bidirectional_eviction_score(tid) for tid in task_ids}
        else:
            # Respect basic scorer configuration to avoid missing per-task fields
            scores = {tid: self._get_basic_learning_progress_score(tid) for tid in task_ids}
        return min(task_ids, key=lambda tid: scores.get(tid, 0.0))

    def should_evict_task(self, task_id: int, min_presentations: int = 5) -> bool:
        """Check if a task should be evicted based on criteria."""
        # First check if task has enough presentations
        task_stats = self.task_tracker.get_task_stats(task_id)
        if task_stats is None:
            return False

        if task_stats["completion_count"] < min_presentations:
            return False

        # Check if this task has low learning progress compared to others
        all_task_ids = self.task_tracker.get_all_tracked_tasks()
        if len(all_task_ids) <= 1:
            return False

        scores = self.score_tasks(all_task_ids)
        task_score = scores.get(task_id, 0.0)

        # Evict if this task is in the bottom 40% of learning progress scores
        # This ensures eviction happens more readily with small task pools
        sorted_scores = sorted(scores.values())
        threshold_index = max(0, int(len(sorted_scores) * 0.4))
        threshold_score = sorted_scores[threshold_index] if sorted_scores else 0.0

        return task_score <= threshold_score

    def on_task_evicted(self, task_id: int) -> None:
        """Clean up when a task is evicted."""
        # Remove from task tracker
        self.task_tracker.remove_task(task_id)

        # Learning progress specific cleanup
        self._remove_task_from_scoring(task_id)

        # Invalidate stats cache when task state changes
        self.invalidate_cache()

    def _remove_task_from_scoring(self, task_id: int) -> None:
        """Remove task from scoring system."""
        if self.hypers.use_bidirectional:
            self._outcomes.pop(task_id, None)
            self._counter.pop(task_id, None)
            if hasattr(self, "_ema_tracker"):
                self._ema_tracker.remove(task_id)
            else:
                self._per_task_fast.pop(task_id, None)
                self._per_task_slow.pop(task_id, None)
            self._score_cache.pop(task_id, None)
            self._cache_valid_tasks.discard(task_id)
        else:
            self._task_emas.pop(task_id, None)
            self._score_cache.pop(task_id, None)
            self._cache_valid_tasks.discard(task_id)

    def update_task_performance(self, task_id: int, score: float) -> None:
        """Update task performance using the appropriate scoring method."""
        # Update task tracker
        self.task_tracker.update_task_performance(task_id, score)

        # Update scoring method
        if self.hypers.use_bidirectional:
            self._update_bidirectional_ema(task_id, score)
        else:
            self._update_basic_ema(task_id, score)

        # Invalidate stats cache
        self.invalidate_cache()

    def get_stats(self) -> Dict[str, float]:
        """Get learning progress statistics (compatibility method for tests)."""
        if self.hypers.use_bidirectional:
            return self._get_bidirectional_detailed_stats()
        else:
            return self._get_basic_detailed_stats()

    def update_task_with_slice_values(self, task_id: int, score: float, slice_values: Dict[str, Any]) -> None:
        """Update task performance including slice values for analysis."""
        # First update performance
        self.update_task_performance(task_id, score)

        # Then update slice analyzer
        self.slice_analyzer.update_task_completion(task_id, slice_values, score)

    def _update_bidirectional_ema(self, task_id: int, score: float) -> None:
        """Update bidirectional EMA tracking for a single task."""
        # Normalize score to [0, 1] range for learning progress calculation
        # Note: This assumes rewards are normalized. If rewards are outside [0,1],
        # consider using a different normalization strategy (e.g., sigmoid or min-max scaling)
        success_rate = max(0.0, min(1.0, score))

        # Initialize outcomes for new tasks
        if task_id not in self._outcomes:
            self._outcomes[task_id] = []

        self._outcomes[task_id].append(success_rate)
        self._outcomes[task_id] = self._outcomes[task_id][-self.hypers.memory :]

        if task_id not in self._counter:
            self._counter[task_id] = 0
        self._counter[task_id] += 1

        # === FIX: Update only THIS task's EMAs ===
        baseline = 0.5  # Fixed baseline, not task-dependent
        denominator = max(1.0 - baseline, 0.01)
        normalized = (success_rate - baseline) / denominator

        self._ema_tracker.update(task_id, normalized)

        self._cache_valid_tasks.discard(task_id)

    def _update_basic_ema(self, task_id: int, score: float) -> None:
        """Update basic EMA tracking for a task with new score."""
        if task_id not in self._task_emas:
            self._task_emas[task_id] = (score, score * score, 1)
        else:
            ema_score, ema_squared, num_samples = self._task_emas[task_id]

            # Update EMAs
            alpha = min(1.0, self.hypers.ema_timescale * num_samples)
            new_ema_score = (1 - alpha) * ema_score + alpha * score
            new_ema_squared = (1 - alpha) * ema_squared + alpha * (score * score)

            self._task_emas[task_id] = (new_ema_score, new_ema_squared, num_samples + 1)

        # Invalidate cache for this task when EMA is updated
        self._cache_valid_tasks.discard(task_id)

    def on_task_created(self, task: CurriculumTask) -> None:
        """Handle task creation by tracking it."""
        self.task_tracker.track_task_creation(task._task_id)

        # Extract and update slice values if available
        slice_values = task.get_slice_values()
        if slice_values:
            # Initial tracking with neutral score
            self.slice_analyzer.update_task_completion(task._task_id, slice_values, 0.5)

        # Invalidate stats cache when task state changes
        self.invalidate_cache()

    def get_detailed_stats(self) -> Dict[str, float]:
        """Get detailed stats including slice distribution analysis.

        Note: Learning progress stats are always included in stats() regardless of
        enable_detailed_logging, so they are not included here to avoid duplication.
        """
        # Only return slice analyzer stats (LP stats are always included in stats())
        return super().get_detailed_stats()  # Gets slice analyzer stats

    def _get_bidirectional_detailed_stats(self) -> Dict[str, float]:
        """Get detailed bidirectional learning progress statistics."""
        if not self._outcomes:
            return {
                "num_tracked_tasks": 0.0,
                "mean_task_success_rate": 0.0,
                "mean_learning_progress": 0.0,
            }

        learning_progress_array = self._learning_progress()
        mean_learning_progress = float(np.mean(learning_progress_array)) if len(learning_progress_array) > 0 else 0.0

        return {
            "num_tracked_tasks": float(len(self._outcomes)),
            "mean_task_success_rate": float(
                np.mean([np.mean(vals) if vals else DEFAULT_SUCCESS_RATE for vals in self._outcomes.values()])
            )
            if self._outcomes
            else 0.0,
            "mean_learning_progress": mean_learning_progress,
        }

    def _get_basic_detailed_stats(self) -> Dict[str, float]:
        """Get detailed basic learning progress statistics."""
        if not self._task_emas:
            return {
                "num_tracked_tasks": 0.0,
                "mean_num_samples": 0.0,
                "mean_ema_score": 0.0,
                "mean_learning_progress": 0.0,
            }

        num_samples_list = [num_samples for _, _, num_samples in self._task_emas.values()]
        ema_scores = [ema_score for ema_score, _, _ in self._task_emas.values()]

        # Calculate mean learning progress from EMA data
        learning_progress_scores = []
        for ema_score, ema_squared, _num_samples in self._task_emas.values():
            variance = max(0.0, ema_squared - ema_score * ema_score)
            std_dev = np.sqrt(variance)
            learning_progress_scores.append(std_dev)

        return {
            "num_tracked_tasks": float(len(self._task_emas)),
            "mean_num_samples": float(np.mean(num_samples_list)),
            "mean_ema_score": float(np.mean(ema_scores)),
            "mean_learning_progress": float(np.mean(learning_progress_scores)) if learning_progress_scores else 0.0,
        }

    # Bidirectional learning progress implementation (integrated from modules)
    def _learning_progress(self) -> np.ndarray:
        """Calculate learning progress per task from per-task EMAs (no cached arrays)."""
        if not self._outcomes:
            return np.array([])

        task_ids = sorted(self._outcomes.keys())
        if not task_ids:
            return np.array([])

        fast_list: list[float] = []
        slow_list: list[float] = []
        for task_id in task_ids:
            fast = self._per_task_fast.get(task_id)
            slow = self._per_task_slow.get(task_id)

            if fast is None or slow is None:
                success_vals = self._outcomes.get(task_id, [])
                success_rate = np.mean(success_vals) if success_vals else DEFAULT_SUCCESS_RATE
                baseline = 0.5
                denominator = max(1.0 - baseline, 0.01)
                normalized = (success_rate - baseline) / denominator
                fast = slow = normalized

            if self.hypers.progress_smoothing != 0.0:
                fast = float(self._reweight(fast))
                slow = float(self._reweight(slow))

            fast_list.append(fast)
            slow_list.append(slow)

        fast_arr = np.asarray(fast_list, dtype=float)
        slow_arr = np.asarray(slow_list, dtype=float)

        lp = np.abs(fast_arr - slow_arr)
        performance_bonus = np.maximum(fast_arr, 0) * self.hypers.lp_gain

        return lp + performance_bonus

    def _reweight(self, probs: np.ndarray | float) -> np.ndarray | float:
        """Apply progress smoothing reweighting to probability values."""
        arr = np.asarray(probs, dtype=float)
        smoothing = self.hypers.progress_smoothing
        numerator = arr * (1.0 - smoothing)
        denominator = arr + smoothing * (1.0 - 2.0 * arr)

        # Prevent divide-by-zero or sign flips; mirror distribution behavior.
        denominator = np.where(denominator <= 0, 1.0, denominator)
        result = numerator / denominator

        if arr.ndim == 0:
            return float(result)
        return result

    def _sigmoid(self, x: np.ndarray) -> np.ndarray:
        """Apply sigmoid function to array values with clipping for stability."""
        return 1 / (1 + np.exp(-np.clip(x, -500, 500)))

    def _normalize_bidirectional_scores(self, raw_scores: np.ndarray) -> np.ndarray:
        return sigmoid_normalized_distribution(raw_scores)

    def get_state(self) -> Dict[str, Any]:
        """Get learning progress algorithm state for checkpointing."""
        state = {
            "type": self.hypers.algorithm_type(),
            "hypers": self.hypers.model_dump(),
            "task_tracker": self.task_tracker.get_state(),
        }

        # Save bidirectional scoring state
        if hasattr(self, "_outcomes"):
            state.update(
                {
                    # Deep-copy mutable state to avoid aliasing while training continues
                    "outcomes": {k: list(v) for k, v in self._outcomes.items()},
                    "counter": dict(self._counter),
                    "per_task_fast": dict(self._per_task_fast),
                    "per_task_slow": dict(self._per_task_slow),
                    "score_cache": dict(self._score_cache),
                    "cache_valid_tasks": list(self._cache_valid_tasks),
                }
            )

        return state

    def load_state(self, state: Dict[str, Any]) -> None:
        """Load learning progress algorithm state from checkpoint."""
        # Restore task tracker
        self.task_tracker.load_state(state["task_tracker"])

        # Restore bidirectional scoring state
        if "outcomes" in state:
            self._outcomes = state.get("outcomes", {})
            self._counter = state.get("counter", {})
            self._per_task_fast = state.get("per_task_fast", {})
            self._per_task_slow = state.get("per_task_slow", {})
            self._ema_tracker = BidirectionalEmaTracker(
                fast=self._per_task_fast,
                slow=self._per_task_slow,
                ema_timescale=self.hypers.ema_timescale,
                slow_timescale_factor=self.hypers.slow_timescale_factor,
            )

            # If essential pieces are missing (legacy checkpoint), rebuild LP state from scratch
            if not self._per_task_fast or not self._per_task_slow or not self._outcomes:
                self._outcomes = {}
                self._counter = {}
                self._per_task_fast = {}
                self._per_task_slow = {}

            # Always recompute scores after loading to avoid stale cached values
            self._score_cache = {}
            self._cache_valid_tasks = set()

        # Invalidate stats cache after restoring state
        self._stats_cache_valid = False
