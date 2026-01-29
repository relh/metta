"""
Scout behavior for Pinky policy.

Scouts explore the map to discover structures for other roles.
Strategy: Frontier-based exploration, venture deep with +400 HP from gear.
"""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING, Optional

from cogames_agents.policy.scripted_agent.common.roles import ROLE_TO_STATION
from cogames_agents.policy.scripted_agent.pinky.behaviors.base import Services, is_adjacent
from cogames_agents.policy.scripted_agent.pinky.types import DEBUG, RiskTolerance, Role
from mettagrid.simulator import Action

if TYPE_CHECKING:
    from cogames_agents.policy.scripted_agent.pinky.state import AgentState


class ScoutBehavior:
    """Scout agent: explore and discover the map."""

    role = Role.SCOUT
    risk_tolerance = RiskTolerance.AGGRESSIVE

    def act(self, state: AgentState, services: Services) -> Action:
        """Execute scout behavior."""
        # Priority 1: Retreat only if critically low HP (scouts are tanky)
        if state.hp < 50:
            if DEBUG:
                print(f"[A{state.agent_id}] SCOUT: Retreating! HP={state.hp}")
            return self._retreat_to_safety(state, services)

        # Priority 2: Get gear if missing (high priority - +400 HP is huge)
        if self.needs_gear(state):
            return self._get_gear(state, services)

        # Priority 3: Frontier-based exploration
        return self._explore_frontier(state, services)

    def needs_gear(self, state: AgentState) -> bool:
        """Scouts need scout gear for +400 HP."""
        return not state.scout_gear

    def has_resources_to_act(self, state: AgentState) -> bool:
        """Scouts don't need resources to explore."""
        return True

    def _retreat_to_safety(self, state: AgentState, services: Services) -> Action:
        """Return to nearest safe zone."""
        safe_pos = services.safety.nearest_safe_zone(state)
        if safe_pos is None:
            # No safe zone known, just explore
            return services.navigator.explore(state)
        return services.navigator.move_to(state, safe_pos, reach_adjacent=True)

    def _get_gear(self, state: AgentState, services: Services) -> Action:
        """Get scout gear from station."""
        station_name = ROLE_TO_STATION[Role.SCOUT]
        station_pos = state.map.stations.get(station_name)

        if station_pos is None:
            # No gear station found after initial search, proceed without gear
            if state.step > 20:
                return self._explore_frontier(state, services)
            if DEBUG:
                print(f"[A{state.agent_id}] SCOUT: Station not found, exploring")
            return services.navigator.explore(state)

        if is_adjacent(state.pos, station_pos):
            if DEBUG:
                print(f"[A{state.agent_id}] SCOUT: Getting gear from {station_pos}")
            return services.navigator.use_object_at(state, station_pos)

        return services.navigator.move_to(state, station_pos, reach_adjacent=True)

    def _explore_frontier(self, state: AgentState, services: Services) -> Action:
        """Find and move toward nearest unexplored frontier cell."""
        frontier = self._find_nearest_frontier(state)

        if frontier is None:
            # Map fully explored or boxed in - patrol
            if DEBUG and state.step % 50 == 0:
                explored = sum(sum(row) for row in state.map.explored)
                total = state.map.grid_size * state.map.grid_size
                print(f"[A{state.agent_id}] SCOUT: No frontier, explored={explored}/{total}")
            return services.navigator.explore(state)

        return services.navigator.move_to(state, frontier)

    def _find_nearest_frontier(self, state: AgentState) -> Optional[tuple[int, int]]:
        """BFS to find nearest unexplored cell adjacent to explored cell.

        A frontier is an unexplored cell next to an explored cell.
        """
        if not state.map.explored:
            return None

        start = state.pos
        visited: set[tuple[int, int]] = {start}
        queue: deque[tuple[tuple[int, int], Optional[tuple[int, int]]]] = deque()
        queue.append((start, None))

        directions = [(-1, 0), (1, 0), (0, 1), (0, -1)]

        while queue:
            pos, first_step = queue.popleft()
            r, c = pos

            for dr, dc in directions:
                nr, nc = r + dr, c + dc

                # Check bounds
                if not (0 <= nr < state.map.grid_size and 0 <= nc < state.map.grid_size):
                    continue

                if (nr, nc) in visited:
                    continue

                visited.add((nr, nc))

                # Found unexplored cell - this is our frontier target
                if not state.map.explored[nr][nc]:
                    if first_step is None:
                        return (nr, nc)
                    return first_step

                # Continue BFS through explored, free cells
                from cogames_agents.policy.scripted_agent.pinky.types import CellType

                if state.map.occupancy[nr][nc] == CellType.FREE.value:
                    next_first_step = first_step
                    if first_step is None and (r, c) == start:
                        next_first_step = (nr, nc)
                    queue.append(((nr, nc), next_first_step))

        return None
