"""
Scrambler behavior for Pinky policy.

Scramblers raid enemy junctions to neutralize them, enabling aligners.
Strategy: Get hearts, target enemy junctions that block neutral territory.
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
    JUNCTION_AOE_RANGE,
    DebugInfo,
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

    # How many steps to explore before giving up on gear
    EXPLORATION_STEPS = 100

    # How many ticks to explore before retrying gear station
    GEAR_RETRY_INTERVAL = 100

    # How many steps before junction alignment data is considered stale
    # Since alignment can change (e.g., enemy aligners convert junctions),
    # scramblers should revisit old junctions to check for new targets
    JUNCTION_STALE_THRESHOLD = 50

    def act(self, state: AgentState, services: Services) -> Action:
        """Execute scrambler behavior.

        Priority order:
        1. Stuck detection - break out of stuck loops (using navigator's escape handling)
        2. Critical HP retreat - survive first
        3. Get gear (REQUIRED) - must have scrambler gear to scramble effectively
        4. Get hearts (REQUIRED) - must have hearts to scramble
        5. Hunt and scramble enemy junctions
        """
        # Track gear state
        state.had_gear_last_step = state.scrambler_gear

        # Priority 0: Check for stuck patterns and handle escape mode (via navigator)
        escape_action = services.navigator.check_and_handle_escape(state)
        if escape_action:
            debug_info = services.navigator.get_escape_debug_info(state)
            state.debug_info = DebugInfo(**debug_info)
            return escape_action

        # Priority 1: Retreat only if critically low (scramblers are tanky)
        # Only retreat when HP drops below 30 (they start with 50)
        if state.hp < 30:
            if DEBUG:
                print(f"[A{state.agent_id}] SCRAMBLER: Retreating! HP={state.hp}")
            state.debug_info = DebugInfo(mode="retreat", goal="safety", target_object="safe_zone", signal="hp_low")
            return self._retreat_to_safety(state, services)

        # Priority 2: Get gear (REQUIRED) - scrambler gear is needed to scramble effectively
        # Gear gives +200 HP which is essential for surviving in enemy territory
        if self.needs_gear(state):
            return self._get_gear(state, services)

        # Priority 3: Get hearts (REQUIRED) - hearts are needed to scramble junctions
        if not self.has_resources_to_act(state):
            return self._get_hearts(state, services)

        # Priority 4: Hunt and scramble enemy junctions
        return self._scramble_junction(state, services)

    def needs_gear(self, state: AgentState) -> bool:
        """Scramblers MUST have scrambler gear to scramble effectively.

        Gear provides +200 HP which is essential for surviving enemy territory.
        Without gear, scramblers would die too quickly to be effective.
        """
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

        # First try visible scrambler_station in current observation
        if state.last_obs is not None:
            result = services.map_tracker.get_direction_to_nearest(state, state.last_obs, frozenset({station_name}))
            if result:
                direction, target_pos = result
                if DEBUG:
                    print(f"[A{state.agent_id}] SCRAMBLER: Station visible at {target_pos}, moving {direction}")
                state.debug_info = DebugInfo(
                    mode="get_gear", goal="scrambler_station", target_object=station_name, target_pos=target_pos
                )
                return Action(name=f"move_{direction}")

        # Use accumulated map knowledge if station was found
        station_pos = state.map.stations.get(station_name)

        if station_pos is not None:
            dist = manhattan_distance(state.pos, station_pos)

            # If ON the station, we should have received gear from walking in
            if state.pos == station_pos:
                if DEBUG:
                    print(f"[A{state.agent_id}] SCRAMBLER: ON station {station_pos}, no gear - explore")
                state.debug_info = DebugInfo(
                    mode="get_gear", goal="on_station_no_gear", target_object=station_name, target_pos=station_pos
                )
                state.last_gear_attempt_step = state.step
                return Action(name="move_east")

            if is_adjacent(state.pos, station_pos):
                if DEBUG:
                    print(f"[A{state.agent_id}] SCRAMBLER: Getting gear from {station_pos}")
                state.debug_info = DebugInfo(
                    mode="get_gear", goal="use_station", target_object=station_name, target_pos=station_pos
                )
                return services.navigator.use_object_at(state, station_pos)

            if DEBUG and state.step % 10 == 0:
                print(f"[A{state.agent_id}] SCRAMBLER: Moving to station at {station_pos} (dist={dist})")
            state.debug_info = DebugInfo(
                mode="get_gear", goal=f"move_to_station({dist})", target_object=station_name, target_pos=station_pos
            )
            return services.navigator.move_to(state, station_pos, reach_adjacent=True)

        # Station not found yet - explore
        if DEBUG and state.step % 10 == 0:
            print(f"[A{state.agent_id}] SCRAMBLER: Exploring for station (step {state.step})")
        state.debug_info = DebugInfo(mode="explore", goal="find_station", target_object=station_name)
        return self._explore_for_station(state, services)

    def _explore_for_station(self, state: AgentState, services: Services) -> Action:
        """Explore to find the scrambler station."""
        # Spread scramblers out by giving each agent a different primary direction
        direction = get_explore_direction_for_agent(state.agent_id)
        return explore_for_station(state, services, primary_direction=direction)

    # How often to cycle exploration direction (in steps)
    EXPLORE_DIRECTION_CYCLE = 100

    def _explore_for_enemy_junctions(self, state: AgentState, services: Services) -> Action:
        """Explore to find clips junctions, ensuring whole-map coverage.

        Strategy:
        1. Revisit stale junctions (alignment data may be outdated) - least recently seen first
        2. If no stale junctions, patrol the map by cycling through different directions
        3. Reset exploration origin periodically to cover new areas
        """
        # Find junctions that haven't been visited recently (alignment could have changed)
        # Prioritize least recently seen - these are most likely to have outdated alignment info
        stale_junctions: list[tuple[int, int, StructureInfo]] = []  # (steps_since_seen, dist, junction)

        for junction in state.map.get_junctions():
            steps_since_seen = state.step - junction.last_seen_step

            # Only consider junctions we haven't seen recently
            if steps_since_seen < self.JUNCTION_STALE_THRESHOLD:
                continue

            # Skip known clips junctions (we already found them, _find_best_target handles them)
            # Focus on neutral and unknown junctions that could have become clips
            if junction.is_clips_aligned():
                continue

            dist = manhattan_distance(state.pos, junction.position)
            stale_junctions.append((steps_since_seen, dist, junction))

        if stale_junctions:
            # Sort by: most stale first (highest steps_since_seen), then by distance
            stale_junctions.sort(key=lambda x: (-x[0], x[1]))
            target = stale_junctions[0][2]

            if DEBUG and state.step % 50 == 0:
                print(
                    f"[A{state.agent_id}] SCRAMBLER: Revisiting stale junction at {target.position} "
                    f"(last_seen={target.last_seen_step}, age={state.step - target.last_seen_step})"
                )

            state.debug_info = DebugInfo(
                mode="explore",
                goal=f"revisit_stale(age={state.step - target.last_seen_step})",
                target_object="junction",
                target_pos=target.position,
            )
            return services.navigator.move_to(state, target.position, reach_adjacent=True)

        # No stale junctions - patrol the map to find enemy territory
        # Cycle through directions over time to ensure whole-map coverage
        # Each scrambler starts at a different direction (agent_id offset) and cycles through all 4
        directions = ["north", "east", "south", "west"]
        current_cycle = state.step // self.EXPLORE_DIRECTION_CYCLE
        cycle_index = (current_cycle + state.agent_id) % 4
        direction_bias = directions[cycle_index]

        # Reset exploration origin when we've been exploring from the same origin for too long
        # This prevents getting stuck in one area - forces movement to new regions
        if state.nav.explore_origin is not None:
            steps_at_origin = state.step - state.nav.explore_start_step
            if steps_at_origin >= self.EXPLORE_DIRECTION_CYCLE:
                # Time to move to a new area - reset origin to current position
                state.nav.explore_origin = state.pos
                state.nav.explore_start_step = state.step
                if DEBUG:
                    print(
                        f"[A{state.agent_id}] SCRAMBLER: Resetting patrol origin to {state.pos}, "
                        f"direction={direction_bias}"
                    )

        if DEBUG and state.step % 50 == 0:
            clips_count = len(state.map.get_clips_junctions())
            all_count = len(state.map.get_junctions())
            print(
                f"[A{state.agent_id}] SCRAMBLER: Patrolling (clips={clips_count}, "
                f"all={all_count}, direction={direction_bias}, cycle={current_cycle})"
            )

        state.debug_info = DebugInfo(mode="explore", goal=f"patrol_{direction_bias}", target_object="junction")
        return services.navigator.explore(state, direction_bias=direction_bias)

    def _get_hearts(self, state: AgentState, services: Services) -> Action:
        """Get hearts from chest."""
        # First try visible chest in current observation
        if state.last_obs is not None:
            result = services.map_tracker.get_direction_to_nearest(state, state.last_obs, frozenset({"chest"}))
            if result:
                direction, target_pos = result
                if DEBUG:
                    print(f"[A{state.agent_id}] SCRAMBLER: Chest visible at {target_pos}, moving {direction}")
                state.debug_info = DebugInfo(
                    mode="get_hearts", goal="chest", target_object="chest", target_pos=target_pos
                )
                return Action(name=f"move_{direction}")

        # Use accumulated map knowledge
        chest_pos = state.map.stations.get("chest")

        if chest_pos is None:
            # Try assembler as fallback
            assembler_pos = state.map.stations.get("assembler")
            if assembler_pos is not None:
                chest_pos = assembler_pos
            else:
                if DEBUG:
                    print(f"[A{state.agent_id}] SCRAMBLER: No chest/assembler, exploring")
                state.debug_info = DebugInfo(mode="explore", goal="find_chest", target_object="chest")
                return services.navigator.explore(state)

        dist = manhattan_distance(state.pos, chest_pos)

        if is_adjacent(state.pos, chest_pos):
            if DEBUG:
                print(f"[A{state.agent_id}] SCRAMBLER: Getting hearts from {chest_pos}")
            state.debug_info = DebugInfo(
                mode="get_hearts", goal="use_chest", target_object="chest", target_pos=chest_pos
            )
            return services.navigator.use_object_at(state, chest_pos)

        state.debug_info = DebugInfo(
            mode="get_hearts", goal=f"move_to_chest(dist={dist})", target_object="chest", target_pos=chest_pos
        )
        return services.navigator.move_to(state, chest_pos, reach_adjacent=True)

    def _scramble_junction(self, state: AgentState, services: Services) -> Action:
        """Find and scramble an enemy (clips) junction.

        Strategy: ONLY target clips-aligned junctions (save hearts for real scrambles).
        Always verify alignment AND resources before using - both can change at any time.
        """
        # SAFETY CHECK: Verify we still have the required resources
        # This is a defensive check - act() should have already verified this
        if self.needs_gear(state):
            if DEBUG:
                print(f"[A{state.agent_id}] SCRAMBLER: In _scramble_junction but missing gear, getting gear")
            return self._get_gear(state, services)

        if not self.has_resources_to_act(state):
            if DEBUG:
                print(f"[A{state.agent_id}] SCRAMBLER: In _scramble_junction but no hearts, getting hearts")
            return self._get_hearts(state, services)

        # First try to find CLIPS junction in current observation
        if state.last_obs is not None:
            result = services.map_tracker.get_direction_to_nearest(
                state, state.last_obs, frozenset({"junction", "charger", "supply_depot"})
            )
            if result:
                direction, target_pos = result
                struct = state.map.get_structure_at(target_pos)

                # ONLY target confirmed clips-aligned junctions
                # Don't waste time on neutral/unknown - let exploration handle discovery
                if struct is not None and struct.is_clips_aligned():
                    if DEBUG:
                        print(f"[A{state.agent_id}] SCRAMBLER: Enemy junction at {target_pos}, moving {direction}")
                    state.debug_info = DebugInfo(
                        mode="scramble", goal="enemy_junction", target_object="junction", target_pos=target_pos
                    )
                    return Action(name=f"move_{direction}")
                # If not clips-aligned, don't target it - fall through to map knowledge or explore

        # Fall back to map knowledge - find known clips junctions
        target = self._find_best_target(state, services)

        if target is not None:
            dist = manhattan_distance(state.pos, target.position)

            if is_adjacent(state.pos, target.position):
                # IMPORTANT: Re-verify alignment before using!
                # Alignment could have changed while we were moving toward it
                current_struct = state.map.get_structure_at(target.position)
                if current_struct is None or not current_struct.is_clips_aligned():
                    if DEBUG:
                        alignment = current_struct.alignment if current_struct else "unknown"
                        print(
                            f"[A{state.agent_id}] SCRAMBLER: Target at {target.position} no longer clips "
                            f"(now {alignment}), finding new target"
                        )
                    state.debug_info = DebugInfo(
                        mode="scramble",
                        goal="target_alignment_changed",
                        target_object="junction",
                        signal="alignment_changed",
                    )
                    # Target is no longer clips - explore to find a new one
                    return self._explore_for_enemy_junctions(state, services)

                # CRITICAL: Final check before spending hearts - verify we have resources
                if not self.has_resources_to_act(state):
                    if DEBUG:
                        print(
                            f"[A{state.agent_id}] SCRAMBLER: Adjacent to junction but no hearts! Getting hearts first."
                        )
                    return self._get_hearts(state, services)

                if DEBUG:
                    print(f"[A{state.agent_id}] SCRAMBLER: Scrambling junction at {target.position}")
                state.debug_info = DebugInfo(
                    mode="scramble", goal="use_junction", target_object="junction", target_pos=target.position
                )
                return services.navigator.use_object_at(state, target.position)

            # Not adjacent yet - verify target is still clips before continuing to move toward it
            current_struct = state.map.get_structure_at(target.position)
            if current_struct is None or not current_struct.is_clips_aligned():
                if DEBUG:
                    alignment = current_struct.alignment if current_struct else "unknown"
                    print(
                        f"[A{state.agent_id}] SCRAMBLER: Target at {target.position} no longer clips "
                        f"(now {alignment}), finding new target"
                    )
                # Target changed - find a new one next tick
                return self._explore_for_enemy_junctions(state, services)

            state.debug_info = DebugInfo(
                mode="scramble",
                goal=f"move_to_junction(dist={dist})",
                target_object="junction",
                target_pos=target.position,
            )
            return services.navigator.move_to(state, target.position, reach_adjacent=True)

        # No known clips junctions - explore to find them or revisit stale junctions
        # Since alignment can change, revisit old junctions (least recently seen first)
        return self._explore_for_enemy_junctions(state, services)

    def _find_best_target(self, state: AgentState, services: Services) -> Optional[StructureInfo]:
        """Find enemy junction to scramble.

        ONLY returns confirmed clips-aligned junctions.
        Stale/neutral junctions are handled by exploration, not targeting.
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
