"""
Base behavior protocol and Services dataclass for Pinky policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from cogames_agents.policy.scripted_agent.pinky.types import RiskTolerance, Role
from mettagrid.simulator import Action

if TYPE_CHECKING:
    from cogames_agents.policy.scripted_agent.pinky.services import MapTracker, Navigator, SafetyManager
    from cogames_agents.policy.scripted_agent.pinky.state import AgentState


@dataclass
class Services:
    """Bundle of shared services passed to behaviors."""

    navigator: Navigator
    map_tracker: MapTracker
    safety: SafetyManager
    action_names: list[str]  # List of action names for vibe changes


class RoleBehavior(Protocol):
    """Interface for role-specific decision making."""

    role: Role
    risk_tolerance: RiskTolerance

    def act(self, state: AgentState, services: Services) -> Action:
        """Decide what action to take this step."""
        ...

    def needs_gear(self, state: AgentState) -> bool:
        """Does this role need to acquire gear?"""
        ...

    def has_resources_to_act(self, state: AgentState) -> bool:
        """Does agent have resources needed for role actions?"""
        ...


def is_adjacent(pos1: tuple[int, int], pos2: tuple[int, int]) -> bool:
    """Check if two positions are adjacent (4-way)."""
    dr = abs(pos1[0] - pos2[0])
    dc = abs(pos1[1] - pos2[1])
    return (dr == 1 and dc == 0) or (dr == 0 and dc == 1)


def manhattan_distance(pos1: tuple[int, int], pos2: tuple[int, int]) -> int:
    """Calculate Manhattan distance."""
    return abs(pos1[0] - pos2[0]) + abs(pos1[1] - pos2[1])


def change_vibe_action(vibe_name: str, services: Services) -> Action:
    """Return action to change vibe."""
    change_vibe_actions = [a for a in services.action_names if a.startswith("change_vibe_")]
    if len(change_vibe_actions) <= 1:
        return Action(name="noop")
    return Action(name=f"change_vibe_{vibe_name}")
