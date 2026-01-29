"""
Aligner behavior for Pinky policy.

Aligners convert neutral junctions to expand cogs territory.
Strategy: Find viable target first, then get gear + hearts, then align.
A viable target is a neutral junction that is 10+ tiles away from any clips junction.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from cogames_agents.policy.scripted_agent.common.roles import ROLE_TO_STATION
from cogames_agents.policy.scripted_agent.pinky.behaviors.base import (
    Services,
    explore_for_station,
    get_explore_direction_for_agent,
    is_adjacent,
    manhattan_distance,
)
from cogames_agents.policy.scripted_agent.pinky.types import (
    DEBUG,
    DebugInfo,
    RiskTolerance,
    Role,
    StructureInfo,
)
from mettagrid.simulator import Action

if TYPE_CHECKING:
    from cogames_agents.policy.scripted_agent.pinky.state import AgentState

# Minimum distance from clips junctions for a valid aligner target
MIN_DISTANCE_FROM_CLIPS = 8


class AlignerBehavior:
    """Aligner agent: convert neutral junctions to cogs."""

    role = Role.ALIGNER
    risk_tolerance = RiskTolerance.MODERATE

    # How many ticks to explore before retrying gear station
    GEAR_RETRY_INTERVAL = 100

    def act(self, state: AgentState, services: Services) -> Action:
        """Execute aligner behavior.

        Flow:
        1. Handle stuck/escape
        2. Retreat if low HP
        3. Find viable target (neutral junction 10+ from clips junctions)
        4. If no target -> explore
        5. If has target -> get gear -> get hearts -> align
        """
        # Track gear state for detecting gear loss
        has_gear_now = state.aligner_gear
        just_lost_gear = state.had_gear_last_step and not has_gear_now
        state.had_gear_last_step = has_gear_now

        # Priority 0: Check for stuck patterns and handle escape mode
        escape_action = services.navigator.check_and_handle_escape(state)
        if escape_action:
            state.aligner_target = None  # Clear target when escaping
            debug_info = services.navigator.get_escape_debug_info(state)
            state.debug_info = DebugInfo(**debug_info)
            return escape_action

        # Priority 1: Retreat if HP is getting low (be more conservative to avoid dying)
        # Aligners are valuable - retreat at 50 HP to stay alive
        if state.hp <= 50:
            if DEBUG:
                print(f"[A{state.agent_id}] ALIGNER: Retreating! HP={state.hp}")
            state.debug_info = DebugInfo(mode="retreat", goal="safety", target_object="safe_zone", signal="hp_low")
            return self._retreat_to_safety(state, services)

        # Priority 2: Find or validate a viable target
        # Re-validate current target each step (it may have been aligned by someone else or become invalid)
        target = self._get_or_find_target(state, services)

        # If no viable target, explore to find junctions
        if target is None:
            state.aligner_target = None
            if DEBUG:
                print(f"[A{state.agent_id}] ALIGNER: No viable target, exploring")
            state.debug_info = DebugInfo(mode="explore", goal="find_junction", target_object="junction")
            return self._explore_for_junctions(state, services)

        # Store the target
        state.aligner_target = target.position

        # Priority 3: Get gear if missing (required for aligning)
        if self.needs_gear(state):
            # Check if we should try to get gear now
            ticks_since_last_attempt = state.step - state.last_gear_attempt_step

            # Try to get gear if:
            # 1. Just lost gear (immediately go home)
            # 2. First 30 steps (initial period)
            # 3. 100 ticks have passed since last attempt
            should_try_gear = just_lost_gear or state.step < 30 or ticks_since_last_attempt >= self.GEAR_RETRY_INTERVAL

            if should_try_gear:
                return self._get_gear(state, services)
            else:
                # Between retries, get hearts so we're ready when we get gear
                if not self.has_resources_to_act(state):
                    return self._get_hearts(state, services)
                # Otherwise explore toward target
                state.debug_info = DebugInfo(
                    mode="explore", goal="toward_target", target_object="junction", target_pos=target.position
                )
                return self._move_toward_target(state, target.position)

        # Priority 4: Get hearts if empty (needed to align)
        if not self.has_resources_to_act(state):
            return self._get_hearts(state, services)

        # Priority 5: Move to and align the target junction
        return self._align_junction(state, services, target)

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

    def _is_valid_target(self, pos: tuple[int, int], state: AgentState) -> bool:
        """Check if a position is a valid aligner target.

        Valid target = neutral junction that is 10+ tiles from any clips junction.
        """
        struct = state.map.get_structure_at(pos)
        if struct is None:
            return False

        # Must be neutral (not already aligned)
        if not struct.is_neutral():
            return False

        # Must be 10+ tiles from any clips junction
        clips_junctions = state.map.get_clips_junctions()
        for clips_j in clips_junctions:
            if manhattan_distance(pos, clips_j.position) < MIN_DISTANCE_FROM_CLIPS:
                return False

        return True

    def _get_or_find_target(self, state: AgentState, services: Services) -> Optional[StructureInfo]:
        """Get current target if still valid, otherwise find a new one.

        Returns None if no valid targets exist.
        """
        # Check if current target is still valid
        current_target = getattr(state, "aligner_target", None)
        if current_target is not None and self._is_valid_target(current_target, state):
            struct = state.map.get_structure_at(current_target)
            if struct is not None:
                if DEBUG:
                    print(f"[A{state.agent_id}] ALIGNER: Keeping target at {current_target}")
                return struct

        # Current target invalid or missing, find a new one
        return self._find_best_target(state, services)

    def _get_gear(self, state: AgentState, services: Services) -> Action:
        """Get aligner gear from station."""
        station_name = ROLE_TO_STATION[Role.ALIGNER]

        # First try visible aligner_station in current observation (most reliable)
        if state.last_obs is not None:
            result = services.map_tracker.get_direction_to_nearest(state, state.last_obs, frozenset({station_name}))
            if result:
                direction, target_pos = result
                if DEBUG:
                    print(f"[A{state.agent_id}] ALIGNER: Station visible at {target_pos}, moving {direction}")
                state.debug_info = DebugInfo(
                    mode="get_gear", goal="aligner_station", target_object=station_name, target_pos=target_pos
                )
                return Action(name=f"move_{direction}")

        # Use accumulated map knowledge if station was found
        station_pos = state.map.stations.get(station_name)

        if station_pos is not None:
            dist = manhattan_distance(state.pos, station_pos)

            # If ON the station, we should have received gear from walking in
            # If gear not received yet, record this attempt and try to be useful while waiting
            if state.pos == station_pos:
                if DEBUG:
                    print(
                        f"[A{state.agent_id}] ALIGNER: ON station at {station_pos}, no gear - "
                        f"will try to be useful and retry in {self.GEAR_RETRY_INTERVAL} ticks"
                    )
                state.debug_info = DebugInfo(
                    mode="get_gear", goal="on_station_no_gear", target_object=station_name, target_pos=station_pos
                )
                # Record this attempt - aligner will try other things for GEAR_RETRY_INTERVAL ticks then retry
                state.last_gear_attempt_step = state.step
                # Step off the station, then fall through to try other behaviors
                return Action(name="move_east")

            if is_adjacent(state.pos, station_pos):
                if DEBUG:
                    print(f"[A{state.agent_id}] ALIGNER: Getting gear from {station_pos}")
                state.debug_info = DebugInfo(
                    mode="get_gear", goal="use_station", target_object=station_name, target_pos=station_pos
                )
                return services.navigator.use_object_at(state, station_pos)

            if DEBUG and state.step % 10 == 0:
                print(f"[A{state.agent_id}] ALIGNER: Moving to station at {station_pos} (dist={dist})")
            state.debug_info = DebugInfo(
                mode="get_gear",
                goal=f"move_to_station(dist={dist})",
                target_object=station_name,
                target_pos=station_pos,
            )
            # Use simple directional movement - more reliable for aligners
            return self._move_toward_target(state, station_pos)

        # Station not found yet - keep exploring until we find it
        # Don't give up - gear is required before getting hearts
        if DEBUG and state.step % 10 == 0:
            print(f"[A{state.agent_id}] ALIGNER: Exploring for station (step {state.step})")
        state.debug_info = DebugInfo(mode="explore", goal="find_station", target_object=station_name)
        return self._explore_for_station(state, services)

    def _explore_for_station(self, state: AgentState, services: Services) -> Action:
        """Explore to find the aligner station."""
        # Spread aligners out by giving each agent a different primary direction
        direction = get_explore_direction_for_agent(state.agent_id)
        return explore_for_station(state, services, primary_direction=direction)

    def _get_hearts(self, state: AgentState, services: Services) -> Action:
        """Get hearts from chest."""
        # First try visible chest in current observation
        if state.last_obs is not None:
            result = services.map_tracker.get_direction_to_nearest(state, state.last_obs, frozenset({"chest"}))
            if result:
                direction, target_pos = result
                if DEBUG:
                    print(f"[A{state.agent_id}] ALIGNER: Chest visible at {target_pos}, moving {direction}")
                state.debug_info = DebugInfo(
                    mode="get_hearts", goal="chest", target_object="chest", target_pos=target_pos
                )
                return Action(name=f"move_{direction}")

        # Use accumulated map knowledge
        chest_pos = state.map.stations.get("chest")

        if chest_pos is None:
            # Try assembler as fallback (can also give hearts)
            assembler_pos = state.map.stations.get("assembler")
            if assembler_pos is not None:
                chest_pos = assembler_pos
            else:
                if DEBUG and state.step % 20 == 0:
                    print(f"[A{state.agent_id}] ALIGNER: No chest/assembler found, exploring")
                state.debug_info = DebugInfo(mode="explore", goal="find_chest", target_object="chest")
                return services.navigator.explore(state)

        dist = manhattan_distance(state.pos, chest_pos)

        if is_adjacent(state.pos, chest_pos):
            if DEBUG:
                print(f"[A{state.agent_id}] ALIGNER: Getting hearts from {chest_pos}")
            state.debug_info = DebugInfo(
                mode="get_hearts", goal="use_chest", target_object="chest", target_pos=chest_pos
            )
            return services.navigator.use_object_at(state, chest_pos)

        if DEBUG and state.step % 10 == 0:
            print(f"[A{state.agent_id}] ALIGNER: Moving to chest at {chest_pos} (dist={dist})")
        state.debug_info = DebugInfo(
            mode="get_hearts", goal=f"move_to_chest(dist={dist})", target_object="chest", target_pos=chest_pos
        )
        # Use simple directional movement toward target - more reliable than pathfinding
        # when the internal map hasn't been fully explored
        return self._move_toward_target(state, chest_pos)

    def _align_junction(self, state: AgentState, services: Services, target: StructureInfo) -> Action:
        """Move to and align the target junction."""
        dist = manhattan_distance(state.pos, target.position)

        if is_adjacent(state.pos, target.position):
            if DEBUG:
                print(f"[A{state.agent_id}] ALIGNER: Aligning junction at {target.position}")
            state.debug_info = DebugInfo(
                mode="align", goal="use_junction", target_object="junction", target_pos=target.position
            )
            return services.navigator.use_object_at(state, target.position)

        if DEBUG and state.step % 10 == 0:
            print(f"[A{state.agent_id}] ALIGNER: Moving to junction at {target.position} (dist={dist})")
        state.debug_info = DebugInfo(
            mode="align", goal=f"move_to_junction(dist={dist})", target_object="junction", target_pos=target.position
        )
        # Use simple directional movement - more reliable for aligners
        return self._move_toward_target(state, target.position)

    def _move_toward_target(self, state: AgentState, target: tuple[int, int]) -> Action:
        """Move one step toward target using simple directional movement.

        More reliable than pathfinding when internal map hasn't been fully explored.
        Prioritizes the axis with the larger delta.
        """
        dr = target[0] - state.pos[0]  # row delta (positive = south)
        dc = target[1] - state.pos[1]  # col delta (positive = east)

        # Prioritize the axis with larger delta
        if abs(dr) >= abs(dc):
            # Try vertical first, then horizontal
            if dr > 0:
                return Action(name="move_south")
            elif dr < 0:
                return Action(name="move_north")
            elif dc > 0:
                return Action(name="move_east")
            elif dc < 0:
                return Action(name="move_west")
        else:
            # Try horizontal first, then vertical
            if dc > 0:
                return Action(name="move_east")
            elif dc < 0:
                return Action(name="move_west")
            elif dr > 0:
                return Action(name="move_south")
            elif dr < 0:
                return Action(name="move_north")

        return Action(name="noop")  # Already at target

    def _find_best_target(self, state: AgentState, services: Services) -> Optional[StructureInfo]:
        """Find alignable junction - must be neutral AND 10+ tiles from clips junctions.

        Prioritizes junctions near the hub (strategic value).
        """
        max_dist = services.safety.max_safe_distance(state, self.risk_tolerance)

        # Get hub position for prioritization
        hub_pos = state.map.stations.get("assembler") or state.map.stations.get("hub")

        # Get all clips junction positions for distance check
        clips_junctions = state.map.get_clips_junctions()

        def is_too_close_to_clips(pos: tuple[int, int]) -> bool:
            """Target must be 10+ tiles from any clips junction."""
            return any(manhattan_distance(pos, ej.position) < MIN_DISTANCE_FROM_CLIPS for ej in clips_junctions)

        # Find alignable junctions: neutral AND 10+ from clips junctions
        alignable: list[tuple[int, int, StructureInfo]] = []  # (hub_dist, agent_dist, junction)
        for junction in state.map.get_neutral_junctions():
            if is_too_close_to_clips(junction.position):
                continue  # Can't align - too close to clips junction

            agent_dist = manhattan_distance(state.pos, junction.position)
            if agent_dist > max_dist:
                continue

            # Prioritize junctions near hub
            hub_dist = manhattan_distance(junction.position, hub_pos) if hub_pos else 999
            alignable.append((hub_dist, agent_dist, junction))

        if not alignable:
            if DEBUG:
                neutral_count = len(state.map.get_neutral_junctions())
                clips_count = len(clips_junctions)
                print(
                    f"[A{state.agent_id}] ALIGNER: No valid targets. "
                    f"Neutral junctions: {neutral_count}, Clips junctions: {clips_count}"
                )
            return None

        # Sort by: 1) distance to hub (closer is better), 2) distance to agent
        alignable.sort(key=lambda x: (x[0], x[1]))
        return alignable[0][2]

    def _explore_for_junctions(self, state: AgentState, services: Services) -> Action:
        """Explore to find new junctions by filling out the map.

        Uses the navigator's frontier-based exploration with a direction bias
        based on agent ID to spread coverage across the map.
        """
        # Each aligner explores toward a different direction to spread out
        directions = ["north", "east", "south", "west"]
        direction_bias = directions[state.agent_id % 4]

        return services.navigator.explore(state, direction_bias=direction_bias)
