"""
SafetyManager service for Pinky policy.

Manages HP/energy awareness and risk assessment.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from cogames_agents.policy.scripted_agent.pinky.types import (
    HP_DRAIN_NEAR_ENEMY,
    HP_DRAIN_OUTSIDE_SAFE_ZONE,
    HP_SAFETY_MARGIN,
    JUNCTION_AOE_RANGE,
    RiskTolerance,
)

if TYPE_CHECKING:
    from cogames_agents.policy.scripted_agent.pinky.state import AgentState


class SafetyManager:
    """Manages risk based on HP, energy, and territory."""

    # HP thresholds for retreat by risk tolerance
    # These define the HP buffer to keep when calculating safe range
    RETREAT_THRESHOLDS = {
        RiskTolerance.CONSERVATIVE: 40,  # Miners keep 40 HP buffer for safety
        RiskTolerance.MODERATE: 30,  # Aligners keep 30 HP buffer
        RiskTolerance.AGGRESSIVE: 20,  # Scouts/Scramblers are bold, keep 20 HP
    }

    def should_retreat(self, state: AgentState, risk: RiskTolerance) -> bool:
        """Check if agent should retreat to safety based on HP and risk tolerance.

        Returns True if HP is low enough that we need to head back now.
        """
        # If we're already in a safe zone, no need to retreat
        if self.is_in_safe_zone(state):
            return False

        # If no safe zones discovered yet, don't retreat - we need to explore first
        # (unless HP is critically low)
        safe_pos = self.nearest_safe_zone(state)
        if safe_pos is None:
            # Critical HP threshold - retreat even without known safe zone
            return state.hp <= 20

        # Calculate steps to nearest safe zone
        steps_to_safety = self._steps_to_nearest_safe_zone(state)
        drain_rate = self._get_hp_drain_rate(state)

        # HP needed to survive the trip
        hp_needed = (steps_to_safety * drain_rate) + HP_SAFETY_MARGIN

        return state.hp <= hp_needed

    def is_in_safe_zone(self, state: AgentState) -> bool:
        """Check if agent is within AOE of any cogs-aligned junction or assembler."""
        # Check assembler
        assembler_pos = state.map.stations.get("assembler")
        if assembler_pos:
            dist = abs(state.row - assembler_pos[0]) + abs(state.col - assembler_pos[1])
            if dist <= JUNCTION_AOE_RANGE:
                return True

        # Check cogs junctions
        for junction in state.map.get_cogs_junctions():
            dist = abs(state.row - junction.position[0]) + abs(state.col - junction.position[1])
            if dist <= JUNCTION_AOE_RANGE:
                return True

        return False

    def is_in_danger_zone(self, state: AgentState) -> bool:
        """Check if agent is within AOE of any clips-aligned junction."""
        for junction in state.map.get_clips_junctions():
            dist = abs(state.row - junction.position[0]) + abs(state.col - junction.position[1])
            if dist <= JUNCTION_AOE_RANGE:
                return True
        return False

    def nearest_safe_zone(self, state: AgentState) -> Optional[tuple[int, int]]:
        """Find nearest cogs-aligned building (assembler or junction)."""
        candidates: list[tuple[int, tuple[int, int]]] = []

        # Assembler is always cogs-aligned
        assembler_pos = state.map.stations.get("assembler")
        if assembler_pos:
            dist = abs(assembler_pos[0] - state.row) + abs(assembler_pos[1] - state.col)
            candidates.append((dist, assembler_pos))

        # Cogs junctions
        for junction in state.map.get_cogs_junctions():
            dist = abs(junction.position[0] - state.row) + abs(junction.position[1] - state.col)
            candidates.append((dist, junction.position))

        if not candidates:
            return None

        candidates.sort(key=lambda x: x[0])
        return candidates[0][1]

    def step_based_range_limit(self, step: int) -> int:
        """Calculate exploration range limit based on current step.

        - First 1000 ticks: limit range to 50
        - After 1000 ticks: start at 100, increase by 10 every 100 ticks
        """
        if step < 1000:
            return 50
        else:
            # Start at 100 at step 1000, increase by 10 every 100 steps
            extra_hundreds = (step - 1000) // 100
            return 100 + extra_hundreds * 10

    def max_safe_distance(self, state: AgentState, risk: RiskTolerance) -> int:
        """Calculate max round-trip distance based on HP, risk tolerance, and step.

        Returns the maximum total distance (to target + back to healing) that's safe.
        Also applies step-based range limits to encourage gradual expansion.
        """
        # Reserve HP based on risk tolerance
        threshold = self.RETREAT_THRESHOLDS[risk]
        available_hp = max(0, state.hp - threshold)

        # Calculate drain rate
        drain_rate = self._get_hp_drain_rate(state)
        if drain_rate <= 0:
            hp_based_dist = 999  # No drain, unlimited HP-based range
        else:
            # Max steps we can take before HP runs out
            max_steps = available_hp // drain_rate
            # Round trip, so divide by 2
            hp_based_dist = max_steps // 2

        # Apply step-based range limit
        step_limit = self.step_based_range_limit(state.step)

        return min(hp_based_dist, step_limit)

    def can_reach_safely(self, state: AgentState, target: tuple[int, int], risk: RiskTolerance) -> bool:
        """Check if agent can reach target AND return to safety."""
        dist_to_target = abs(target[0] - state.row) + abs(target[1] - state.col)

        # Find distance from target back to nearest safe zone
        safe_pos = self.nearest_safe_zone(state)
        if safe_pos is None:
            # No known safe zone, be conservative
            dist_back = dist_to_target
        else:
            dist_back = abs(target[0] - safe_pos[0]) + abs(target[1] - safe_pos[1])

        total_dist = dist_to_target + max(0, dist_back - JUNCTION_AOE_RANGE)
        max_dist = self.max_safe_distance(state, risk)

        return total_dist <= max_dist

    def is_position_in_enemy_aoe(self, state: AgentState, pos: tuple[int, int]) -> bool:
        """Check if a position is within AOE of any enemy junction."""
        for junction in state.map.get_clips_junctions():
            dist = abs(pos[0] - junction.position[0]) + abs(pos[1] - junction.position[1])
            if dist <= JUNCTION_AOE_RANGE:
                return True
        return False

    def _steps_to_nearest_safe_zone(self, state: AgentState) -> int:
        """Calculate steps to reach nearest safe zone's AOE."""
        safe_pos = self.nearest_safe_zone(state)
        if safe_pos is None:
            return 100  # Unknown, be conservative

        dist = abs(safe_pos[0] - state.row) + abs(safe_pos[1] - state.col)
        return max(0, dist - JUNCTION_AOE_RANGE)

    def _get_hp_drain_rate(self, state: AgentState) -> int:
        """Calculate current HP drain rate based on position."""
        # If in safe zone, no drain
        if self.is_in_safe_zone(state):
            return 0

        drain = HP_DRAIN_OUTSIDE_SAFE_ZONE

        # Additional drain if near enemy
        if self.is_in_danger_zone(state):
            drain += HP_DRAIN_NEAR_ENEMY

        return drain
