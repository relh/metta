from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Optional, Sequence


def normalize_overrides(overrides: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in overrides.items():
        # Support authoring with trainer__lr=... (common in configs) and dot notation.
        out[k.replace("__", ".")] = v
    return out


@dataclass(frozen=True)
class ABVariant:
    name: str
    description: str = ""
    overrides: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)

    def normalized(self) -> "ABVariant":
        return ABVariant(
            name=self.name,
            description=self.description,
            overrides=normalize_overrides(self.overrides),
            tags=list(self.tags),
        )


@dataclass(frozen=True)
class ABExperiment:
    name: str
    tool: Sequence[str]
    variants: Sequence[ABVariant]
    description: str = ""
    runs_per_variant: int = 1
    base_overrides: dict[str, Any] = field(default_factory=dict)
    wandb_project: str | None = None
    wandb_entity: str | None = None
    tags: list[str] = field(default_factory=list)
    group: str | None = None

    def validate(self) -> None:
        if not self.name:
            raise ValueError("experiment.name must be non-empty")
        if not self.tool:
            raise ValueError("experiment.tool must be non-empty")
        if len(self.variants) < 2:
            raise ValueError("experiment must have at least 2 variants")
        if self.runs_per_variant <= 0:
            raise ValueError("runs_per_variant must be > 0")

        names = [v.name for v in self.variants]
        if len(set(names)) != len(names):
            raise ValueError(f"duplicate variant names: {names}")

    def normalized(self) -> "ABExperiment":
        self.validate()
        return ABExperiment(
            name=self.name,
            description=self.description,
            tool=list(self.tool),
            variants=[v.normalized() for v in self.variants],
            runs_per_variant=self.runs_per_variant,
            base_overrides=normalize_overrides(self.base_overrides),
            wandb_project=self.wandb_project,
            wandb_entity=self.wandb_entity,
            tags=list(self.tags),
            group=self.group,
        )


@dataclass(frozen=True)
class ABRun:
    experiment: str
    variant: str
    index: int
    run_id: str
    args: list[str]


def default_group_name(experiment_name: str, *, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return f"ab.{experiment_name}.{now.strftime('%Y%m%d')}"


def materialize_runs(
    experiment: ABExperiment,
    *,
    now: datetime | None = None,
) -> list[ABRun]:
    exp = experiment.normalized()
    group = exp.group or default_group_name(exp.name, now=now)

    base_args: dict[str, Any] = dict(exp.base_overrides)
    base_args["group"] = group
    if exp.wandb_project is not None:
        base_args["wandb.project"] = exp.wandb_project
    if exp.wandb_entity is not None:
        base_args["wandb.entity"] = exp.wandb_entity

    # Stable tags across the whole experiment; add variant-scoped tags per run.
    base_tags = list(exp.tags)

    runs: list[ABRun] = []
    for variant in exp.variants:
        for i in range(exp.runs_per_variant):
            run_id = f"{group}.{variant.name}.{i}"
            merged: dict[str, Any] = dict(base_args)
            merged["run"] = run_id
            merged.update(variant.overrides)
            merged_tags = base_tags + list(variant.tags)
            override_tags = merged.get("wandb.tags", [])
            if not isinstance(override_tags, list):
                raise TypeError(f"wandb.tags override must be a list[str], got {type(override_tags).__name__}")
            merged_tags.extend(override_tags)
            merged_tags.append(f"ab_variant:{variant.name}")
            merged["wandb.tags"] = list(dict.fromkeys(merged_tags))

            # Keep deterministic ordering for readability and testability.
            import json  # noqa: PLC0415

            args = [
                f"{k}={json.dumps(merged[k]) if isinstance(merged[k], (dict, list)) else merged[k]}"
                for k in sorted(merged)
            ]
            runs.append(
                ABRun(
                    experiment=exp.name,
                    variant=variant.name,
                    index=i,
                    run_id=run_id,
                    args=args,
                )
            )
    return runs


class ABExperimentBuilder:
    def __init__(self, *, name: str, tool: Sequence[str], description: str = "") -> None:
        self._name = name
        self._tool = list(tool)
        self._description = description
        self._variants: list[ABVariant] = []
        self._runs_per_variant = 1
        self._base_overrides: dict[str, Any] = {}
        self._wandb_project: str | None = None
        self._wandb_entity: str | None = None
        self._tags: list[str] = []
        self._group: str | None = None

    def add_variant(
        self,
        *,
        name: str,
        description: str = "",
        tags: Optional[Iterable[str]] = None,
        **overrides: Any,
    ) -> "ABExperimentBuilder":
        self._variants.append(
            ABVariant(
                name=name,
                description=description,
                overrides=dict(overrides),
                tags=list(tags) if tags is not None else [],
            )
        )
        return self

    def set_runs_per_variant(self, runs_per_variant: int) -> "ABExperimentBuilder":
        self._runs_per_variant = runs_per_variant
        return self

    def set_base_overrides(self, **overrides: Any) -> "ABExperimentBuilder":
        self._base_overrides.update(overrides)
        return self

    def set_wandb(
        self,
        *,
        project: str | None = None,
        entity: str | None = None,
        tags: Sequence[str] | None = None,
    ) -> "ABExperimentBuilder":
        self._wandb_project = project
        self._wandb_entity = entity
        if tags is not None:
            self._tags = list(tags)
        return self

    def set_group(self, group: str | None) -> "ABExperimentBuilder":
        self._group = group
        return self

    def build(self) -> ABExperiment:
        exp = ABExperiment(
            name=self._name,
            description=self._description,
            tool=self._tool,
            variants=list(self._variants),
            runs_per_variant=self._runs_per_variant,
            base_overrides=dict(self._base_overrides),
            wandb_project=self._wandb_project,
            wandb_entity=self._wandb_entity,
            tags=list(self._tags),
            group=self._group,
        )
        exp.validate()
        return exp


def create_experiment(*, name: str, tool: str | Sequence[str], description: str = "") -> ABExperimentBuilder:
    if isinstance(tool, str):
        tool_tokens = tool.split()
    else:
        tool_tokens = list(tool)
    return ABExperimentBuilder(name=name, tool=tool_tokens, description=description)
