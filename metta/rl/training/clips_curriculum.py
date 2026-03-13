"""Performance-based clips intensity curriculum for CogsGuard.

This module provides curriculum systems that scale clips intensity based on
agent performance (junction control %).

Two modes are available:
- Linear: Intensity tracks smoothed performance continuously
- Threshold: Intensity advances in steps when mastery is demonstrated
"""

from __future__ import annotations

import random
import uuid
from abc import ABC, abstractmethod
from typing import Literal, Optional

from pydantic import Field

from cogames.games.cogs_vs_clips.game import ClipsVariant
from cogames.games.cogs_vs_clips.game.clips import ClipsConfig
from cogames.games.cogs_vs_clips.game.damage import DamageVariant
from cogames.games.cogs_vs_clips.game.days import DaysVariant
from cogames.games.cogs_vs_clips.missions.arena import make_arena_map_builder
from cogames.games.cogs_vs_clips.missions.machina_1 import make_machina1_map_builder
from cogames.games.cogs_vs_clips.missions.mission import CvCMission
from cogames.games.cogs_vs_clips.train.reward_variants import apply_reward_variants
from metta.cogworks.curriculum.curriculum import (
    Curriculum,
    CurriculumConfig,
    DiscreteRandomConfig,
)
from metta.cogworks.curriculum.task_generator import AnyTaskGeneratorConfig, TaskGenerator, TaskGeneratorConfig
from metta.rl.training.component import TrainerComponent
from mettagrid.config.mettagrid_config import MettaGridConfig

_PERFORMANCE_REGISTRY: dict[str, "PerformanceProgress"] = {}

JUNCTION_HELD_STAT = "env_game/cogs/aligned.junction.held"


class PerformanceProgress(ABC):
    """Base class for tracking agent performance and computing clips intensity.

    Subclasses implement different strategies for mapping performance to intensity.
    All values are in range [0.0, 1.0].
    """

    def __init__(
        self,
        min_intensity: float = 0.0,
        max_intensity: float = 1.0,
        smoothing_window: int = 10,
        monotonic: bool = False,
        registry_id: Optional[str] = None,
    ):
        self._min_intensity = min_intensity
        self._max_intensity = max_intensity
        self._smoothing_window = smoothing_window
        self._monotonic = monotonic
        self._registry_id = registry_id
        self._junction_percentage_history: list[float] = []
        self._max_intensity_seen: float = min_intensity

        if registry_id is not None:
            _PERFORMANCE_REGISTRY[registry_id] = self

    @property
    def junction_percentage(self) -> float:
        """Smoothed junction control percentage [0.0, 1.0]."""
        if not self._junction_percentage_history:
            return 0.0
        return sum(self._junction_percentage_history) / len(self._junction_percentage_history)

    @property
    @abstractmethod
    def intensity(self) -> float:
        """Current clips intensity [0.0, 1.0]."""

    def update(self, junction_percentage: float) -> None:
        """Update with new junction control percentage [0.0, 1.0]."""
        junction_percentage = max(0.0, min(1.0, junction_percentage))
        self._junction_percentage_history.append(junction_percentage)
        if len(self._junction_percentage_history) > self._smoothing_window:
            self._junction_percentage_history.pop(0)
        self._on_update()

    def _on_update(self) -> None:  # noqa: B027
        """Hook for subclasses to perform additional logic after update."""
        pass

    def cleanup(self) -> None:
        if self._registry_id is not None and self._registry_id in _PERFORMANCE_REGISTRY:
            del _PERFORMANCE_REGISTRY[self._registry_id]


class LinearPerformanceProgress(PerformanceProgress):
    """Intensity scales linearly with smoothed junction control percentage.

    0% junction control → min_intensity
    100% junction control → max_intensity

    If monotonic=True, intensity only increases (never decreases).
    """

    @property
    def intensity(self) -> float:
        raw_intensity = self._min_intensity + self.junction_percentage * (self._max_intensity - self._min_intensity)
        if self._monotonic:
            self._max_intensity_seen = max(self._max_intensity_seen, raw_intensity)
            return self._max_intensity_seen
        return raw_intensity


class ThresholdPerformanceProgress(PerformanceProgress):
    """Intensity advances in discrete steps when mastery threshold is maintained.

    Requires agents to control >= mastery_threshold of junctions for
    epochs_to_advance consecutive epochs before intensity increases by intensity_step.

    Note: This mode is inherently monotonic (intensity only increases).
    """

    def __init__(
        self,
        min_intensity: float = 0.0,
        max_intensity: float = 1.0,
        smoothing_window: int = 10,
        monotonic: bool = False,
        mastery_threshold: float = 1.0,
        epochs_to_advance: int = 10,
        intensity_step: float = 0.1,
        registry_id: Optional[str] = None,
    ):
        super().__init__(min_intensity, max_intensity, smoothing_window, monotonic, registry_id)
        self._mastery_threshold = mastery_threshold
        self._epochs_to_advance = epochs_to_advance
        self._intensity_step = intensity_step
        self._current_intensity = min_intensity
        self._consecutive_mastery_epochs = 0

    @property
    def intensity(self) -> float:
        return self._current_intensity

    def _on_update(self) -> None:
        if self.junction_percentage >= self._mastery_threshold:
            self._consecutive_mastery_epochs += 1
            if self._consecutive_mastery_epochs >= self._epochs_to_advance:
                self._current_intensity = min(
                    self._current_intensity + self._intensity_step,
                    self._max_intensity,
                )
                self._consecutive_mastery_epochs = 0
        else:
            self._consecutive_mastery_epochs = 0


class ClipsTaskGenerator(TaskGenerator):
    """Task generator that scales clips intensity based on agent performance."""

    class Config(TaskGeneratorConfig["ClipsTaskGenerator"]):
        mission: CvCMission = Field(description="The base CogsGuard mission")
        performance_registry_id: str = Field(description="ID to look up PerformanceProgress")
        variants: list[str] = Field(
            default_factory=list,
            description="Reward variants to apply (e.g., 'credit', 'milestones')",
        )

    def __init__(self, config: "ClipsTaskGenerator.Config"):
        super().__init__(config)
        self._config: ClipsTaskGenerator.Config = config

    def _generate_task(self, task_id: int, rng: random.Random) -> MettaGridConfig:
        performance = _PERFORMANCE_REGISTRY.get(self._config.performance_registry_id)
        intensity = performance.intensity if performance else 0.0

        mission = self._config.mission.model_copy(deep=True)
        clips_variant = next(
            (v for v in mission._variant_registry._variants.values() if isinstance(v, ClipsVariant)), None
        )
        assert clips_variant is not None and isinstance(clips_variant.clips_config, ClipsConfig), (
            "ClipsVariant must be in mission variants to use clips curriculum"
        )
        clips_variant.clips_config = _scale_clips_intensity(clips_variant.clips_config, intensity)

        env_config = mission.make_env()

        if self._config.variants:
            apply_reward_variants(env_config, variants=self._config.variants)

        env_config.label = f"{env_config.label}.clips_{intensity:.2f}"
        return env_config


def _scale_clips_intensity(clips: ClipsConfig, intensity: float) -> ClipsConfig:
    """Scale clips behavior based on intensity [0.0, 1.0].

    At intensity 0.0: clips are disabled
    At intensity 1.0: clips run at default speed
    Between: intervals are scaled inversely (lower intensity = slower clips)
    """
    if intensity <= 0.0:
        return ClipsConfig(disabled=True)

    scale_factor = 1.0 / max(intensity, 0.01)

    return ClipsConfig(
        disabled=False,
        initial_clips_start=clips.initial_clips_start,
        initial_clips_spots=clips.initial_clips_spots,
        scramble_start=int(clips.scramble_start * scale_factor),
        scramble_interval=int(clips.scramble_interval * scale_factor),
        scramble_radius=clips.scramble_radius,
        align_start=int(clips.align_start * scale_factor),
        align_interval=int(clips.align_interval * scale_factor),
    )


class DynamicCurriculumConfig(CurriculumConfig):
    """CurriculumConfig that generates fresh tasks on each get_task() call."""

    def make(self) -> "DynamicCurriculum":
        return DynamicCurriculum(self)


class DynamicCurriculum(Curriculum):
    """A Curriculum that generates fresh tasks on every get_task() call."""

    def get_task(self):
        return self._create_task()


class ClipsCurriculumConfig(CurriculumConfig):
    """Curriculum config that scales clips intensity based on agent performance.

    Two modes:
    - "linear": Intensity tracks smoothed performance continuously
    - "threshold": Intensity advances in steps when mastery is demonstrated
    """

    layout: Literal["machina_1", "arena"] = Field(default="machina_1")
    mode: str = Field(default="linear", description="'linear' or 'threshold'")
    min_intensity: float = Field(default=0.0)
    max_intensity: float = Field(default=1.0)
    smoothing_window: int = Field(default=10)
    monotonic: bool = Field(default=False, description="If True, intensity only increases (never decreases)")
    mastery_threshold: float = Field(default=1.0)
    epochs_to_advance: int = Field(default=10)
    intensity_step: float = Field(default=0.1)
    variants: list[str] = Field(default_factory=list)

    task_generator: AnyTaskGeneratorConfig = Field(default=None)  # type: ignore
    num_active_tasks: int = Field(default=1)
    algorithm_config: DiscreteRandomConfig = Field(default_factory=DiscreteRandomConfig)

    _registry_id: str = ""
    _performance: Optional[PerformanceProgress] = None
    _mission: Optional[CvCMission] = None

    def model_post_init(self, __context) -> None:
        self._registry_id = f"clips_curriculum_{uuid.uuid4().hex[:8]}"

        if self.layout == "machina_1":
            map_builder = make_machina1_map_builder(8)
            description = "CogsGuard clips curriculum (Machina1 layout)"
        else:
            map_builder = make_arena_map_builder(8)
            description = "CogsGuard clips curriculum (arena layout)"
        mission = CvCMission(
            name="basic",
            description=description,
            map_builder=map_builder,
            num_cogs=8,
            min_cogs=8,
            max_cogs=8,
            max_steps=10000,
        ).with_variants([DamageVariant(), DaysVariant(), ClipsVariant()])
        self._mission = mission

        if self.mode == "linear":
            self._performance = LinearPerformanceProgress(
                min_intensity=self.min_intensity,
                max_intensity=self.max_intensity,
                smoothing_window=self.smoothing_window,
                monotonic=self.monotonic,
                registry_id=self._registry_id,
            )
        elif self.mode == "threshold":
            self._performance = ThresholdPerformanceProgress(
                min_intensity=self.min_intensity,
                max_intensity=self.max_intensity,
                smoothing_window=self.smoothing_window,
                monotonic=self.monotonic,
                mastery_threshold=self.mastery_threshold,
                epochs_to_advance=self.epochs_to_advance,
                intensity_step=self.intensity_step,
                registry_id=self._registry_id,
            )
        else:
            raise ValueError(f"Unknown mode: {self.mode}. Use 'linear' or 'threshold'.")

        object.__setattr__(
            self,
            "task_generator",
            ClipsTaskGenerator.Config(
                mission=self._mission,
                performance_registry_id=self._registry_id,
                variants=self.variants,
            ),
        )

        super().model_post_init(__context)

    def make(self) -> "DynamicCurriculum":
        return DynamicCurriculum(self)

    def get_trainer_components(self) -> list:
        """Return the performance updater component."""
        registry_id = self._registry_id
        assert self._mission is not None
        total_junctions = self._mission.total_junctions
        max_steps = self._mission.max_steps

        class PerformanceUpdater(TrainerComponent):
            def __init__(self):
                super().__init__(epoch_interval=1)

            def on_epoch_end(self, epoch: int) -> None:
                performance = _PERFORMANCE_REGISTRY.get(registry_id)
                if performance is None:
                    return

                stats_reporter = getattr(self.context, "stats_reporter", None)
                if stats_reporter is None:
                    return

                stats = stats_reporter.get_latest_payload()
                if stats is None or JUNCTION_HELD_STAT not in stats:
                    return

                # JUNCTION_HELD_STAT is cumulative junction-steps held during the episode.
                # Normalize by (total_junctions * max_steps) to get a percentage [0, 1].
                # Note: A perfect agent can't reach 100% due to ramp-up time, ~90% is realistic max.
                mean_junctions_held = stats[JUNCTION_HELD_STAT]
                max_possible_held = total_junctions * max_steps
                junction_percentage = mean_junctions_held / max_possible_held
                performance.update(junction_percentage)

                # Log intensity and performance to wandb for debugging
                if stats_reporter.wandb_run is not None:
                    stats_reporter.wandb_run.log(
                        {
                            "curriculum/clips_intensity": performance.intensity,
                            "curriculum/junction_percentage": junction_percentage,
                        },
                        commit=False,
                    )

        return [PerformanceUpdater()]
