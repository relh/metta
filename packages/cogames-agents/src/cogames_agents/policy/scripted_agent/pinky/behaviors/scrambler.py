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

    # How many ticks at same position before switching to explore
    STUCK_THRESHOLD = 5  # Fast detection to avoid wasting time on blocked paths

    def act(self, state: AgentState, services: Services) -> Action:
        """Execute scrambler behavior."""
        # Track gear state for detecting gear loss
        has_gear_now = state.scrambler_gear
        just_lost_gear = state.had_gear_last_step and not has_gear_now
        state.had_gear_last_step = has_gear_now

        # Track stuck detection: count consecutive steps at same position
        if state.pos == state.last_position:
            state.steps_at_same_position += 1
        else:
            state.steps_at_same_position = 0
            state.last_position = state.pos

        # Priority 0: If stuck for too long, try random direction to break out
        if state.steps_at_same_position >= self.STUCK_THRESHOLD:
            if DEBUG:
                print(f"[A{state.agent_id}] SCRAMBLER: STUCK for {state.steps_at_same_position} ticks, random break")
            state.debug_info = DebugInfo(mode="explore", goal="unstuck", target_object="-", signal="stuck")
            state.steps_at_same_position = 0
            # Try random direction to escape - rotate through based on step
            directions = ["north", "south", "east", "west"]
            direction = directions[(state.step + state.agent_id) % 4]
            return Action(name=f"move_{direction}")

        # Priority 1: Retreat only if critically low (scramblers are tanky)
        # Only retreat when HP drops below 30 (they start with 50)
        if state.hp < 30:
            if DEBUG:
                print(f"[A{state.agent_id}] SCRAMBLER: Retreating! HP={state.hp}")
            state.debug_info = DebugInfo(mode="retreat", goal="safety", target_object="safe_zone", signal="hp_low")
            return self._retreat_to_safety(state, services)

        # Priority 2: Get hearts if empty (needed to scramble)
        # Hearts are more important than gear - can scramble without gear
        if not self.has_resources_to_act(state):
            return self._get_hearts(state, services)

        # Priority 3: Get gear if missing AND station is very close
        # Gear gives +200 HP but isn't essential
        if self.needs_gear(state):
            station_name = ROLE_TO_STATION[Role.SCRAMBLER]
            station_pos = state.map.stations.get(station_name)
            if station_pos is not None:
                dist = manhattan_distance(state.pos, station_pos)
                # Only get gear if very close (< 5 steps) or just lost it
                if dist < 5 or just_lost_gear:
                    return self._get_gear(state, services)

        # Priority 4: Hunt and scramble enemy junctions
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
        """Explore systematically to find the scrambler station.

        Uses an expanding spiral pattern, offset by agent_id to spread agents out.
        """
        # Direction sequences for different starting directions
        direction_orders = [
            ["east", "south", "west", "north"],
            ["south", "west", "north", "east"],
            ["west", "north", "east", "south"],
            ["north", "east", "south", "west"],
        ]
        dirs = direction_orders[state.agent_id % 4]

        pattern: list[str] = []
        for ring in range(1, 8):
            steps = ring * 2
            pattern.extend([dirs[0]] * steps)
            pattern.extend([dirs[1]] * steps)
            pattern.extend([dirs[2]] * (steps + 2))
            pattern.extend([dirs[3]] * (steps + 2))

        explore_step = max(0, state.step - 2)
        idx = explore_step % len(pattern)
        return Action(name=f"move_{pattern[idx]}")

    def _explore_for_enemy_junctions(self, state: AgentState, services: Services) -> Action:
        """Explore aggressively to find clips junctions.

        Uses random direction selection (similar to random policy which navigates better).
        """
        import random

        directions = ["north", "south", "east", "west"]
        direction = random.choice(directions)
        return Action(name=f"move_{direction}")

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

        Strategy: Only target clips-aligned junctions (save hearts for real scrambles).
        """
        # First try to find junction in current observation
        if state.last_obs is not None:
            result = services.map_tracker.get_direction_to_nearest(
                state, state.last_obs, frozenset({"junction", "charger", "supply_depot"})
            )
            if result:
                direction, target_pos = result
                struct = state.map.get_structure_at(target_pos)

                # ONLY target clips-aligned junctions (don't waste hearts on neutral)
                if struct is not None and struct.is_clips_aligned():
                    if DEBUG:
                        print(f"[A{state.agent_id}] SCRAMBLER: Enemy junction at {target_pos}, moving {direction}")
                    state.debug_info = DebugInfo(
                        mode="scramble", goal="enemy_junction", target_object="junction", target_pos=target_pos
                    )
                    return Action(name=f"move_{direction}")
                elif struct is None or struct.alignment is None:
                    # Unknown alignment - move toward to discover
                    state.debug_info = DebugInfo(
                        mode="explore", goal="check_junction", target_object="junction", target_pos=target_pos
                    )
                    return Action(name=f"move_{direction}")

        # Fall back to map knowledge - find known clips junctions
        target = self._find_best_target(state, services)

        if target is None:
            # No known enemy junctions - explore toward map edges to find them
            if DEBUG and state.step % 50 == 0:
                clips_count = len(state.map.get_clips_junctions())
                all_count = len(state.map.get_junctions())
                print(f"[A{state.agent_id}] SCRAMBLER: No enemy junctions found (clips={clips_count}, all={all_count})")
            state.debug_info = DebugInfo(mode="explore", goal="find_enemy_junction", target_object="junction")
            # Explore toward map edges where clips junctions likely are
            return self._explore_for_enemy_junctions(state, services)

        dist = manhattan_distance(state.pos, target.position)

        if is_adjacent(state.pos, target.position):
            if DEBUG:
                print(f"[A{state.agent_id}] SCRAMBLER: Scrambling junction at {target.position}")
            state.debug_info = DebugInfo(
                mode="scramble", goal="use_junction", target_object="junction", target_pos=target.position
            )
            return services.navigator.use_object_at(state, target.position)

        state.debug_info = DebugInfo(
            mode="scramble", goal=f"move_to_junction(dist={dist})", target_object="junction", target_pos=target.position
        )
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
