from __future__ import annotations

from enum import Enum


class StableCheckGroup(str, Enum):
    INTERNAL_TRAINING_LIGHT = "internal_training_light"  # These run nightly and during `metta ci`.
    INTERNAL_TRAINING_HEAVY = "internal_training_heavy"  # These run nightly.
    LIVE_TESTS_LIGHT = "live_tests_light"  # These should be made to run every hour and after every release.
    LIVE_TESTS_HEAVY = "live_tests_heavy"  # These should be made to run every hour.
    CLI_HEALTH = "cli_health"  # LLM-driven CLI usability checks; run nightly.
