from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

from metta.common.util.fs import get_repo_root

_FULL_GIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")


class TrainingCompatTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_path: str = Field(min_length=1)
    metric: str = Field(min_length=1)
    expected_min: float = Field(gt=0)
    topology: str = Field(min_length=1)
    notes: str | None = None


class TrainingCompatRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = Field(min_length=1)
    git_commit: str
    env_compat_version: str = Field(min_length=1)
    notes: str | None = None
    targets: dict[str, TrainingCompatTarget]

    @field_validator("git_commit")
    @classmethod
    def _validate_git_commit(cls, value: str) -> str:
        if not _FULL_GIT_SHA_PATTERN.fullmatch(value):
            raise ValueError("git_commit must be a full 40-character git SHA")
        return value


TRAINING_COMPAT_REGISTRY: dict[str, TrainingCompatRecord] = {
    "1.0": TrainingCompatRecord(
        version="1.0",
        git_commit="6c8f7369e6b6effe114db78d908649c18e8dfd08",
        env_compat_version="0.19",
        notes="Initial training compat baseline, seeded from the current stable SPS acceptance targets.",
        targets={
            "arena_basic_easy_shaped.train_100m": TrainingCompatTarget(
                tool_path="recipes.prod.arena_basic_easy_shaped.train_100m",
                metric="overview/sps",
                expected_min=15_000,
                topology="1xGPU",
                notes="Current single-GPU stable SPS floor.",
            ),
            "arena_basic_easy_shaped.train_2b": TrainingCompatTarget(
                tool_path="recipes.prod.arena_basic_easy_shaped.train_2b",
                metric="overview/sps",
                expected_min=52_000,
                topology="4xGPU",
                notes="Current multi-GPU stable SPS floor.",
            ),
        },
    )
}


def get_training_compat_version() -> str:
    return (get_repo_root() / "TRAINING_COMPAT_VERSION").read_text().strip()


def list_training_compat_versions() -> list[str]:
    return sorted(TRAINING_COMPAT_REGISTRY)


def get_training_compat_record(version: str | None = None) -> TrainingCompatRecord:
    resolved_version = version or get_training_compat_version()
    if not resolved_version:
        raise ValueError("TRAINING_COMPAT_VERSION is empty")
    try:
        return TRAINING_COMPAT_REGISTRY[resolved_version]
    except KeyError as exc:
        available = ", ".join(list_training_compat_versions())
        raise ValueError(f"Unknown training compat version '{resolved_version}'. Available: {available}") from exc


def get_training_compat_target(stable_check_name: str, version: str | None = None) -> TrainingCompatTarget:
    record = get_training_compat_record(version)
    try:
        return record.targets[stable_check_name]
    except KeyError as exc:
        available = ", ".join(sorted(record.targets))
        raise ValueError(
            f"Unknown training compat target '{stable_check_name}' for version {record.version}. Available: {available}"
        ) from exc


def format_training_compat_metric_label(stable_check_name: str, version: str | None = None) -> str:
    record = get_training_compat_record(version)
    target = get_training_compat_target(stable_check_name, version=record.version)
    return (
        f"{target.metric} [{stable_check_name}; training compat {record.version}; "
        f"commit {record.git_commit[:12]}; env compat {record.env_compat_version}; "
        f"expected >= {target.expected_min:g}]"
    )
