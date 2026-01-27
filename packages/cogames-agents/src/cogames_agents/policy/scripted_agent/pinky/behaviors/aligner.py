"""
Aligner behavior for Pinky policy.

Aligners convert neutral junctions to expand cogs territory.
Strategy: Get hearts, target neutral junctions OUTSIDE enemy AOE only.
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


class AlignerBehavior:
    """Aligner agent: convert neutral junctions to cogs."""

    role = Role.ALIGNER
    risk_tolerance = RiskTolerance.MODERATE

    def act(self, state: AgentState, services: Services) -> Action:
        """Execute aligner behavior."""
        # Priority 1: Retreat if unsafe
        if services.safety.should_retreat(state, self.risk_tolerance):
            if DEBUG:
                print(f"[A{state.agent_id}] ALIGNER: Retreating! HP={state.hp}")
            return self._retreat_to_safety(state, services)

        # Priority 2: Get gear if missing
        if self.needs_gear(state):
            return self._get_gear(state, services)

        # Priority 3: Get hearts if empty (needed to align)
        if not self.has_resources_to_act(state):
            return self._get_hearts(state, services)

        # Priority 4: Find and align best target junction
        return self._align_junction(state, services)

    def needs_gear(self, state: AgentState) -> bool:
        """Aligners need aligner gear for +20 influence."""
        return not state.aligner_gear

    def has_resources_to_act(self, state: AgentState) -> bool:
        """Aligners need hearts to align junctions."""
        return state.heart >= 1

    def _retreat_to_safety(self, state: AgentState, services: Services) -> Action:
        """Return to nearest safe zone."""
        safe_pos = services.safety.nearest_safe_zone(state)
        if safe_pos is None:
            return services.navigator.explore(state)
        return services.navigator.move_to(state, safe_pos, reach_adjacent=True)

    def _get_gear(self, state: AgentState, services: Services) -> Action:
        """Get aligner gear from station."""
        station_name = ROLE_TO_STATION[Role.ALIGNER]
        station_pos = state.map.stations.get(station_name)

        if station_pos is None:
            # No gear station found after initial search, proceed without gear
            if state.step > 20:
                # Check if we have hearts and can start aligning
                if self.has_resources_to_act(state):
                    return self._align_junction(state, services)
                return self._get_hearts(state, services)
            if DEBUG:
                print(f"[A{state.agent_id}] ALIGNER: Station not found, exploring")
            return services.navigator.explore(state)

        if is_adjacent(state.pos, station_pos):
            if DEBUG:
                print(f"[A{state.agent_id}] ALIGNER: Getting gear from {station_pos}")
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
                    print(f"[A{state.agent_id}] ALIGNER: No chest/assembler, exploring")
                return services.navigator.explore(state)
            chest_pos = assembler_pos

        if is_adjacent(state.pos, chest_pos):
            if DEBUG:
                print(f"[A{state.agent_id}] ALIGNER: Getting hearts from {chest_pos}")
            return services.navigator.use_object_at(state, chest_pos)

        return services.navigator.move_to(state, chest_pos, reach_adjacent=True)

    def _align_junction(self, state: AgentState, services: Services) -> Action:
        """Find and align a neutral junction."""
        target = self._find_best_target(state, services)

        if target is None:
            if DEBUG and state.step % 50 == 0:
                print(f"[A{state.agent_id}] ALIGNER: No alignable junctions, exploring")
            return services.navigator.explore(state)

        if is_adjacent(state.pos, target.position):
            if DEBUG:
                print(f"[A{state.agent_id}] ALIGNER: Aligning junction at {target.position}")
            return services.navigator.use_object_at(state, target.position)

        return services.navigator.move_to(state, target.position, reach_adjacent=True)

    def _find_best_target(self, state: AgentState, services: Services) -> Optional[StructureInfo]:
        """Find alignable junction - must be neutral AND outside enemy AOE.

        Aligners can ONLY target neutral junctions that are not in enemy AOE.
        """
        max_dist = services.safety.max_safe_distance(state, self.risk_tolerance)

        # Get all enemy junction positions for AOE check
        enemy_junctions = state.map.get_clips_junctions()

        def is_in_enemy_aoe(pos: tuple[int, int]) -> bool:
            return any(manhattan_distance(pos, ej.position) <= JUNCTION_AOE_RANGE for ej in enemy_junctions)

        # Find alignable junctions: neutral AND outside enemy AOE
        alignable: list[tuple[int, StructureInfo]] = []
        for junction in state.map.get_neutral_junctions():
            if is_in_enemy_aoe(junction.position):
                continue  # Can't align - in enemy AOE

            dist = manhattan_distance(state.pos, junction.position)
            if dist <= max_dist:
                alignable.append((dist, junction))

        if not alignable:
            return None

        # Sort by distance
        alignable.sort(key=lambda x: x[0])
        return alignable[0][1]
