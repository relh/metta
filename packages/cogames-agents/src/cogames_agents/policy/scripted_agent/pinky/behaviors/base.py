"""
Base behavior protocol and Services dataclass for Pinky policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from cogames_agents.policy.scripted_agent.common.geometry import (
    is_adjacent as geometry_is_adjacent,
)
from cogames_agents.policy.scripted_agent.common.geometry import (
    manhattan_distance as geometry_manhattan_distance,
)
from cogames_agents.policy.scripted_agent.pinky.types import RiskTolerance, Role
from cogames_agents.policy.scripted_agent.utils import change_vibe_action as utils_change_vibe_action
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
    return geometry_is_adjacent(pos1, pos2)


def manhattan_distance(pos1: tuple[int, int], pos2: tuple[int, int]) -> int:
    """Calculate Manhattan distance."""
    return geometry_manhattan_distance(pos1, pos2)


def change_vibe_action(vibe_name: str, services: Services) -> Action:
    """Return action to change vibe."""
    return utils_change_vibe_action(vibe_name, action_names=services.action_names)


# Steps to aggressively explore before falling back to navigator
AGGRESSIVE_EXPLORE_STEPS = 50


def explore_for_station(state: AgentState, services: Services, primary_direction: str = "south") -> Action:
    """Explore to find a gear station using proper pathfinding.

    Shared exploration logic for all behaviors:
    - First N steps: aggressively move in primary direction (stations are typically south of spawn)
    - Uses traversability checks to avoid getting stuck on walls
    - Falls back to navigator.explore with direction bias

    Args:
        state: Agent state
        services: Shared services
        primary_direction: Direction to explore first (default "south" since stations are south of spawn)

    Returns:
        Action to explore
    """
    directions = ["south", "east", "west", "north"]

    # First N steps: aggressively move in primary direction, checking traversability
    if state.step < AGGRESSIVE_EXPLORE_STEPS:
        dr, dc = services.navigator.MOVE_DELTAS[primary_direction]
        target_r, target_c = state.row + dr, state.col + dc
        if services.navigator._is_traversable(state, target_r, target_c, allow_unknown=True, check_agents=True):
            return Action(name=f"move_{primary_direction}")
        # Primary direction blocked - try alternatives
        for alt_dir in directions:
            if alt_dir == primary_direction:
                continue
            dr, dc = services.navigator.MOVE_DELTAS[alt_dir]
            if services.navigator._is_traversable(
                state, state.row + dr, state.col + dc, allow_unknown=True, check_agents=True
            ):
                return Action(name=f"move_{alt_dir}")
        # All blocked - use navigator explore
        return services.navigator.explore(state, direction_bias=primary_direction)

    # After aggressive phase, use navigator's explore with direction bias
    return services.navigator.explore(state, direction_bias=primary_direction)


def get_explore_direction_for_agent(agent_id: int) -> str:
    """Get a direction bias for exploration based on agent_id.

    Spreads agents out by giving each one a different primary direction.
    """
    directions = ["south", "east", "west", "north"]
    return directions[agent_id % len(directions)]
