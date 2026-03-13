"""Tests for clips curriculum performance tracking and intensity scaling."""

import pytest

from cogames.games.cogs_vs_clips.game.clips import ClipsConfig
from metta.rl.training.clips_curriculum import (
    LinearPerformanceProgress,
    ThresholdPerformanceProgress,
    _scale_clips_intensity,
)


class TestLinearPerformanceProgress:
    """Tests for linear (continuous) intensity scaling."""

    def test_initial_state(self):
        """Initial intensity should be min_intensity when no updates."""
        progress = LinearPerformanceProgress(min_intensity=0.0, max_intensity=1.0)
        assert progress.junction_percentage == 0.0
        assert progress.intensity == 0.0

    def test_linear_scaling(self):
        """Intensity should scale linearly with junction_percentage."""
        progress = LinearPerformanceProgress(min_intensity=0.0, max_intensity=1.0)

        progress.update(0.5)
        assert progress.junction_percentage == 0.5
        assert progress.intensity == 0.5

        progress.update(1.0)
        # With smoothing_window=10, avg of [0.5, 1.0] = 0.75
        assert progress.junction_percentage == 0.75
        assert progress.intensity == 0.75

    def test_custom_intensity_range(self):
        """Intensity should map to custom min/max range."""
        progress = LinearPerformanceProgress(min_intensity=0.2, max_intensity=0.8)

        progress.update(0.0)
        assert progress.intensity == 0.2  # min

        progress.update(1.0)
        # avg of [0.0, 1.0] = 0.5 → 0.2 + 0.5 * (0.8 - 0.2) = 0.5
        assert progress.intensity == 0.5

    def test_smoothing_window(self):
        """Junction percentage should be averaged over smoothing window."""
        progress = LinearPerformanceProgress(smoothing_window=3)

        progress.update(0.3)
        progress.update(0.6)
        progress.update(0.9)
        assert progress.junction_percentage == pytest.approx(0.6)  # avg of [0.3, 0.6, 0.9]

        progress.update(0.9)  # pushes out 0.3
        assert progress.junction_percentage == pytest.approx(0.8)  # avg of [0.6, 0.9, 0.9]

    def test_clamps_input(self):
        """Input junction_percentage should be clamped to [0, 1]."""
        progress = LinearPerformanceProgress()

        progress.update(-0.5)
        assert progress.junction_percentage == 0.0

        progress.update(1.5)
        # avg of [0.0, 1.0] = 0.5
        assert progress.junction_percentage == 0.5


class TestThresholdPerformanceProgress:
    """Tests for threshold (step-based) intensity scaling."""

    def test_initial_state(self):
        """Initial intensity should be min_intensity."""
        progress = ThresholdPerformanceProgress(min_intensity=0.1, max_intensity=1.0)
        assert progress.intensity == 0.1

    def test_no_advance_below_threshold(self):
        """Intensity should not advance when below mastery threshold."""
        progress = ThresholdPerformanceProgress(
            mastery_threshold=1.0,
            epochs_to_advance=3,
            intensity_step=0.1,
        )

        for _ in range(10):
            progress.update(0.9)  # Below threshold

        assert progress.intensity == 0.0  # Still at min

    def test_advance_after_consecutive_epochs(self):
        """Intensity should advance after consecutive epochs at mastery."""
        progress = ThresholdPerformanceProgress(
            min_intensity=0.0,
            max_intensity=1.0,
            smoothing_window=1,  # No smoothing for simpler test
            mastery_threshold=1.0,
            epochs_to_advance=3,
            intensity_step=0.2,
        )

        # First 2 epochs at mastery - no advance yet
        progress.update(1.0)
        progress.update(1.0)
        assert progress.intensity == 0.0

        # Third epoch triggers advance
        progress.update(1.0)
        assert progress.intensity == 0.2

        # Next 3 epochs trigger another advance
        progress.update(1.0)
        progress.update(1.0)
        progress.update(1.0)
        assert progress.intensity == 0.4

    def test_reset_on_drop(self):
        """Counter should reset when performance drops below threshold."""
        progress = ThresholdPerformanceProgress(
            smoothing_window=1,
            mastery_threshold=1.0,
            epochs_to_advance=3,
            intensity_step=0.1,
        )

        progress.update(1.0)
        progress.update(1.0)
        # Would advance on next, but we drop
        progress.update(0.5)
        progress.update(1.0)
        progress.update(1.0)
        # Still need one more
        assert progress.intensity == 0.0

        progress.update(1.0)
        assert progress.intensity == 0.1

    def test_caps_at_max_intensity(self):
        """Intensity should not exceed max_intensity."""
        progress = ThresholdPerformanceProgress(
            min_intensity=0.0,
            max_intensity=0.25,
            smoothing_window=1,
            mastery_threshold=1.0,
            epochs_to_advance=1,
            intensity_step=0.1,
        )

        for _ in range(10):
            progress.update(1.0)

        assert progress.intensity == 0.25  # Capped at max


class TestScaleClipsIntensity:
    """Tests for _scale_clips_intensity function."""

    def test_zero_intensity_disables_clips(self):
        """Intensity 0 should disable clips."""
        clips = ClipsConfig()
        scaled = _scale_clips_intensity(clips, 0.0)
        assert scaled.disabled is True

    def test_full_intensity_unchanged(self):
        """Intensity 1.0 should keep default intervals."""
        clips = ClipsConfig(
            scramble_interval=100,
            align_interval=100,
        )
        scaled = _scale_clips_intensity(clips, 1.0)

        assert scaled.disabled is False
        assert scaled.scramble_interval == 100
        assert scaled.align_interval == 100

    def test_half_intensity_doubles_intervals(self):
        """Intensity 0.5 should double intervals (slower clips)."""
        clips = ClipsConfig(
            scramble_interval=100,
            align_interval=100,
            scramble_start=50,
            align_start=100,
        )
        scaled = _scale_clips_intensity(clips, 0.5)

        assert scaled.disabled is False
        assert scaled.scramble_interval == 200
        assert scaled.align_interval == 200
        assert scaled.scramble_start == 100
        assert scaled.align_start == 200

    def test_preserves_non_scaled_fields(self):
        """Radius and initial spots should not be scaled."""
        clips = ClipsConfig(
            initial_clips_start=10,
            initial_clips_spots=2,
            scramble_radius=25,
        )
        scaled = _scale_clips_intensity(clips, 0.5)

        assert scaled.initial_clips_start == 10
        assert scaled.initial_clips_spots == 2
        assert scaled.scramble_radius == 25


class TestMetricScaling:
    """Tests for the metric scaling math used in the updater."""

    def test_full_junction_control(self):
        """Holding all junctions for full episode should give 100%."""
        total_junctions = 118
        max_steps = 10000

        # Cumulative stat: 118 junctions * 10000 steps
        cumulative_stat = total_junctions * max_steps

        avg_junctions_held = cumulative_stat / max_steps
        junction_percentage = avg_junctions_held / total_junctions

        assert junction_percentage == pytest.approx(1.0)

    def test_half_junction_control(self):
        """Holding half the junctions should give 50%."""
        total_junctions = 118
        max_steps = 10000

        # Holding 59 junctions for all steps
        cumulative_stat = 59 * max_steps

        avg_junctions_held = cumulative_stat / max_steps
        junction_percentage = avg_junctions_held / total_junctions

        assert junction_percentage == pytest.approx(0.5, rel=0.01)

    def test_partial_episode_control(self):
        """Holding all junctions for half the episode should give 50%."""
        total_junctions = 118
        max_steps = 10000

        # Holding 118 junctions for 5000 steps, then 0
        cumulative_stat = total_junctions * 5000

        avg_junctions_held = cumulative_stat / max_steps
        junction_percentage = avg_junctions_held / total_junctions

        assert junction_percentage == pytest.approx(0.5)
