"""
Miner behavior for Pinky policy.

Miners gather resources from extractors and deposit at aligned buildings.
Strategy: Mine aggressively, deposit when full, only retreat when critical.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from cogames_agents.policy.scripted_agent.pinky.behaviors.base import Services, is_adjacent, manhattan_distance
from cogames_agents.policy.scripted_agent.pinky.types import (
    DEBUG,
    ROLE_TO_STATION,
    DebugInfo,
    RiskTolerance,
    Role,
    StructureInfo,
    StructureType,
)
from mettagrid.simulator import Action

if TYPE_CHECKING:
    from cogames_agents.policy.scripted_agent.pinky.state import AgentState


class MinerBehavior:
    """Miner agent: gather resources and deposit at aligned buildings."""

    role = Role.MINER
    risk_tolerance = RiskTolerance.CONSERVATIVE

    # How many steps to explore before mining without gear
    EXPLORATION_STEPS = 50

    def act(self, state: AgentState, services: Services) -> Action:
        """Execute miner behavior - move toward extractors.

        Mining happens automatically when walking into extractor cells.
        Uses observation-relative coordinates to avoid position drift issues.
        """
        import random

        # Track cargo changes to detect when extraction stops working (inventory full).
        # If cargo doesn't increase for several steps while we have energy to move,
        # the inventory is likely full. This is more robust than tracking cargo capacity.
        if state.total_cargo > state.prev_total_cargo:
            # Cargo increased - reset counter
            state.steps_without_cargo_gain = 0
        elif state.total_cargo == state.prev_total_cargo and state.total_cargo > 0:
            # Cargo unchanged but we have some cargo - increment counter
            state.steps_without_cargo_gain += 1
        elif state.total_cargo < state.prev_total_cargo:
            # Cargo decreased (deposit) - reset counter
            state.steps_without_cargo_gain = 0

        # Update prev_total_cargo for next step
        state.prev_total_cargo = state.total_cargo

        # Priority 1: Critical HP retreat
        if state.hp <= 15:
            if DEBUG:
                print(f"[A{state.agent_id}] MINER: CRITICAL HP={state.hp}, retreating!")
            state.debug_info = DebugInfo(mode="retreat", goal="safety", target_object="safe_zone", signal="hp_critical")
            return self._retreat_to_safety(state, services)

        # Priority 2: Get miner gear if we don't have it
        if not state.miner_gear:
            # First try visible miner_station in current observation
            if state.last_obs is not None:
                result = services.map_tracker.get_direction_to_nearest(
                    state, state.last_obs, frozenset({"miner_station"})
                )
                if result:
                    direction, target_pos = result
                    if DEBUG:
                        print(f"[A{state.agent_id}] MINER: Station visible at {target_pos}, moving {direction}")
                    state.debug_info = DebugInfo(
                        mode="get_gear", goal="miner_station", target_object="miner_station", target_pos=target_pos
                    )
                    return Action(name=f"move_{direction}")

            # Use accumulated map knowledge if station was found
            gear_action = self._get_gear(state, services)
            if gear_action:
                return gear_action

            # During first N steps, explore to find the station before mining
            # After exploration, give up on gear and mine without it
            if state.step < self.EXPLORATION_STEPS:
                if DEBUG and state.step % 10 == 0:
                    print(
                        f"[A{state.agent_id}] MINER: Exploring for station (step {state.step}/{self.EXPLORATION_STEPS})"
                    )
                state.debug_info = DebugInfo(mode="explore", goal="find_station", target_object="miner_station")
                return self._explore_for_station(state, services)
            else:
                if DEBUG and state.step == self.EXPLORATION_STEPS:
                    print(f"[A{state.agent_id}] MINER: Giving up on gear, mining without it")

        # Priority 3: Deposit when cargo is FULL
        cargo_full_reason = self._cargo_full_reason(state)
        if cargo_full_reason:
            if DEBUG:
                print(
                    f"[A{state.agent_id}] MINER: Cargo FULL {state.total_cargo}/{state.cargo_capacity}, "
                    "returning to depot"
                )
            state.debug_info = DebugInfo(
                mode="deposit", goal=f"drop_cargo({state.total_cargo})", target_object="depot", signal=cargo_full_reason
            )
            return self._deposit_resources(state, services)

        # Priority 4: Keep mining - move toward extractors
        # First try to find extractor in current observation (most accurate)
        if state.last_obs is not None:
            result = services.map_tracker.get_direction_to_nearest(
                state,
                state.last_obs,
                frozenset({"carbon_extractor", "oxygen_extractor", "germanium_extractor", "silicon_extractor"}),
            )
            if result:
                direction, target_pos = result
                state.debug_info = DebugInfo(
                    mode="mine", goal="find_extractor", target_object="extractor", target_pos=target_pos
                )
                return Action(name=f"move_{direction}")

        # No extractor visible - use internal map knowledge to navigate to known extractors
        known_extractor = self._find_nearest_extractor(state, services)
        if known_extractor:
            if DEBUG:
                print(
                    f"[A{state.agent_id}] MINER: No extractor visible, navigating to known {known_extractor.name} "
                    f"at {known_extractor.position}"
                )
            state.debug_info = DebugInfo(
                mode="mine",
                goal="navigate_to_known_extractor",
                target_object=known_extractor.resource_type or "extractor",
                target_pos=known_extractor.position,
            )
            return services.navigator.move_to(state, known_extractor.position, reach_adjacent=True)

        # Fallback: random walk exploration to find new extractors
        state.debug_info = DebugInfo(mode="explore", goal="random_walk", target_object="-")
        directions = ["north", "south", "east", "west"]
        return Action(name=f"move_{random.choice(directions)}")

    def needs_gear(self, state: AgentState) -> bool:
        """Miners need miner gear for +40 cargo capacity."""
        return not state.miner_gear

    def has_resources_to_act(self, state: AgentState) -> bool:
        """Miners don't need resources to mine."""
        return True

    # How many steps without cargo gain before assuming inventory is full
    STEPS_TO_ASSUME_FULL = 3

    def _cargo_full_reason(self, state: AgentState) -> str:
        """Check if cargo is full and return the reason signal.

        Returns:
            - "extract_failed_cargo_full" if no cargo gain for several steps (extraction stopped working)
            - "cargo_at_capacity" if cargo >= computed capacity
            - "" if cargo is not full
        """
        # If we have cargo and haven't gained any for several steps, assume full
        if state.total_cargo > 0 and state.steps_without_cargo_gain >= self.STEPS_TO_ASSUME_FULL:
            if DEBUG:
                print(
                    f"[A{state.agent_id}] MINER: No cargo gain for {state.steps_without_cargo_gain} steps, "
                    f"assuming full (cargo={state.total_cargo})"
                )
            return "extract_failed_cargo_full"
        # Fallback to capacity check
        if state.total_cargo >= state.cargo_capacity:
            return "cargo_at_capacity"
        return ""

    def _retreat_to_safety(self, state: AgentState, services: Services) -> Action:
        """Return to nearest safe zone."""
        safe_pos = services.safety.nearest_safe_zone(state)
        if safe_pos is None:
            # No known safe zone, just try to find any junction
            for junction in state.map.get_junctions():
                safe_pos = junction.position
                break

        if safe_pos is None:
            state.debug_info = DebugInfo(mode="retreat", goal="explore_for_safety", target_object="-")
            return services.navigator.explore(state)

        # If we have cargo and are adjacent to safe building, deposit
        if state.total_cargo > 0 and is_adjacent(state.pos, safe_pos):
            state.debug_info = DebugInfo(
                mode="retreat", goal="deposit_and_heal", target_object="safe_zone", target_pos=safe_pos
            )
            return services.navigator.use_object_at(state, safe_pos)

        state.debug_info = DebugInfo(
            mode="retreat", goal="reach_safety", target_object="safe_zone", target_pos=safe_pos
        )
        return services.navigator.move_to(state, safe_pos, reach_adjacent=True)

    def _explore_for_station(self, state: AgentState, services: Services) -> Action:
        """Explore systematically to find the miner station.

        Explores in a small box pattern around spawn to find nearby station.
        Pattern stays within ~5 steps of spawn to avoid wandering too far.
        """
        # Small exploration pattern: 3 steps in each direction, then return
        # This keeps the agent close to spawn while checking all directions
        pattern = [
            "east",
            "east",
            "east",  # Check east (stations often near spawn)
            "west",
            "west",
            "west",
            "south",
            "south",
            "south",  # Go back and check south
            "north",
            "north",
            "north",
            "west",
            "west",
            "west",  # Go back and check west
            "east",
            "east",
            "east",
            "north",
            "north",
            "north",  # Go back and check north
            "south",
            "south",
            "south",  # Return to spawn area
        ]
        # Start exploration index from step 2 (step 1 is vibe change)
        explore_step = max(0, state.step - 2)
        idx = explore_step % len(pattern)
        return Action(name=f"move_{pattern[idx]}")

    def _get_gear(self, state: AgentState, services: Services) -> Optional[Action]:
        """Go get miner gear from station."""
        station_name = ROLE_TO_STATION[Role.MINER]
        station_pos = state.map.stations.get(station_name)

        if station_pos is None:
            # Station not found yet
            return None

        dist = manhattan_distance(state.pos, station_pos)

        # If ON the station (dist=0), we should have received gear from walking in.
        # If gear not received yet, noop to let the game state update.
        if state.pos == station_pos:
            if DEBUG:
                print(f"[A{state.agent_id}] MINER: ON station at {station_pos}, waiting for gear")
            state.debug_info = DebugInfo(
                mode="get_gear", goal="on_station", target_object="miner_station", target_pos=station_pos
            )
            # Return None to let the miner continue with other priorities (explore/mine)
            # The gear should have been granted when we walked onto the station
            return None

        if is_adjacent(state.pos, station_pos):
            if DEBUG:
                print(f"[A{state.agent_id}] MINER: Getting gear from {station_pos}")
            state.debug_info = DebugInfo(
                mode="get_gear", goal="use_station", target_object="miner_station", target_pos=station_pos
            )
            return services.navigator.use_object_at(state, station_pos)

        if DEBUG and state.step % 10 == 0:
            print(f"[A{state.agent_id}] MINER: Moving to station at {station_pos} (dist={dist})")
        state.debug_info = DebugInfo(
            mode="get_gear", goal=f"move_to_station(dist={dist})", target_object="miner_station", target_pos=station_pos
        )
        return services.navigator.move_to(state, station_pos, reach_adjacent=True)

    def _deposit_resources(self, state: AgentState, services: Services) -> Action:
        """Deposit resources at nearest COGS-ALIGNED hub or junction only.

        Uses map knowledge (which tracks alignment) to find cogs-aligned depots.
        Observation-based nav doesn't check alignment, so we rely on map knowledge.
        Only considers cogs-aligned structures (hub or cogs junctions), NOT neutral.
        """
        # Use map knowledge - find nearest COGS-ALIGNED depot only
        # Map knowledge correctly tracks alignment changes from observations
        candidates: list[tuple[int, tuple[int, int]]] = []

        # Only cogs-aligned junctions (NOT neutral, NOT clips)
        for junction in state.map.get_cogs_junctions():
            dist = manhattan_distance(state.pos, junction.position)
            candidates.append((dist, junction.position))

        # Hub/assembler is always cogs-aligned
        assembler_pos = state.map.stations.get("assembler")
        if assembler_pos:
            dist = manhattan_distance(state.pos, assembler_pos)
            candidates.append((dist, assembler_pos))

        if not candidates:
            if DEBUG:
                # Show what structures we DO know about
                struct_types: dict[str, int] = {}
                for s in state.map.structures.values():
                    t = s.structure_type.name
                    struct_types[t] = struct_types.get(t, 0) + 1
                cogs_junctions = len(state.map.get_cogs_junctions())
                all_junctions = len(state.map.get_junctions())
                # Also show junction alignments
                junction_alignments = [(j.position, j.alignment) for j in state.map.get_junctions()]
                print(
                    f"[A{state.agent_id}] MINER: No COGS depot found "
                    f"(cogs_junctions={cogs_junctions}, all_junctions={all_junctions}), "
                    f"structures={struct_types}, junction_alignments={junction_alignments}, exploring"
                )
            state.debug_info = DebugInfo(mode="deposit", goal="explore_for_cogs_depot", target_object="-")
            return services.navigator.explore(state)

        candidates.sort(key=lambda x: x[0])
        depot_pos = candidates[0][1]
        dist = candidates[0][0]

        # If we're ON or adjacent to the depot, try to interact with it
        if state.pos == depot_pos or is_adjacent(state.pos, depot_pos):
            # Verify depot is still cogs-aligned (alignment may have changed)
            struct = state.map.get_structure_at(depot_pos)
            if struct is not None and struct.structure_type == StructureType.JUNCTION:
                if not struct.is_cogs_aligned():
                    if DEBUG:
                        print(
                            f"[A{state.agent_id}] MINER: Depot at {depot_pos} is no longer cogs-aligned "
                            f"(alignment={struct.alignment}), finding new depot"
                        )
                    # Depot is no longer cogs-aligned - recurse to find a new one
                    # Remove from candidates and try again
                    state.debug_info = DebugInfo(
                        mode="deposit", goal="depot_lost_alignment", target_object="-", signal="alignment_changed"
                    )
                    return services.navigator.explore(state)

            if DEBUG:
                print(f"[A{state.agent_id}] MINER: At cogs depot {depot_pos}, depositing cargo={state.total_cargo}")
            state.debug_info = DebugInfo(
                mode="deposit", goal="use_cogs_depot", target_object="cogs_depot", target_pos=depot_pos
            )
            return services.navigator.use_object_at(state, depot_pos)

        if DEBUG and state.step % 10 == 0:
            print(
                f"[A{state.agent_id}] MINER: Moving to cogs depot at {depot_pos}, "
                f"dist={dist}, cargo={state.total_cargo}, agent_pos={state.pos}"
            )

        state.debug_info = DebugInfo(
            mode="deposit", goal=f"move_to_cogs_depot(dist={dist})", target_object="cogs_depot", target_pos=depot_pos
        )
        return services.navigator.move_to(state, depot_pos, reach_adjacent=True)

    def _move_toward_extractor_from_obs(self, state: AgentState) -> Action:
        """Move toward nearest extractor visible in current observation.

        Uses relative observation positions, not world coordinates.
        Center is at (obs_hr, obs_wr) = (5, 5) typically.
        """
        import random

        # Find closest extractor in state.map.structures by iterating all
        # and using relative position calculation from recent observation
        # But since coordinates are broken, use random walk with exploration

        directions = ["north", "south", "east", "west"]
        random.shuffle(directions)
        return Action(name=f"move_{directions[0]}")

    def _find_nearest_extractor(
        self, state: AgentState, services: Services, exclude: Optional[tuple[int, int]] = None
    ) -> Optional[StructureInfo]:
        """Find nearest usable extractor - no overly conservative distance limits."""
        extractors = state.map.get_usable_extractors()

        if not extractors:
            return None

        # Use a generous max distance based on HP
        # Allow traveling up to HP/2 steps (one way), leaving buffer for return
        max_dist = max(50, state.hp // 2)

        if DEBUG and state.step % 50 == 0:
            struct_types = {}
            for s in state.map.structures.values():
                t = s.structure_type.name
                struct_types[t] = struct_types.get(t, 0) + 1
            print(
                f"[A{state.agent_id}] MINER: _find_nearest_extractor: "
                f"max_dist={max_dist}, extractors={len(extractors)}, hp={state.hp}, "
                f"structures={len(state.map.structures)}, types={struct_types}"
            )

        # Filter and sort by distance
        candidates: list[tuple[int, StructureInfo]] = []
        for ext in extractors:
            if exclude and ext.position == exclude:
                continue
            dist = manhattan_distance(state.pos, ext.position)
            if dist <= max_dist:
                candidates.append((dist, ext))

        if not candidates:
            # If no extractors in range, return the closest one anyway
            all_candidates = []
            for ext in extractors:
                if exclude and ext.position == exclude:
                    continue
                dist = manhattan_distance(state.pos, ext.position)
                all_candidates.append((dist, ext))
            if all_candidates:
                all_candidates.sort(key=lambda x: x[0])
                return all_candidates[0][1]
            return None

        candidates.sort(key=lambda x: x[0])
        return candidates[0][1]

    def _get_nearest_depot(self, state: AgentState, services: Services) -> Optional[tuple[int, int]]:
        """Get nearest COGS-ALIGNED hub/junction for deposit."""
        candidates: list[tuple[int, tuple[int, int]]] = []

        # Assembler/hub (always cogs-aligned)
        assembler_pos = state.map.stations.get("assembler")
        if assembler_pos:
            dist = manhattan_distance(state.pos, assembler_pos)
            candidates.append((dist, assembler_pos))

        # Only cogs-aligned junctions (NOT neutral, NOT clips)
        for junction in state.map.get_cogs_junctions():
            dist = manhattan_distance(state.pos, junction.position)
            candidates.append((dist, junction.position))

        if not candidates:
            return None

        candidates.sort(key=lambda x: x[0])
        return candidates[0][1]
