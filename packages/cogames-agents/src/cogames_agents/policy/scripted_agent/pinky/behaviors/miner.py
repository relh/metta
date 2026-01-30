"""
Miner behavior for Pinky policy.

Miners gather resources from extractors and deposit at aligned buildings.
Strategy: Mine aggressively, deposit when full, only retreat when critical.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from cogames_agents.policy.scripted_agent.pinky.behaviors.base import (
    Services,
    explore_for_station,
    is_adjacent,
    manhattan_distance,
)
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
    EXPLORATION_STEPS = 100

    # How many ticks to mine/explore before retrying gear station
    GEAR_RETRY_INTERVAL = 100

    # How often to clear the failed extractors list (allow retry)
    FAILED_EXTRACTOR_RETRY_INTERVAL = 200

    def act(self, state: AgentState, services: Services) -> Action:
        """Execute miner behavior - move toward extractors.

        Mining happens automatically when walking into extractor cells.
        Uses observation-relative coordinates to avoid position drift issues.
        """

        # Periodically clear failed extractors to allow retry (they may have replenished)
        if state.step % self.FAILED_EXTRACTOR_RETRY_INTERVAL == 0:
            state.nav.failed_extractors.clear()

        # Track cargo changes to detect when extraction stops working (inventory full).
        # If cargo doesn't increase for several steps while we have energy to move,
        # the inventory is likely full. This is more robust than tracking cargo capacity.
        cargo_gained = state.total_cargo > state.prev_total_cargo
        if cargo_gained:
            # Cargo increased - reset counter and clear current target (successfully mined)
            state.steps_without_cargo_gain = 0
            state.nav.steps_at_current_extractor = 0
            # Clear the current target - we'll pick a new one next step
            state.nav.current_extractor_target = None
        elif state.total_cargo == state.prev_total_cargo and state.total_cargo > 0:
            # Cargo unchanged but we have some cargo - increment counter
            state.steps_without_cargo_gain += 1
        elif state.total_cargo < state.prev_total_cargo:
            # Cargo decreased (deposit) - reset counter
            state.steps_without_cargo_gain = 0

        # Track time at current extractor target to detect empty/stuck extractors
        if state.nav.current_extractor_target is not None:
            target = state.nav.current_extractor_target
            dist = manhattan_distance(state.pos, target)
            if dist <= 1:  # At or adjacent to target
                state.nav.steps_at_current_extractor += 1
                # If we've been at this extractor for 5+ steps without cargo gain, mark it as failed
                if state.nav.steps_at_current_extractor >= 5 and not cargo_gained:
                    if DEBUG:
                        print(
                            f"[A{state.agent_id}] MINER: Extractor at {target} appears empty/blocked, "
                            f"marking as failed after {state.nav.steps_at_current_extractor} steps"
                        )
                    state.nav.failed_extractors.add(target)
                    state.nav.current_extractor_target = None
                    state.nav.steps_at_current_extractor = 0

        # Update prev_total_cargo for next step
        state.prev_total_cargo = state.total_cargo

        # Priority 0: Check for stuck patterns and handle escape mode (via navigator)
        escape_action = services.navigator.check_and_handle_escape(state)
        if escape_action:
            debug_info = services.navigator.get_escape_debug_info(state)
            state.debug_info = DebugInfo(**debug_info)
            return escape_action

        # Priority 1: Critical HP retreat
        if state.hp <= 15:
            if DEBUG:
                print(f"[A{state.agent_id}] MINER: CRITICAL HP={state.hp}, retreating!")
            state.debug_info = DebugInfo(mode="retreat", goal="safety", target_object="safe_zone", signal="hp_critical")
            return self._retreat_to_safety(state, services)

        # Priority 2: Get miner gear if we don't have it
        # Track gear state for detecting gear loss
        has_gear_now = state.miner_gear
        just_lost_gear = state.had_gear_last_step and not has_gear_now
        state.had_gear_last_step = has_gear_now

        if not state.miner_gear:
            # Check if we should try to get gear now
            ticks_since_last_attempt = state.step - state.last_gear_attempt_step

            # Try to get gear if:
            # 1. Just lost gear (immediately go home)
            # 2. Initial exploration period
            # 3. 200 ticks have passed since last attempt
            should_try_gear = (
                just_lost_gear
                or state.step < self.EXPLORATION_STEPS
                or ticks_since_last_attempt >= self.GEAR_RETRY_INTERVAL
            )

            if should_try_gear:
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

                # Station not found - explore for it
                if DEBUG and state.step % 10 == 0:
                    print(f"[A{state.agent_id}] MINER: Exploring for station (step {state.step})")
                state.debug_info = DebugInfo(mode="explore", goal="find_station", target_object="miner_station")
                return self._explore_for_station(state, services)

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
        # Build set of positions to exclude: known-empty + recently failed extractors
        excluded_extractors: set[tuple[int, int]] = set(state.nav.failed_extractors)
        for pos, struct in state.map.structures.items():
            if struct.structure_type == StructureType.EXTRACTOR and not struct.is_usable_extractor():
                excluded_extractors.add(pos)

        if state.last_obs is not None:
            # Get the resource type with the lowest communal amount
            lowest_resource = self._get_lowest_communal_resource(state)
            all_extractor_types = {"carbon_extractor", "oxygen_extractor", "germanium_extractor", "silicon_extractor"}

            # Build preferred types (lowest communal resource)
            if lowest_resource:
                preferred_types = {f"{lowest_resource}_extractor"}
            else:
                preferred_types = set()

            # Try preferred types first (lowest communal resource)
            result = None
            if preferred_types:
                result = services.map_tracker.get_direction_to_nearest(
                    state,
                    state.last_obs,
                    frozenset(preferred_types),
                    exclude_positions=excluded_extractors,
                )

            # Fall back to any extractor type
            if not result:
                result = services.map_tracker.get_direction_to_nearest(
                    state,
                    state.last_obs,
                    frozenset(all_extractor_types),
                    exclude_positions=excluded_extractors,
                )

            if result:
                direction, target_pos = result
                # Track this as our current target
                if state.nav.current_extractor_target != target_pos:
                    state.nav.current_extractor_target = target_pos
                    state.nav.steps_at_current_extractor = 0
                # Found a visible mineral - remember this step
                state.nav.explore_last_mineral_step = state.step
                state.debug_info = DebugInfo(
                    mode="mine", goal="find_extractor", target_object="extractor", target_pos=target_pos
                )
                return Action(name=f"move_{direction}")

        # No extractor visible - use internal map knowledge to navigate to known extractors
        known_extractor = self._find_nearest_extractor(state, services, excluded_extractors)
        if known_extractor:
            # Track this as our current target
            if state.nav.current_extractor_target != known_extractor.position:
                state.nav.current_extractor_target = known_extractor.position
                state.nav.steps_at_current_extractor = 0
            # Found a mineral - remember this step
            state.nav.explore_last_mineral_step = state.step

            # Track this resource type for rotation
            res_type = known_extractor.resource_type
            if res_type:
                self._record_resource_gathered(state, res_type)

            if DEBUG:
                print(
                    f"[A{state.agent_id}] MINER: No extractor visible, navigating to known {known_extractor.name} "
                    f"at {known_extractor.position}"
                )
            # Format: "carbon:100" or "extractor" if no resource type
            res_type_name = res_type or "extractor"
            inv_amt = known_extractor.inventory_amount
            target_name = f"{res_type_name}:{inv_amt}" if inv_amt >= 0 else res_type_name
            state.debug_info = DebugInfo(
                mode="mine",
                goal="navigate_to_known_extractor",
                target_object=target_name,
                target_pos=known_extractor.position,
            )
            return services.navigator.move_to(state, known_extractor.position, reach_adjacent=True)

        # No minerals found - explore with expanding radius
        return self._explore_for_minerals(state, services)

    def needs_gear(self, state: AgentState) -> bool:
        """Miners need miner gear for +40 cargo capacity."""
        return not state.miner_gear

    def has_resources_to_act(self, state: AgentState) -> bool:
        """Miners don't need resources to mine."""
        return True

    def _record_resource_gathered(self, state: AgentState, resource_type: str) -> None:
        """Record that we gathered a resource type for rotation tracking.

        Maintains a list of the last 4 resource types gathered.
        When the miner fills up on one type, it will prefer other types.
        """
        recent = state.nav.last_resource_types
        # Only add if different from the most recent one (avoid duplicates from same extractor)
        if not recent or recent[0] != resource_type:
            recent.insert(0, resource_type)
            # Keep only the last 4 types
            if len(recent) > 4:
                recent.pop()

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
        """Explore to find the miner station."""
        # Miners explore south since stations are south of spawn in the hub
        return explore_for_station(state, services, primary_direction="south")

    def _explore_for_minerals(self, state: AgentState, services: Services) -> Action:
        """Explore to find new mineral extractors.

        Uses the navigator's explore method with direction bias to spread out
        from the base and find new resources. Tracks exploration direction to
        avoid circling.
        """
        # Pick a consistent exploration direction based on agent ID to spread miners out
        # Agent 0 explores south, 1 explores east, 2 explores west, etc.
        directions = ["south", "east", "west", "north"]
        base_direction = directions[state.agent_id % len(directions)]

        # If we've been exploring the same direction for a while without finding minerals,
        # switch to a different direction
        steps_since_mineral = state.step - state.nav.explore_last_mineral_step
        if steps_since_mineral > 100:
            # Rotate to next direction
            dir_idx = (directions.index(base_direction) + (steps_since_mineral // 100)) % len(directions)
            base_direction = directions[dir_idx]
            if DEBUG:
                print(
                    f"[A{state.agent_id}] MINER: No minerals for {steps_since_mineral} steps, "
                    f"exploring {base_direction}"
                )

        state.debug_info = DebugInfo(
            mode="explore",
            goal=base_direction,
            target_object="-",
        )

        # Use navigator's explore which handles pathfinding around obstacles
        return services.navigator.explore(state, direction_bias=base_direction)

    def _get_gear(self, state: AgentState, services: Services) -> Optional[Action]:
        """Go get miner gear from station."""
        station_name = ROLE_TO_STATION[Role.MINER]
        station_pos = state.map.stations.get(station_name)

        if station_pos is None:
            # Station not found yet
            return None

        dist = manhattan_distance(state.pos, station_pos)

        # If ON the station (dist=0), we should have received gear from walking in.
        # If gear not received yet, record this attempt and let miner continue mining.
        # After GEAR_RETRY_INTERVAL ticks, they'll try again.
        if state.pos == station_pos:
            if DEBUG:
                print(f"[A{state.agent_id}] MINER: ON station at {station_pos}, no gear - will mine and retry later")
            state.debug_info = DebugInfo(
                mode="get_gear", goal="on_station_no_gear", target_object="miner_station", target_pos=station_pos
            )
            # Record this attempt - miner will mine for GEAR_RETRY_INTERVAL ticks then retry
            state.last_gear_attempt_step = state.step
            # Return None to let the miner continue with mining
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

        # Hub is always cogs-aligned
        hub_pos = state.map.stations.get("hub")
        if hub_pos:
            dist = manhattan_distance(state.pos, hub_pos)
            candidates.append((dist, hub_pos))

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

    def _get_lowest_communal_resource(self, state: AgentState) -> Optional[str]:
        """Get the resource type with the lowest communal amount.

        Returns:
            Resource type name (carbon, oxygen, germanium, silicon) or None if all are 0.
        """
        resources = {
            "carbon": state.collective_carbon,
            "oxygen": state.collective_oxygen,
            "germanium": state.collective_germanium,
            "silicon": state.collective_silicon,
        }
        # Find the minimum (break ties alphabetically for consistency)
        min_amount = min(resources.values())
        for name in sorted(resources.keys()):
            if resources[name] == min_amount:
                return name
        return None

    def _find_nearest_extractor(
        self,
        state: AgentState,
        services: Services,
        exclude_positions: Optional[set[tuple[int, int]]] = None,
    ) -> Optional[StructureInfo]:
        """Find nearest usable extractor, preferring the resource with lowest communal amount.

        Resource prioritization logic:
        - Check communal resource levels and prefer the resource type with the lowest amount
        - Among preferred types, pick the nearest one
        - Fall back to nearest of any type if no preferred available

        Args:
            exclude_positions: Set of extractor positions to exclude (empty/failed ones)
        """
        extractors = state.map.get_usable_extractors()

        if not extractors:
            return None

        # Combine with failed extractors to exclude
        excluded = exclude_positions or set()
        excluded = excluded | state.nav.failed_extractors

        # Use step-based range limit (encourages gradual expansion)
        # Also cap by HP to avoid stranding
        step_limit = services.safety.step_based_range_limit(state.step)
        hp_limit = max(50, state.hp // 2)
        max_dist = min(step_limit, hp_limit)

        # Get the resource type with the lowest communal amount
        lowest_resource = self._get_lowest_communal_resource(state)

        if DEBUG and state.step % 50 == 0:
            struct_types = {}
            for s in state.map.structures.values():
                t = s.structure_type.name
                struct_types[t] = struct_types.get(t, 0) + 1
            print(
                f"[A{state.agent_id}] MINER: _find_nearest_extractor: "
                f"max_dist={max_dist} (step_limit={step_limit}, hp_limit={hp_limit}), "
                f"extractors={len(extractors)}, hp={state.hp}, "
                f"lowest_communal={lowest_resource} "
                f"(C={state.collective_carbon}, O={state.collective_oxygen}, "
                f"G={state.collective_germanium}, S={state.collective_silicon})"
            )

        # Filter extractors by distance and categorize by preference
        # Prefer extractors that produce the lowest communal resource
        preferred_candidates: list[tuple[int, StructureInfo]] = []  # Lowest communal resource type
        fallback_candidates: list[tuple[int, StructureInfo]] = []  # Other resource types

        for ext in extractors:
            if ext.position in excluded:
                continue
            dist = manhattan_distance(state.pos, ext.position)
            if dist > max_dist:
                continue

            res_type = ext.resource_type
            if res_type and res_type == lowest_resource:
                preferred_candidates.append((dist, ext))
            else:
                fallback_candidates.append((dist, ext))

        # Return nearest preferred, or nearest fallback
        if preferred_candidates:
            preferred_candidates.sort(key=lambda x: x[0])
            return preferred_candidates[0][1]

        if fallback_candidates:
            fallback_candidates.sort(key=lambda x: x[0])
            return fallback_candidates[0][1]

        # No extractors in range - return the closest one anyway (any type)
        all_candidates = []
        for ext in extractors:
            if ext.position in excluded:
                continue
            dist = manhattan_distance(state.pos, ext.position)
            res_type = ext.resource_type
            # Still prefer lowest communal resource type even when out of range
            priority = 0 if (res_type and res_type == lowest_resource) else 1
            all_candidates.append((priority, dist, ext))

        if all_candidates:
            all_candidates.sort(key=lambda x: (x[0], x[1]))  # Sort by priority, then distance
            return all_candidates[0][2]

        return None

    def _get_nearest_depot(self, state: AgentState, services: Services) -> Optional[tuple[int, int]]:
        """Get nearest COGS-ALIGNED hub/junction for deposit."""
        candidates: list[tuple[int, tuple[int, int]]] = []

        # Hub (always cogs-aligned)
        hub_pos = state.map.stations.get("hub")
        if hub_pos:
            dist = manhattan_distance(state.pos, hub_pos)
            candidates.append((dist, hub_pos))

        # Only cogs-aligned junctions (NOT neutral, NOT clips)
        for junction in state.map.get_cogs_junctions():
            dist = manhattan_distance(state.pos, junction.position)
            candidates.append((dist, junction.position))

        if not candidates:
            return None

        candidates.sort(key=lambda x: x[0])
        return candidates[0][1]
