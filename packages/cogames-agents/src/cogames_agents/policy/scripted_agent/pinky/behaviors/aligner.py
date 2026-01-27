"""
Aligner behavior for Pinky policy.

Aligners convert neutral junctions to expand cogs territory.
Strategy: Get gear, get hearts, target neutral junctions OUTSIDE enemy AOE only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from cogames_agents.policy.scripted_agent.pinky.behaviors.base import Services, is_adjacent, manhattan_distance
from cogames_agents.policy.scripted_agent.pinky.types import (
    DEBUG,
    JUNCTION_AOE_RANGE,
    ROLE_TO_STATION,
    DebugInfo,
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

    # Maximum distance from spawn to explore (stay within 50x50 area)
    MAX_EXPLORE_RADIUS = 25

    # How many ticks to explore before retrying gear station
    GEAR_RETRY_INTERVAL = 100

    # How many ticks at same position before switching to explore
    STUCK_THRESHOLD = 5  # Fast detection to avoid wasting time on blocked paths

    def act(self, state: AgentState, services: Services) -> Action:
        """Execute aligner behavior."""
        # Track gear state for detecting gear loss
        has_gear_now = state.aligner_gear
        just_lost_gear = state.had_gear_last_step and not has_gear_now
        state.had_gear_last_step = has_gear_now

        # Track stuck detection: count consecutive steps at same position
        if state.pos == state.last_position:
            state.steps_at_same_position += 1
        else:
            state.steps_at_same_position = 0
            state.last_position = state.pos

        # Priority 0: If stuck for too long, force explore to break out
        if state.steps_at_same_position >= self.STUCK_THRESHOLD:
            if DEBUG:
                print(f"[A{state.agent_id}] ALIGNER: STUCK for {state.steps_at_same_position} ticks, random break")
            state.debug_info = DebugInfo(mode="explore", goal="unstuck", target_object="-", signal="stuck")
            state.steps_at_same_position = 0
            # Try random direction to escape - rotate through based on step
            directions = ["north", "south", "east", "west"]
            direction = directions[(state.step + state.agent_id) % 4]
            return Action(name=f"move_{direction}")

        # Priority 1: Retreat if HP is getting low (be more conservative to avoid dying)
        # Aligners are valuable - retreat at 50 HP to stay alive
        if state.hp <= 50:
            if DEBUG:
                print(f"[A{state.agent_id}] ALIGNER: Retreating! HP={state.hp}")
            state.debug_info = DebugInfo(mode="retreat", goal="safety", target_object="safe_zone", signal="hp_low")
            return self._retreat_to_safety(state, services)

        # Priority 2: Get gear if missing (required for aligning)
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
                # Otherwise explore to find junctions
                state.debug_info = DebugInfo(mode="explore", goal="find_junction", target_object="junction")
                return services.navigator.explore(state)

        # Priority 3: Get hearts if empty (needed to align)
        if not self.has_resources_to_act(state):
            return self._get_hearts(state, services)

        # Priority 4: Find and align best target junction
        # Note: Can only align neutral junctions OUTSIDE clips AOE
        # Scramblers must neutralize clips junctions first to expand alignable area
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
        """Explore using expanding box pattern to cover more map area.

        Uses agent_id to offset starting direction, spreading agents out.
        """
        # Get spawn position (default to 100,100 if not tracked)
        spawn = getattr(state, "spawn_pos", None) or (100, 100)

        # Calculate current distance from spawn
        dr = state.pos[0] - spawn[0]
        dc = state.pos[1] - spawn[1]
        dist_from_spawn = max(abs(dr), abs(dc))

        # If too far from spawn, move back toward it
        if dist_from_spawn > self.MAX_EXPLORE_RADIUS:
            if abs(dr) > abs(dc):
                return Action(name="move_north" if dr > 0 else "move_south")
            else:
                return Action(name="move_west" if dc > 0 else "move_east")

        # Direction sequences for different starting directions
        direction_orders = [
            ["east", "south", "west", "north"],
            ["south", "west", "north", "east"],
            ["west", "north", "east", "south"],
            ["north", "east", "south", "west"],
        ]
        # Pick direction order based on agent_id to spread agents out
        dirs = direction_orders[state.agent_id % 4]

        explore_step = max(0, state.step - 2)
        segment_base = 10

        # Build expanding pattern with agent-specific directions
        segments: list[tuple[str, int]] = []
        ring = 1
        while len(segments) < 100:
            seg_len = segment_base * ring
            segments.append((dirs[0], seg_len))
            segments.append((dirs[1], seg_len))
            segments.append((dirs[2], seg_len + segment_base))
            segments.append((dirs[3], seg_len + segment_base))
            ring += 1
            if ring > 5:
                ring = 1

        step_count = 0
        for direction, seg_len in segments:
            if step_count + seg_len > explore_step:
                return Action(name=f"move_{direction}")
            step_count += seg_len

        return Action(name=f"move_{dirs[0]}")

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

    def _align_junction(self, state: AgentState, services: Services) -> Action:
        """Find and align a neutral junction."""
        # First try to find a junction in current observation
        if state.last_obs is not None:
            result = services.map_tracker.get_direction_to_nearest(
                state, state.last_obs, frozenset({"junction", "charger", "supply_depot"})
            )
            if result:
                direction, target_pos = result
                # Check if this junction is alignable (not cogs-aligned, not in enemy AOE)
                struct = state.map.get_structure_at(target_pos)

                # Skip if we KNOW it's already cogs-aligned
                if struct is not None and struct.is_cogs_aligned():
                    pass  # Don't target our own junctions
                else:
                    # Target it if: neutral, unknown, or clips (to check when we arrive)
                    # All junctions start neutral, so safe to assume alignable
                    enemy_junctions = state.map.get_clips_junctions()
                    in_enemy_aoe = any(
                        manhattan_distance(target_pos, ej.position) <= JUNCTION_AOE_RANGE for ej in enemy_junctions
                    )
                    if not in_enemy_aoe:
                        alignment = struct.alignment if struct else "unknown"
                        if DEBUG:
                            print(f"[A{state.agent_id}] ALIGNER: Junction at {target_pos} ({alignment}), {direction}")
                        state.debug_info = DebugInfo(
                            mode="align", goal="junction", target_object="junction", target_pos=target_pos
                        )
                        return Action(name=f"move_{direction}")

        # Fall back to map knowledge for best target
        target = self._find_best_target(state, services)

        if target is None:
            state.debug_info = DebugInfo(mode="explore", goal="find_junction", target_object="junction")
            return self._explore_for_junctions(state, services)

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
        """Find alignable junction - must be neutral AND outside enemy AOE.

        Prioritizes junctions near the hub (strategic value).
        """
        max_dist = services.safety.max_safe_distance(state, self.risk_tolerance)

        # Get hub position for prioritization
        hub_pos = state.map.stations.get("assembler") or state.map.stations.get("hub")

        # Get all enemy junction positions for AOE check
        enemy_junctions = state.map.get_clips_junctions()

        def is_in_enemy_aoe(pos: tuple[int, int]) -> bool:
            return any(manhattan_distance(pos, ej.position) <= JUNCTION_AOE_RANGE for ej in enemy_junctions)

        # Find alignable junctions: neutral AND outside enemy AOE
        alignable: list[tuple[int, int, StructureInfo]] = []  # (hub_dist, agent_dist, junction)
        for junction in state.map.get_neutral_junctions():
            if is_in_enemy_aoe(junction.position):
                continue  # Can't align - in enemy AOE

            agent_dist = manhattan_distance(state.pos, junction.position)
            if agent_dist > max_dist:
                continue

            # Prioritize junctions near hub
            hub_dist = manhattan_distance(junction.position, hub_pos) if hub_pos else 999
            alignable.append((hub_dist, agent_dist, junction))

        if not alignable:
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
