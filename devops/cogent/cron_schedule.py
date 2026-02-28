"""Cogent scheduled jobs — typed definitions for what the poller should run.

Add jobs to JOBS below. The poller reads this file on every tick.
"""

from enum import Enum

from pydantic import BaseModel, model_validator
from typing_extensions import Self


class Frequency(str, Enum):
    once = "once"
    minutes = "minutes"
    hourly = "hourly"
    daily = "daily"
    weekdays = "weekdays"


class Schedule(BaseModel):
    """When a job should run.

    - once: run once, then never again (poller tracks completed jobs)
    - minutes: run every `interval` minutes
    - hourly: run once per hour at minute `at_minute`
    - daily: run once per day at `at_hour`:`at_minute` UTC
    - weekdays: run Mon-Fri at `at_hour`:`at_minute` UTC
    """

    frequency: Frequency
    interval: int | None = None
    at_hour: int | None = None
    at_minute: int = 0

    @model_validator(mode="after")
    def _validate_fields(self) -> Self:
        if self.frequency == Frequency.minutes:
            assert self.interval is not None and self.interval > 0, "minutes frequency requires interval > 0"
        if self.frequency in (Frequency.daily, Frequency.weekdays):
            assert self.at_hour is not None, f"{self.frequency} requires at_hour"
        return self

    @staticmethod
    def once() -> "Schedule":
        return Schedule(frequency=Frequency.once)

    @staticmethod
    def every(minutes: int) -> "Schedule":
        return Schedule(frequency=Frequency.minutes, interval=minutes)

    @staticmethod
    def hourly(at_minute: int = 0) -> "Schedule":
        return Schedule(frequency=Frequency.hourly, at_minute=at_minute)

    @staticmethod
    def daily(hour: int, minute: int = 0) -> "Schedule":
        return Schedule(frequency=Frequency.daily, at_hour=hour, at_minute=minute)

    @staticmethod
    def weekdays(hour: int, minute: int = 0) -> "Schedule":
        return Schedule(frequency=Frequency.weekdays, at_hour=hour, at_minute=minute)


class Action(str, Enum):
    """What the poller does when a job fires."""

    skill = "skill"
    prompt = "prompt"
    sync = "sync"


_DEFAULT_SCHEDULE = Schedule(frequency=Frequency.once)


class Job(BaseModel):
    """A scheduled job definition.

    At least one of `skill` or `prompt` is required (unless action is sync).
    Both can be provided together — skill content is sent first, prompt is appended.
    `branch` is always required — the writer must specify which branch to operate on.
    """

    name: str
    schedule: Schedule = _DEFAULT_SCHEDULE
    branch: str
    action: Action = Action.skill
    skill: str | None = None
    prompt: str | None = None
    timeout_minutes: int = 60
    agent: str = "codex"
    enabled: bool = True

    @model_validator(mode="after")
    def _validate_action(self) -> Self:
        if self.action == Action.sync:
            return self
        if self.action == Action.skill and not self.skill:
            raise ValueError("skill action requires 'skill' field")
        if self.action == Action.prompt and not self.prompt:
            raise ValueError("prompt action requires 'prompt' field")
        if not self.skill and not self.prompt:
            raise ValueError("at least one of skill or prompt is required")
        if self.agent not in ("claude", "codex"):
            raise ValueError(f"agent must be 'claude' or 'codex', got '{self.agent}'")
        return self


# ---------------------------------------------------------------------------
# Job definitions — edit this list to change what the cogent instance runs.
# The poller reads JOBS on every tick.
# ---------------------------------------------------------------------------

JOBS: list[Job] = [
    Job(
        name="sync-repos",
        schedule=Schedule.every(minutes=5),
        branch="main",
        action=Action.sync,
    ),
    Job(
        name="review-main",
        schedule=Schedule.weekdays(hour=9),
        branch="main",
        skill="cb.review-main",
    ),
]
