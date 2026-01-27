"""
MapTracker service for Pinky policy.

Processes observations and maintains map knowledge.
"""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING, Optional, Union

from cogames_agents.policy.scripted_agent.pinky.types import (
    DEBUG,
    ROLE_TO_STATION,
    CellType,
    StructureInfo,
    StructureType,
)

if TYPE_CHECKING:
    from cogames_agents.policy.scripted_agent.pinky.state import AgentState
    from mettagrid.policy.policy_env_interface import PolicyEnvInterface
    from mettagrid.simulator.interface import AgentObservation


class MapTracker:
    """Processes observations and maintains map knowledge."""

    def __init__(self, policy_env_info: PolicyEnvInterface):
        self._obs_hr = policy_env_info.obs_height // 2
        self._obs_wr = policy_env_info.obs_width // 2
        self._tag_names = policy_env_info.tag_id_to_name
        if DEBUG:
            print(f"[MAP] Available tags: {list(self._tag_names.values())}")
        self._spatial_feature_names = {"tag", "cooldown_remaining", "clipped", "remaining_uses", "collective"}
        self._agent_feature_key_by_name = {"agent:group": "agent_group", "agent:frozen": "agent_frozen"}

        # Build collective ID to name mapping from tags
        # Tags like "cogs" and "clips" indicate collective names
        # Collective IDs in observations correspond to these names (alphabetically sorted)
        self._collective_names = ["clips", "cogs"]  # Alphabetically sorted - matches mettagrid convention
        self._cogs_collective_id: Optional[int] = None
        self._clips_collective_id: Optional[int] = None
        for i, name in enumerate(self._collective_names):
            if name == "cogs":
                self._cogs_collective_id = i
            elif name == "clips":
                self._clips_collective_id = i
        if DEBUG:
            print(f"[MAP] Collective IDs: cogs={self._cogs_collective_id}, clips={self._clips_collective_id}")

        # Derive vibe names from action names (change_vibe_<vibe_name>)
        # The order of vibes in action names matches the vibe IDs in observations
        self._vibe_names: list[str] = []
        for action_name in policy_env_info.action_names:
            if action_name.startswith("change_vibe_"):
                vibe_name = action_name[len("change_vibe_") :]
                self._vibe_names.append(vibe_name)

    def update(self, state: AgentState, obs: AgentObservation) -> None:
        """Parse observation and update map knowledge."""
        # Clear agent occupancy each step
        state.map.agent_occupancy.clear()

        # Read inventory from observation
        self._read_inventory(state, obs)

        # Compute position from object matching (more reliable than action tracking)
        self._compute_position_from_observation(state, obs)

        # Parse spatial features from observation (now using corrected position)
        position_features = self._parse_observation(state, obs)

        # Mark observed cells as explored and FREE
        self._mark_explored(state)

        # Process discovered objects
        for pos, features in position_features.items():
            if "tags" not in features:
                continue

            obj_name = self._get_object_name(features)
            if DEBUG and state.step <= 10 and pos == (101, 108) and state.agent_id == 0:
                tags = features.get("tags", [])
                tag_names = [self._tag_names.get(t, f"?{t}") for t in tags]
                print(f"[A{state.agent_id}] MAP: FOUND pos={pos} tags={tag_names} -> '{obj_name}'")
            self._process_object(state, pos, obj_name, features)

    def _read_inventory(self, state: AgentState, obs: AgentObservation) -> None:
        """Read inventory and vibe from observation center cell."""
        inv: dict[str, int] = {}
        vibe_id = 0

        center_r, center_c = self._obs_hr, self._obs_wr
        for tok in obs.tokens:
            if tok.row() == center_r and tok.col() == center_c:
                feature_name = tok.feature.name
                if feature_name.startswith("inv:"):
                    resource_name = feature_name[4:]
                    inv[resource_name] = tok.value
                elif feature_name == "vibe":
                    vibe_id = tok.value

        # Update inventory
        state.energy = inv.get("energy", 0)
        state.hp = inv.get("hp", 100)
        state.carbon = inv.get("carbon", 0)
        state.oxygen = inv.get("oxygen", 0)
        state.germanium = inv.get("germanium", 0)
        state.silicon = inv.get("silicon", 0)
        state.heart = inv.get("heart", 0)
        state.influence = inv.get("influence", 0)

        # Update gear
        state.miner_gear = inv.get("miner", 0) > 0
        state.scout_gear = inv.get("scout", 0) > 0
        state.aligner_gear = inv.get("aligner", 0) > 0
        state.scrambler_gear = inv.get("scrambler", 0) > 0

        # Update vibe
        state.vibe = self._get_vibe_name(vibe_id)

    def _compute_position_from_observation(self, state: AgentState, obs: AgentObservation) -> None:
        """Compute agent position by matching known objects in observation.

        More reliable than action-based tracking because it:
        - Doesn't matter if moves succeed or fail
        - Self-corrects any position drift
        - Based on actual observation, not assumptions

        Strategy: Find objects in observation, match to known world positions,
        derive agent position from the offset.
        """
        # Collect observed objects with their observation-relative positions
        # Format: {obs_pos: obj_name}
        observed_objects: dict[tuple[int, int], str] = {}

        for tok in obs.tokens:
            if tok.feature.name != "tag":
                continue

            obs_r, obs_c = tok.row(), tok.col()
            # Skip center cell (that's the agent itself)
            if obs_r == self._obs_hr and obs_c == self._obs_wr:
                continue

            tag_name = self._tag_names.get(tok.value, "")
            obj_name = tag_name.removeprefix("type:")

            # Only track unique identifiable objects (stations, junctions, assemblers)
            if obj_name in self.MATCHABLE_OBJECTS:
                obs_pos = (obs_r, obs_c)
                # Keep the most specific name if multiple tags
                if obs_pos not in observed_objects or obj_name in self.PRIORITY_OBJECTS:
                    observed_objects[obs_pos] = obj_name

        if not observed_objects:
            return  # No matchable objects, keep current position

        # Try to match observed objects against known world positions
        position_votes: list[tuple[int, int]] = []

        for obs_pos, obj_name in observed_objects.items():
            obs_r, obs_c = obs_pos

            # Check known stations
            for station_name, world_pos in state.map.stations.items():
                # Match by name similarity
                if self._objects_match(obj_name, station_name):
                    # Derive agent position: world_pos - obs_offset
                    derived_row = world_pos[0] - (obs_r - self._obs_hr)
                    derived_col = world_pos[1] - (obs_c - self._obs_wr)
                    position_votes.append((derived_row, derived_col))

            # Check known structures (junctions, extractors, etc.)
            for world_pos, struct in state.map.structures.items():
                if self._objects_match(obj_name, struct.name):
                    derived_row = world_pos[0] - (obs_r - self._obs_hr)
                    derived_col = world_pos[1] - (obs_c - self._obs_wr)
                    position_votes.append((derived_row, derived_col))

        if not position_votes:
            return  # No matches found, keep current position

        # Use majority vote (most common derived position)
        # This handles cases where multiple objects are visible
        position_counts = Counter(position_votes)
        most_common_pos, count = position_counts.most_common(1)[0]

        # Only update if we have confidence (multiple matches or different from current)
        if count >= 1:
            old_pos = (state.row, state.col)
            if most_common_pos != old_pos:
                if DEBUG:
                    print(
                        f"[A{state.agent_id}] MAP: Position corrected via object matching: "
                        f"{old_pos} -> {most_common_pos} (votes={count})"
                    )
                state.row, state.col = most_common_pos

    # Objects that can be used for position matching (unique, static)
    MATCHABLE_OBJECTS = frozenset(
        {
            "miner_station",
            "scout_station",
            "aligner_station",
            "scrambler_station",
            "assembler",
            "nexus",
            "hub",
            "junction",
            "charger",
            "chest",
            "carbon_extractor",
            "oxygen_extractor",
            "germanium_extractor",
            "silicon_extractor",
        }
    )

    def _objects_match(self, obs_name: str, known_name: str) -> bool:
        """Check if observed object name matches a known object name."""
        obs_lower = obs_name.lower()
        known_lower = known_name.lower()
        # Direct match
        if obs_lower == known_lower:
            return True
        # Substring match (e.g., "charger" matches "cogs_charger")
        if obs_lower in known_lower or known_lower in obs_lower:
            return True
        # Type match (e.g., "junction" matches "charger" which is a junction type)
        junction_names = {"junction", "charger", "supply_depot"}
        if obs_lower in junction_names and known_lower in junction_names:
            return True
        return False

    def _get_vibe_name(self, vibe_id: int) -> str:
        """Convert vibe ID to name."""
        # Use dynamically derived vibe names from action names
        if 0 <= vibe_id < len(self._vibe_names):
            return self._vibe_names[vibe_id]
        return "default"

    def _parse_observation(
        self, state: AgentState, obs: AgentObservation
    ) -> dict[tuple[int, int], dict[str, Union[int, list[int], dict[str, int]]]]:
        """Parse observation tokens into position-keyed features."""
        position_features: dict[tuple[int, int], dict[str, Union[int, list[int], dict[str, int]]]] = {}

        for tok in obs.tokens:
            # Use row()/col() methods - location tuple is (col, row) format
            obs_r, obs_c = tok.row(), tok.col()
            feature_name = tok.feature.name
            value = tok.value

            # Skip center cell (inventory/global)
            if obs_r == self._obs_hr and obs_c == self._obs_wr:
                continue

            # Convert to world coords
            r = obs_r - self._obs_hr + state.row
            c = obs_c - self._obs_wr + state.col

            if not (0 <= r < state.map.grid_size and 0 <= c < state.map.grid_size):
                continue

            pos = (r, c)
            if pos not in position_features:
                position_features[pos] = {}

            # Handle spatial features
            if feature_name in self._spatial_feature_names:
                if feature_name == "tag":
                    tags = position_features[pos].setdefault("tags", [])
                    if isinstance(tags, list):
                        tags.append(value)
                else:
                    position_features[pos][feature_name] = value

            # Handle inventory features (for extractors)
            elif feature_name.startswith("inv:"):
                resource = feature_name[4:]
                inventory = position_features[pos].setdefault("inventory", {})
                if isinstance(inventory, dict):
                    inventory[resource] = value

        return position_features

    def _mark_explored(self, state: AgentState) -> None:
        """Mark observed cells as explored and FREE.

        All cells in the current observation window are marked FREE initially.
        Then _process_object() will mark specific cells as OBSTACLE if objects are present.
        This correctly handles dynamic changes (objects that moved since last observation).

        Cells outside the observation window retain their previous state (FREE, OBSTACLE, or UNKNOWN),
        which is the "internal map" knowledge built up over time.
        """
        for obs_r in range(2 * self._obs_hr + 1):
            for obs_c in range(2 * self._obs_wr + 1):
                r = obs_r - self._obs_hr + state.row
                c = obs_c - self._obs_wr + state.col
                if 0 <= r < state.map.grid_size and 0 <= c < state.map.grid_size:
                    # Mark all observed cells as FREE (objects will be re-marked as OBSTACLE)
                    state.map.occupancy[r][c] = CellType.FREE.value
                    state.map.explored[r][c] = True

    # Object types that should be preferred over collective tags
    PRIORITY_OBJECTS = frozenset(
        {
            "miner_station",
            "scout_station",
            "aligner_station",
            "scrambler_station",
            "carbon_extractor",
            "oxygen_extractor",
            "germanium_extractor",
            "silicon_extractor",
            "junction",
            "hub",
            "chest",
            "wall",
            "agent",
        }
    )

    def _get_object_name(self, features: dict[str, Union[int, list[int], dict[str, int]]]) -> str:
        """Get object name from features - prioritize type: tags over collective: tags.

        Priority order (matching utils.py _select_primary_tag):
        1. type:* tags (strip prefix and return the type name)
        2. Non-collective tags that are PRIORITY_OBJECTS
        3. Any non-collective tag
        4. First tag (fallback)
        """
        tags_value = features.get("tags", [])
        if not isinstance(tags_value, list) or not tags_value:
            return "unknown"

        # Resolve all tag names
        resolved_tags = [self._tag_names.get(tag_id, "") for tag_id in tags_value]

        # First priority: type:* tags (preferred for identifying game objects)
        for tag in resolved_tags:
            if tag.startswith("type:"):
                return tag[5:]  # Strip "type:" prefix

        # Second priority: PRIORITY_OBJECTS among non-collective tags
        for tag in resolved_tags:
            if tag and not tag.startswith("collective:") and tag in self.PRIORITY_OBJECTS:
                return tag

        # Third priority: any non-collective tag
        for tag in resolved_tags:
            if tag and not tag.startswith("collective:"):
                return tag

        # Fallback: first non-empty tag
        for tag in resolved_tags:
            if tag:
                return tag

        return "unknown"

    def _process_object(
        self,
        state: AgentState,
        pos: tuple[int, int],
        obj_name: str,
        features: dict[str, Union[int, list[int], dict[str, int]]],
    ) -> None:
        """Process a discovered object and update state."""
        obj_lower = obj_name.lower()

        # Extract common features
        cooldown_val = features.get("cooldown_remaining", 0)
        cooldown = cooldown_val if isinstance(cooldown_val, int) else 0
        clipped_val = features.get("clipped", 0)
        clipped = clipped_val if isinstance(clipped_val, int) else 0
        remaining_val = features.get("remaining_uses", 999)
        remaining = remaining_val if isinstance(remaining_val, int) else 999
        inventory = features.get("inventory", {})
        inv_amount = sum(inventory.values()) if isinstance(inventory, dict) else 999

        # Extract collective ID for alignment detection
        collective_val = features.get("collective")
        collective_id: Optional[int] = collective_val if isinstance(collective_val, int) else None

        # Check if it's a wall
        if self._is_wall(obj_lower):
            state.map.occupancy[pos[0]][pos[1]] = CellType.OBSTACLE.value
            return

        # Check if it's another agent
        if obj_lower == "agent":
            state.map.agent_occupancy.add(pos)
            return

        # Check for gear stations
        for _role, station_name in ROLE_TO_STATION.items():
            if station_name in obj_lower or self._is_station(obj_lower, station_name):
                state.map.occupancy[pos[0]][pos[1]] = CellType.OBSTACLE.value
                struct_type = self._get_station_type(station_name)
                self._update_structure(state, pos, obj_name, struct_type, None, cooldown, remaining, inv_amount)
                if station_name not in state.map.stations:
                    state.map.stations[station_name] = pos
                    if DEBUG:
                        print(f"[A{state.agent_id}] MAP: Found {station_name} at {pos}")
                return

        # Check for junction (charger/supply_depot/junction)
        if "charger" in obj_lower or "supply_depot" in obj_lower or obj_lower == "junction":
            state.map.occupancy[pos[0]][pos[1]] = CellType.OBSTACLE.value
            alignment = self._derive_alignment(obj_lower, clipped, collective_id)
            self._update_structure(
                state, pos, obj_name, StructureType.JUNCTION, alignment, cooldown, remaining, inv_amount
            )
            if "junction" not in state.map.stations:
                state.map.stations["junction"] = pos
            if DEBUG and pos not in state.map.structures:
                print(
                    f"[A{state.agent_id}] MAP: Found junction at {pos} "
                    f"(alignment={alignment}, collective_id={collective_id})"
                )
            return

        # Check for assembler/nexus/hub
        if "assembler" in obj_lower or "nexus" in obj_lower or "hub" in obj_lower:
            state.map.occupancy[pos[0]][pos[1]] = CellType.OBSTACLE.value
            self._update_structure(
                state, pos, obj_name, StructureType.ASSEMBLER, "cogs", cooldown, remaining, inv_amount
            )
            if "assembler" not in state.map.stations:
                state.map.stations["assembler"] = pos
                if DEBUG:
                    print(f"[A{state.agent_id}] MAP: Found assembler at {pos}")
            return

        # Check for chest (hearts)
        resources = ["carbon", "oxygen", "germanium", "silicon"]
        is_resource_chest = any(f"{res}_" in obj_lower for res in resources)
        if "chest" in obj_lower and not is_resource_chest:
            state.map.occupancy[pos[0]][pos[1]] = CellType.OBSTACLE.value
            self._update_structure(state, pos, obj_name, StructureType.CHEST, None, cooldown, remaining, inv_amount)
            if "chest" not in state.map.stations:
                state.map.stations["chest"] = pos
                if DEBUG:
                    print(f"[A{state.agent_id}] MAP: Found chest at {pos}")
            return

        # Check for extractors
        for resource in resources:
            if f"{resource}_extractor" in obj_lower or f"{resource}_chest" in obj_lower:
                state.map.occupancy[pos[0]][pos[1]] = CellType.OBSTACLE.value
                res_amount = inventory.get(resource, inv_amount) if isinstance(inventory, dict) else inv_amount
                self._update_structure(
                    state, pos, obj_name, StructureType.EXTRACTOR, None, cooldown, remaining, res_amount, resource
                )
                if DEBUG:
                    print(
                        f"[A{state.agent_id}] MAP: Found {resource} extractor at {pos} "
                        f"(remaining={remaining}, inv_amount={res_amount}, inventory={inventory})"
                    )
                return

    def _update_structure(
        self,
        state: AgentState,
        pos: tuple[int, int],
        obj_name: str,
        struct_type: StructureType,
        alignment: Optional[str],
        cooldown: int,
        remaining: int,
        inv_amount: int,
        resource_type: Optional[str] = None,
    ) -> None:
        """Update or create a structure in the map."""
        if pos in state.map.structures:
            struct = state.map.structures[pos]
            # Check if alignment changed
            if DEBUG and struct.alignment != alignment:
                print(f"[A{state.agent_id}] MAP: Junction {pos} alignment changed: {struct.alignment} -> {alignment}")
            struct.last_seen_step = state.step
            struct.cooldown_remaining = cooldown
            struct.remaining_uses = remaining
            struct.inventory_amount = inv_amount
            # Always update alignment - None means neutral (not cogs or clips)
            struct.alignment = alignment
        else:
            state.map.structures[pos] = StructureInfo(
                position=pos,
                structure_type=struct_type,
                name=obj_name,
                last_seen_step=state.step,
                alignment=alignment,
                resource_type=resource_type,
                cooldown_remaining=cooldown,
                remaining_uses=remaining,
                inventory_amount=inv_amount,
            )

    def _derive_alignment(self, obj_name: str, clipped: int, collective_id: Optional[int] = None) -> Optional[str]:
        """Derive alignment from collective ID, object name, and clipped status.

        Priority:
        1. Collective ID from observation (most reliable)
        2. Object name containing "cogs" or "clips"
        3. Clipped flag (clips territory marker)
        """
        # First check collective ID from observation (most reliable)
        if collective_id is not None:
            if collective_id == self._cogs_collective_id:
                return "cogs"
            elif collective_id == self._clips_collective_id:
                return "clips"

        # Fall back to name-based detection
        if "cogs" in obj_name:
            return "cogs"
        if "clips" in obj_name or clipped > 0:
            return "clips"
        return None

    def _is_wall(self, obj_name: str) -> bool:
        """Check if object is a wall."""
        return "wall" in obj_name or "#" in obj_name

    def _is_station(self, obj_name: str, station: str) -> bool:
        """Check if object is a specific station type."""
        return station in obj_name

    def _get_station_type(self, station_name: str) -> StructureType:
        """Convert station name to StructureType."""
        mapping = {
            "miner_station": StructureType.MINER_STATION,
            "scout_station": StructureType.SCOUT_STATION,
            "aligner_station": StructureType.ALIGNER_STATION,
            "scrambler_station": StructureType.SCRAMBLER_STATION,
        }
        return mapping.get(station_name, StructureType.UNKNOWN)

    def get_direction_to_nearest(
        self,
        state: AgentState,
        obs: AgentObservation,
        target_types: frozenset[str],
    ) -> Optional[tuple[str, tuple[int, int]]]:
        """Get the direction to move toward nearest target in current observation.

        Uses A* pathfinding within the observation window.
        Returns: (direction, world_pos) tuple or None if no path found.
            direction: "north", "south", "east", "west"
            world_pos: (row, col) in world coordinates
        """
        import heapq

        center_c, center_r = self._obs_wr, self._obs_hr  # (5, 5) typically

        # Find cells with any objects (blocked) and target cells
        blocked_cells: set[tuple[int, int]] = set()
        target_cells: list[tuple[int, int]] = []

        for tok in obs.tokens:
            if tok.feature.name != "tag":
                continue

            dr = tok.row() - center_r
            dc = tok.col() - center_c

            tag_name = self._tag_names.get(tok.value, "")
            match_name = tag_name.removeprefix("type:")

            # Check if this is a target (use substring matching for flexibility)
            is_target = match_name in target_types or any(t in match_name for t in target_types)
            if is_target:
                target_cells.append((dr, dc))
                if DEBUG and state.agent_id == 0 and state.step % 50 == 0:
                    print(f"[A{state.agent_id}] DIR: Found target '{match_name}' at ({dr},{dc})")

            # All objects block movement (except self at center)
            if dr != 0 or dc != 0:
                blocked_cells.add((dr, dc))

        if not target_cells:
            return None

        # Find nearest target (for A* goal)
        target_cells.sort(key=lambda t: abs(t[0]) + abs(t[1]))
        goal = target_cells[0]

        # Convert goal to world coordinates for return value
        goal_world = (state.row + goal[0], state.col + goal[1])

        # A* pathfinding from (0, 0) to goal
        # We want to reach adjacent to goal (since goal cell is blocked)
        def heuristic(pos: tuple[int, int]) -> int:
            return abs(pos[0] - goal[0]) + abs(pos[1] - goal[1])

        def is_adjacent_to_goal(pos: tuple[int, int]) -> bool:
            return abs(pos[0] - goal[0]) + abs(pos[1] - goal[1]) == 1

        start = (0, 0)

        # Special case: already adjacent to goal - return direction to walk into target
        if is_adjacent_to_goal(start):
            dr, dc = goal
            if dr == 1:
                return ("south", goal_world)
            elif dr == -1:
                return ("north", goal_world)
            elif dc == 1:
                return ("east", goal_world)
            else:
                return ("west", goal_world)

        # Priority queue: (f_score, g_score, position)
        open_set: list[tuple[int, int, tuple[int, int]]] = [(heuristic(start), 0, start)]
        came_from: dict[tuple[int, int], tuple[int, int]] = {}
        g_score: dict[tuple[int, int], int] = {start: 0}

        directions = [(1, 0), (-1, 0), (0, 1), (0, -1)]  # south, north, east, west
        obs_bounds = (self._obs_hr, self._obs_wr)  # max distance from center

        while open_set:
            _, current_g, current = heapq.heappop(open_set)

            # Check if we reached adjacent to goal
            if is_adjacent_to_goal(current):
                # Reconstruct path and return first direction
                path = []
                pos = current
                while pos in came_from:
                    path.append(pos)
                    pos = came_from[pos]
                path.reverse()

                if path:
                    first_step = path[0]
                    dr, dc = first_step
                    if dr == 1:
                        direction = "south"
                    elif dr == -1:
                        direction = "north"
                    elif dc == 1:
                        direction = "east"
                    else:
                        direction = "west"

                    if DEBUG and state.agent_id == 0:
                        print(f"[A{state.agent_id}] DIR: A* path to {goal}, first step → {direction}")
                    return (direction, goal_world)
                return None

            for dr, dc in directions:
                neighbor = (current[0] + dr, current[1] + dc)

                # Check bounds (stay within observation window)
                if abs(neighbor[0]) > obs_bounds[0] or abs(neighbor[1]) > obs_bounds[1]:
                    continue

                # Check if blocked (but goal cell is allowed as destination check happens above)
                if neighbor in blocked_cells and neighbor != goal:
                    continue

                tentative_g = current_g + 1
                if neighbor not in g_score or tentative_g < g_score[neighbor]:
                    g_score[neighbor] = tentative_g
                    f_score = tentative_g + heuristic(neighbor)
                    heapq.heappush(open_set, (f_score, tentative_g, neighbor))
                    came_from[neighbor] = current

        # No path found
        if DEBUG and state.agent_id == 0:
            print(f"[A{state.agent_id}] DIR: A* no path to {goal}")
        return None

    # === Query methods ===

    def find_nearest(
        self, state: AgentState, structure_type: StructureType, exclude: Optional[tuple[int, int]] = None
    ) -> Optional[StructureInfo]:
        """Find nearest structure of given type."""
        best: Optional[StructureInfo] = None
        best_dist = float("inf")

        for struct in state.map.structures.values():
            if struct.structure_type != structure_type:
                continue
            if exclude and struct.position == exclude:
                continue

            dist = abs(struct.position[0] - state.row) + abs(struct.position[1] - state.col)
            if dist < best_dist:
                best = struct
                best_dist = dist

        return best

    def distance_to(self, state: AgentState, pos: tuple[int, int]) -> int:
        """Manhattan distance from agent to position."""
        return abs(pos[0] - state.row) + abs(pos[1] - state.col)
