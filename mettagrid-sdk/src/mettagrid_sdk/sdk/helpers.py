from __future__ import annotations

from collections import Counter
from typing import Protocol, runtime_checkable

from pydantic import BaseModel

from mettagrid_sdk.sdk.state import MettagridState


class HelperCapability(BaseModel):
    name: str
    description: str


class HelperCatalog:
    def __init__(self, capabilities: list[HelperCapability]) -> None:
        self._capabilities = capabilities

    def list_capabilities(self) -> list[HelperCapability]:
        return list(self._capabilities)

    def render_capability_summary(self, max_items: int | None = None) -> str:
        capabilities = self.list_capabilities()
        if max_items is not None:
            capabilities = capabilities[:max_items]
        if not capabilities:
            return "none"
        return "\n".join(f"- {item.name}: {item.description}" for item in capabilities)


class StateHelperCatalog(HelperCatalog):
    def __init__(self, state: MettagridState, capabilities: list[HelperCapability] | None = None) -> None:
        super().__init__(
            capabilities
            if capabilities is not None
            else [
                HelperCapability(name="agent_id", description="Return the current agent id."),
                HelperCapability(name="shared_inventory", description="Return the current team shared inventory."),
                HelperCapability(name="shared_objectives", description="Return the current team shared objectives."),
                HelperCapability(
                    name="current_objectives",
                    description="Return the current team shared objectives as the active objective list.",
                ),
                HelperCapability(
                    name="objective_values",
                    description="Return objective suffix values for tags matching a given prefix.",
                ),
                HelperCapability(
                    name="seen_resources",
                    description="Return resource names recorded in seen_resource:* shared objectives.",
                ),
                HelperCapability(
                    name="missing_resources",
                    description="Return resource names recorded in missing_resource:* shared objectives.",
                ),
                HelperCapability(
                    name="self_attribute",
                    description="Return an attribute from sdk.state.self_state.attributes with an optional default.",
                ),
                HelperCapability(name="position", description="Return the current semantic (x, y) position."),
                HelperCapability(
                    name="visible_entity_counts",
                    description="Return counts of visible semantic entities by entity_type.",
                ),
                HelperCapability(
                    name="recent_event_types",
                    description="Return recent semantic event types in order of appearance this step window.",
                ),
            ]
        )
        self._state = state

    def agent_id(self) -> int:
        return int(self._state.self_state.attributes.get("agent_id", 0))

    def shared_inventory(self) -> dict[str, int]:
        if self._state.team_summary is None:
            return {}
        return dict(self._state.team_summary.shared_inventory)

    def shared_objectives(self) -> list[str]:
        if self._state.team_summary is None:
            return []
        return list(self._state.team_summary.shared_objectives)

    def current_objectives(self) -> list[str]:
        return self.shared_objectives()

    def objective_values(self, prefix: str) -> list[str]:
        prefix_tag = f"{prefix}:"
        return [
            objective.removeprefix(prefix_tag)
            for objective in self.shared_objectives()
            if objective.startswith(prefix_tag)
        ]

    def seen_resources(self) -> list[str]:
        return self.objective_values("seen_resource")

    def missing_resources(self) -> list[str]:
        return self.objective_values("missing_resource")

    def self_attribute(
        self,
        name: str,
        default: str | int | float | bool | None = None,
    ) -> str | int | float | bool | None:
        return self._state.self_state.attributes.get(name, default)

    def position(self) -> tuple[int, int]:
        return (self._state.self_state.position.x, self._state.self_state.position.y)

    def visible_entity_counts(self) -> dict[str, int]:
        counts = Counter(entity.entity_type for entity in self._state.visible_entities)
        return dict(sorted(counts.items()))

    def recent_event_types(self) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for event in self._state.recent_events:
            if event.event_type in seen:
                continue
            seen.add(event.event_type)
            ordered.append(event.event_type)
        return ordered


@runtime_checkable
class MettagridHelpers(Protocol):
    def list_capabilities(self) -> list[HelperCapability]: ...
    def render_capability_summary(self, max_items: int | None = None) -> str: ...
    def agent_id(self) -> int: ...
    def shared_inventory(self) -> dict[str, int]: ...
    def shared_objectives(self) -> list[str]: ...
    def current_objectives(self) -> list[str]: ...
    def objective_values(self, prefix: str) -> list[str]: ...
    def seen_resources(self) -> list[str]: ...
    def missing_resources(self) -> list[str]: ...
    def position(self) -> tuple[int, int]: ...
    def visible_entity_counts(self) -> dict[str, int]: ...
    def recent_event_types(self) -> list[str]: ...
    def self_attribute(
        self,
        name: str,
        default: str | int | float | bool | None = None,
    ) -> str | int | float | bool | None: ...
