"""
Scrambler behavior for Pinky policy.

Scramblers raid enemy junctions to neutralize them, enabling aligners.
Strategy: Get hearts, target enemy junctions that block neutral territory.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from cogames_agents.policy.scripted_agent.pinky.behaviors.base import Services, is_adjacent, manhattan_distance
from cogames_agents.policy.scripted_agent.pinky.types import (
    DEBUG,
    JUNCTION_AOE_RANGE,
    ROLE_TO_STATION,
    RiskTolerance,
    Role,
    StructureInfo,
)
from mettagrid.simulator import Action

if TYPE_CHECKING:
    from cogames_agents.policy.scripted_agent.pinky.state import AgentState


class ScramblerBehavior:
    """Scrambler agent: neutralize enemy junctions."""

    role = Role.SCRAMBLER
    risk_tolerance = RiskTolerance.AGGRESSIVE

    def act(self, state: AgentState, services: Services) -> Action:
        """Execute scrambler behavior."""
        # Priority 1: Retreat only if critically low (scramblers are tanky)
        # Only retreat when HP drops below 30 (they start with 50)
        if state.hp < 30:
            if DEBUG:
                print(f"[A{state.agent_id}] SCRAMBLER: Retreating! HP={state.hp}")
            return self._retreat_to_safety(state, services)

        # Priority 2: Get gear if missing (+200 HP essential for raids)
        if self.needs_gear(state):
            return self._get_gear(state, services)

        # Priority 3: Get hearts if empty (needed to scramble)
        if not self.has_resources_to_act(state):
            return self._get_hearts(state, services)

        # Priority 4: Raid enemy junctions
        return self._scramble_junction(state, services)

    def needs_gear(self, state: AgentState) -> bool:
        """Scramblers need scrambler gear for +200 HP."""
        return not state.scrambler_gear

    def has_resources_to_act(self, state: AgentState) -> bool:
        """Scramblers need hearts to scramble junctions."""
        return state.heart >= 1

    def _retreat_to_safety(self, state: AgentState, services: Services) -> Action:
        """Return to nearest safe zone."""
        safe_pos = services.safety.nearest_safe_zone(state)
        if safe_pos is None:
            return services.navigator.explore(state)
        return services.navigator.move_to(state, safe_pos, reach_adjacent=True)

    def _get_gear(self, state: AgentState, services: Services) -> Action:
        """Get scrambler gear from station."""
        station_name = ROLE_TO_STATION[Role.SCRAMBLER]
        station_pos = state.map.stations.get(station_name)

        if station_pos is None:
            # No gear station found after initial search, proceed without gear
            if state.step > 20:
                # Check if we have hearts and can start scrambling
                if self.has_resources_to_act(state):
                    return self._scramble_junction(state, services)
                return self._get_hearts(state, services)
            if DEBUG:
                print(f"[A{state.agent_id}] SCRAMBLER: Station not found, exploring")
            return services.navigator.explore(state)

        if is_adjacent(state.pos, station_pos):
            if DEBUG:
                print(f"[A{state.agent_id}] SCRAMBLER: Getting gear from {station_pos}")
            return services.navigator.use_object_at(state, station_pos)

        return services.navigator.move_to(state, station_pos, reach_adjacent=True)

    def _get_hearts(self, state: AgentState, services: Services) -> Action:
        """Get hearts from chest."""
        chest_pos = state.map.stations.get("chest")

        if chest_pos is None:
            # Try assembler as fallback
            assembler_pos = state.map.stations.get("assembler")
            if assembler_pos is None:
                if DEBUG:
                    print(f"[A{state.agent_id}] SCRAMBLER: No chest/assembler, exploring")
                return services.navigator.explore(state)
            chest_pos = assembler_pos

        if is_adjacent(state.pos, chest_pos):
            if DEBUG:
                print(f"[A{state.agent_id}] SCRAMBLER: Getting hearts from {chest_pos}")
            return services.navigator.use_object_at(state, chest_pos)

        return services.navigator.move_to(state, chest_pos, reach_adjacent=True)

    def _scramble_junction(self, state: AgentState, services: Services) -> Action:
        """Find and scramble an enemy junction."""
        target = self._find_best_target(state, services)

        if target is None:
            if DEBUG and state.step % 50 == 0:
                print(f"[A{state.agent_id}] SCRAMBLER: No enemy junctions, exploring")
            return services.navigator.explore(state)

        if is_adjacent(state.pos, target.position):
            if DEBUG:
                print(f"[A{state.agent_id}] SCRAMBLER: Scrambling junction at {target.position}")
            return services.navigator.use_object_at(state, target.position)

        return services.navigator.move_to(state, target.position, reach_adjacent=True)

    def _find_best_target(self, state: AgentState, services: Services) -> Optional[StructureInfo]:
        """Find enemy junction to scramble.

        Prioritizes junctions that are blocking neutral territory
        (i.e., junctions whose AOE covers neutral junctions).
        """
        max_dist = services.safety.max_safe_distance(state, self.risk_tolerance)

        enemy_junctions = state.map.get_clips_junctions()
        neutral_junctions = state.map.get_neutral_junctions()

        if not enemy_junctions:
            return None

        # Score each enemy junction by how many neutrals it blocks
        scored: list[tuple[int, int, StructureInfo]] = []  # (blocked_count, dist, junction)

        for enemy in enemy_junctions:
            dist = manhattan_distance(state.pos, enemy.position)
            if dist > max_dist:
                continue

            # Count how many neutral junctions this enemy is blocking
            blocked = sum(
                1
                for neutral in neutral_junctions
                if manhattan_distance(enemy.position, neutral.position) <= JUNCTION_AOE_RANGE
            )

            scored.append((blocked, dist, enemy))

        if not scored:
            return None

        # Sort by: most blocked neutrals first, then by distance
        scored.sort(key=lambda x: (-x[0], x[1]))
        return scored[0][2]
