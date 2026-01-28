"""
Navigator service for Pinky policy.

Handles pathfinding, movement, stuck detection, and exploration.
Uses A* pathfinding with dynamic agent avoidance.
"""

from __future__ import annotations

import heapq
import random
from typing import TYPE_CHECKING, Optional

from cogames_agents.policy.scripted_agent.pinky.types import DEBUG, CellType
from mettagrid.simulator import Action

if TYPE_CHECKING:
    from cogames_agents.policy.scripted_agent.pinky.state import AgentState
    from mettagrid.policy.policy_env_interface import PolicyEnvInterface


class Navigator:
    """Handles all movement decisions - pathfinding, stuck detection, collision avoidance."""

    MOVE_DELTAS = {
        "north": (-1, 0),
        "south": (1, 0),
        "east": (0, 1),
        "west": (0, -1),
    }

    DIRECTIONS = ["north", "south", "east", "west"]

    # Stuck detection thresholds (balanced)
    STUCK_THRESHOLD = 10  # Consecutive steps at same position
    POSITION_HISTORY_SIZE = 20  # How many positions to track for circular detection
    CIRCULAR_STUCK_THRESHOLD = 5  # Revisiting same position this many times = stuck
    TIGHT_LOOP_HISTORY = 15  # Check this many recent positions for tight loops
    TIGHT_LOOP_UNIQUE_MIN = 4  # If fewer unique positions than this, we're stuck

    # Escape mode settings
    ESCAPE_COMMITMENT_STEPS = 4  # When stuck, commit to escaping for this many steps

    def __init__(self, policy_env_info: PolicyEnvInterface):
        # Store action names for potential validation
        self._action_names = policy_env_info.action_names

    def move_to(
        self,
        state: AgentState,
        target: tuple[int, int],
        reach_adjacent: bool = False,
    ) -> Action:
        """Pathfind toward a target position using the internal map.

        Uses A* pathfinding with the map built from previous observations.
        Navigates around other agents dynamically. First tries to find a path
        through known (explored) terrain. If no known path exists, allows traversal
        through unknown cells to reach the target.

        Args:
            state: Current agent state
            target: Target position to reach
            reach_adjacent: If True, stop when adjacent to target instead of on it

        Returns:
            Action to move toward target, or noop if stuck/unreachable
        """
        # Check for stuck loop first
        if self._is_stuck(state):
            action = self._break_stuck(state)
            if action:
                return action

        start = state.pos
        if start == target and not reach_adjacent:
            return Action(name="noop")

        # Compute goal cells
        goal_cells = self._compute_goal_cells(state, target, reach_adjacent)
        if not goal_cells:
            if DEBUG:
                print(f"[A{state.agent_id}] NAV: No goal cells for {target}")
            return Action(name="noop")

        # Check cached path (invalidate if path goes through now-blocked cells or agents)
        path = self._get_cached_path(state, target, reach_adjacent)

        # Compute new path if needed
        if path is None:
            # First try to find path through known terrain, avoiding agents
            path = self._shortest_path(state, start, goal_cells, allow_unknown=False, avoid_agents=True)

            # If no path avoiding agents, try allowing agent cells (they may move)
            if not path and state.map.agent_occupancy:
                if DEBUG:
                    print(f"[A{state.agent_id}] NAV: No path avoiding agents, trying through agent cells")
                path = self._shortest_path(state, start, goal_cells, allow_unknown=False, avoid_agents=False)

            # If still no known path, try allowing unknown cells (exploration)
            if not path:
                if DEBUG:
                    print(f"[A{state.agent_id}] NAV: No known path to {target}, trying through unknown")
                path = self._shortest_path(state, start, goal_cells, allow_unknown=True, avoid_agents=True)

            # Last resort: allow both unknown and agent cells
            if not path and state.map.agent_occupancy:
                path = self._shortest_path(state, start, goal_cells, allow_unknown=True, avoid_agents=False)

            state.nav.cached_path = path.copy() if path else None
            state.nav.cached_path_target = target
            state.nav.cached_path_reach_adjacent = reach_adjacent

        if not path:
            if DEBUG:
                print(f"[A{state.agent_id}] NAV: No path to {target}, exploring")
            return self.explore(state)

        next_pos = path[0]

        # Check if next position is blocked by an agent
        if next_pos in state.map.agent_occupancy:
            # Try to find an immediate sidestep around the blocking agent
            sidestep = self._find_sidestep(state, next_pos, target)
            if sidestep:
                if DEBUG:
                    print(f"[A{state.agent_id}] NAV: Agent at {next_pos}, sidestepping to {sidestep}")
                # Clear cached path since we're deviating
                state.nav.cached_path = None
                state.nav.cached_path_target = None
                return self._move_toward(state, sidestep)
            else:
                # No sidestep available, wait by doing noop (agent may move next step)
                if DEBUG:
                    print(f"[A{state.agent_id}] NAV: Agent blocking at {next_pos}, waiting")
                return Action(name="noop")

        # Advance cached path
        if state.nav.cached_path:
            state.nav.cached_path = state.nav.cached_path[1:]
            if not state.nav.cached_path:
                state.nav.cached_path = None
                state.nav.cached_path_target = None

        return self._move_toward(state, next_pos)

    def _find_sidestep(
        self, state: AgentState, blocked_pos: tuple[int, int], target: tuple[int, int]
    ) -> Optional[tuple[int, int]]:
        """Find an immediate sidestep around a blocking agent.

        Tries to find an adjacent free cell that still makes progress toward the target.

        Args:
            state: Agent state
            blocked_pos: The position blocked by an agent
            target: Ultimate target we're trying to reach

        Returns:
            A position to sidestep to, or None if no good sidestep available
        """
        current = state.pos
        current_dist = abs(target[0] - current[0]) + abs(target[1] - current[1])

        candidates: list[tuple[int, tuple[int, int]]] = []

        for direction in self.DIRECTIONS:
            dr, dc = self.MOVE_DELTAS[direction]
            nr, nc = current[0] + dr, current[1] + dc
            neighbor = (nr, nc)

            # Skip the blocked position
            if neighbor == blocked_pos:
                continue

            # Check if this cell is traversable
            if not self._is_traversable(state, nr, nc, allow_unknown=True, check_agents=True):
                continue

            # Calculate distance to target from this position
            new_dist = abs(target[0] - nr) + abs(target[1] - nc)

            # Prefer cells that maintain or improve distance to target
            # Score: lower is better (distance increase as cost)
            score = new_dist - current_dist
            candidates.append((score, neighbor))

        if not candidates:
            return None

        # Sort by score (prefer cells that don't increase distance much)
        candidates.sort(key=lambda x: x[0])

        # Only take sidesteps that don't increase distance by more than 2
        # (otherwise we might be going backwards)
        if candidates[0][0] <= 2:
            return candidates[0][1]

        return None

    def explore(self, state: AgentState, direction_bias: Optional[str] = None) -> Action:
        """Explore by navigating toward unexplored frontier cells.

        Uses the map's explored grid to find the nearest unexplored cell
        adjacent to known territory, then pathfinds toward it.

        Args:
            state: Agent state with map knowledge
            direction_bias: Optional direction preference to spread agents
        """
        # Check for stuck loop
        if self._is_stuck(state):
            action = self._break_stuck(state)
            if action:
                return action

        # Find nearest unexplored frontier cell
        # Use agent_id to bias direction so agents spread out
        if direction_bias is None:
            directions = ["north", "east", "south", "west"]
            direction_bias = directions[state.agent_id % 4]

        frontier = state.map.find_nearest_unexplored(state.pos, max_dist=50, direction_bias=direction_bias)

        if frontier is not None:
            # Navigate toward the frontier cell
            return self.move_to(state, frontier)

        # No frontier found - fall back to expanding box pattern
        if state.nav.explore_origin is None:
            state.nav.explore_origin = state.pos
            state.nav.explore_start_step = state.step

        origin = state.nav.explore_origin
        explore_step = state.step - state.nav.explore_start_step

        # Calculate target position using expanding box pattern
        target = self._get_explore_target(origin, explore_step)

        # Move toward target
        dr = target[0] - state.row
        dc = target[1] - state.col

        # If at target, advance to next step
        if dr == 0 and dc == 0:
            state.nav.explore_start_step = state.step - explore_step - 1
            return self.explore(state, direction_bias)

        # Pick direction toward target, prioritizing larger delta
        direction = None
        if abs(dr) >= abs(dc):
            if dr > 0:
                direction = "south"
            elif dr < 0:
                direction = "north"
            elif dc > 0:
                direction = "east"
            elif dc < 0:
                direction = "west"
        else:
            if dc > 0:
                direction = "east"
            elif dc < 0:
                direction = "west"
            elif dr > 0:
                direction = "south"
            elif dr < 0:
                direction = "north"

        if direction:
            move_dr, move_dc = self.MOVE_DELTAS[direction]
            next_r, next_c = state.row + move_dr, state.col + move_dc
            if self._is_traversable(state, next_r, next_c, allow_unknown=True, check_agents=True):
                return Action(name=f"move_{direction}")

            # Primary direction blocked (possibly by agent) - try perpendicular directions
            if direction in ("north", "south"):
                alternatives = ["east", "west"]
            else:
                alternatives = ["north", "south"]

            for alt_dir in alternatives:
                alt_dr, alt_dc = self.MOVE_DELTAS[alt_dir]
                alt_r, alt_c = state.row + alt_dr, state.col + alt_dc
                if self._is_traversable(state, alt_r, alt_c, allow_unknown=True, check_agents=True):
                    return Action(name=f"move_{alt_dir}")

        # All directions blocked by obstacles or agents - try any traversable direction
        for fallback_dir in self.DIRECTIONS:
            fb_dr, fb_dc = self.MOVE_DELTAS[fallback_dir]
            fb_r, fb_c = state.row + fb_dr, state.col + fb_dc
            if self._is_traversable(state, fb_r, fb_c, allow_unknown=True, check_agents=True):
                return Action(name=f"move_{fallback_dir}")

        # Completely blocked - wait (agents may move)
        if DEBUG:
            print(f"[A{state.agent_id}] NAV: Explore blocked, waiting")
        return Action(name="noop")

    def _get_explore_target(self, origin: tuple[int, int], step: int) -> tuple[int, int]:
        """Calculate target position for expanding box exploration.

        Creates waypoints in a clockwise expanding box pattern:
        Ring 1: E(5) → S(5) → W(10) → N(10)
        Ring 2: E(10) → S(10) → W(15) → N(15)
        etc.
        """
        segment_base = 5  # Base segment length (accounts for movement cooldowns)
        ring = 1
        cumulative_steps = 0

        while True:
            seg_len = segment_base * ring
            # Each ring has 4 segments: E, S, W, N
            # E and S use seg_len, W and N use seg_len + segment_base (to complete the box)
            ring_segments = [
                ("east", seg_len),
                ("south", seg_len),
                ("west", seg_len + segment_base),
                ("north", seg_len + segment_base),
            ]

            for direction, length in ring_segments:
                if cumulative_steps + length > step:
                    # We're in this segment
                    progress = step - cumulative_steps
                    dr, dc = self.MOVE_DELTAS[direction]
                    # Calculate position at start of this segment
                    # then add progress along segment
                    seg_start = self._get_segment_start(origin, ring, direction, segment_base)
                    return (seg_start[0] + dr * progress, seg_start[1] + dc * progress)
                cumulative_steps += length

            ring += 1
            if ring > 10:  # Safety limit - reset to ring 1
                ring = 1
                cumulative_steps = 0

    def _get_segment_start(
        self, origin: tuple[int, int], ring: int, direction: str, segment_base: int
    ) -> tuple[int, int]:
        """Get starting position for a segment in the expanding box."""
        # Calculate corner positions for this ring
        # After completing rings 1..ring-1, we're at the start of ring `ring`
        offset = segment_base * ring
        r, c = origin

        if direction == "east":
            # Start of E segment: NE corner of previous ring (or origin for ring 1)
            if ring == 1:
                return origin
            return (r - offset + segment_base, c + offset - segment_base)
        elif direction == "south":
            # Start of S segment: after going E
            return (r - offset + segment_base, c + offset)
        elif direction == "west":
            # Start of W segment: SE corner
            return (r + offset, c + offset)
        elif direction == "north":
            # Start of N segment: SW corner
            return (r + offset, c - offset)
        return origin

    def use_object_at(self, state: AgentState, target: tuple[int, int]) -> Action:
        """Move toward an object cell to interact with it.

        In mettagrid, moving toward an adjacent object triggers its on_use_handler.
        The move may fail (object is obstacle), but the handler still fires.
        Position tracking correctly stays at the adjacent cell.
        """
        state.nav.using_object_this_step = True
        return self._move_toward(state, target)

    def update_position(self, state: AgentState) -> None:
        """Update agent position based on last executed action.

        This is a simple action-based update that serves as a fallback.
        The map_tracker's object matching will correct any errors by
        matching visible objects to their known world positions.
        """
        last_action = state.nav.last_action_executed

        # Simple action-based position update
        # Object matching in map_tracker will correct any errors
        if last_action and last_action.startswith("move_"):
            direction = last_action[5:]  # Remove "move_" prefix
            if direction in self.MOVE_DELTAS:
                dr, dc = self.MOVE_DELTAS[direction]
                new_r, new_c = state.row + dr, state.col + dc

                # Only update if target is not a known obstacle
                # (object matching will correct if this is wrong)
                if self._is_in_bounds(state, new_r, new_c):
                    cell_type = state.map.occupancy[new_r][new_c]
                    if cell_type != CellType.OBSTACLE.value:
                        state.row = new_r
                        state.col = new_c

        # Track position history for stuck detection
        state.nav.position_history.append(state.pos)
        if len(state.nav.position_history) > 30:
            state.nav.position_history.pop(0)

    def _is_stuck(self, state: AgentState) -> bool:
        """Detect if agent is oscillating or revisiting positions frequently.

        Detects:
        1. Oscillation between 2 positions (A→B→A→B)
        2. Larger oscillation patterns where agent revisits same positions
        """
        history = state.nav.position_history
        if len(history) < 6:
            return False

        # Check last 6 positions for tight oscillation (2 positions)
        recent = history[-6:]
        unique_recent = set(recent)
        if len(unique_recent) == 2:
            if DEBUG:
                print(f"[A{state.agent_id}] NAV: Stuck! Oscillating between {unique_recent}")
            return True

        # Check for larger oscillation pattern - revisiting positions we were at earlier
        # (catches the east-west ping-pong over 8+ steps)
        if len(history) >= 20:
            current_pos = history[-1]
            # Check if current position appeared earlier in history (not just recently)
            earlier_history = history[:-10]  # Positions from 10+ steps ago
            revisit_count = earlier_history.count(current_pos)
            if revisit_count >= 2:
                if DEBUG:
                    print(f"[A{state.agent_id}] NAV: Stuck loop! Revisited {current_pos} {revisit_count}x")
                return True

        return False

    def _break_stuck(self, state: AgentState) -> Optional[Action]:
        """Try to escape stuck state with random movement into unexplored territory."""
        if DEBUG:
            print(f"[A{state.agent_id}] NAV: Breaking stuck loop")

        # Clear cached path
        state.nav.cached_path = None
        state.nav.cached_path_target = None
        state.nav.position_history.clear()

        # Try random direction, allowing unknown cells to escape, avoiding agents
        directions = list(self.DIRECTIONS)
        random.shuffle(directions)
        for direction in directions:
            dr, dc = self.MOVE_DELTAS[direction]
            nr, nc = state.row + dr, state.col + dc
            if self._is_traversable(state, nr, nc, allow_unknown=True, check_agents=True):
                return Action(name=f"move_{direction}")
        return None

    def _move_toward(self, state: AgentState, target: tuple[int, int]) -> Action:
        """Return action to move one step toward target."""
        tr, tc = target
        if state.row == tr and state.col == tc:
            return Action(name="noop")

        dr = tr - state.row
        dc = tc - state.col

        # Check for agent collision
        if (tr, tc) in state.map.agent_occupancy:
            # Try to go around
            return self._try_alternative_direction(state, target)

        if dr == -1 and dc == 0:
            return Action(name="move_north")
        elif dr == 1 and dc == 0:
            return Action(name="move_south")
        elif dr == 0 and dc == 1:
            return Action(name="move_east")
        elif dr == 0 and dc == -1:
            return Action(name="move_west")

        return Action(name="noop")

    def _try_alternative_direction(self, state: AgentState, target: tuple[int, int]) -> Action:
        """Try to move around an obstacle or agent toward target.

        Prefers directions that maintain progress toward the target.
        """
        # Collect valid moves with their distance to target
        candidates: list[tuple[int, str]] = []

        for direction in self.DIRECTIONS:
            dr, dc = self.MOVE_DELTAS[direction]
            nr, nc = state.row + dr, state.col + dc
            if self._is_traversable(state, nr, nc, allow_unknown=True, check_agents=True):
                new_dist = abs(target[0] - nr) + abs(target[1] - nc)
                candidates.append((new_dist, direction))

        if not candidates:
            return Action(name="noop")

        # Sort by distance to target (prefer moves that get closer)
        candidates.sort(key=lambda x: x[0])
        return Action(name=f"move_{candidates[0][1]}")

    def _compute_goal_cells(
        self, state: AgentState, target: tuple[int, int], reach_adjacent: bool
    ) -> list[tuple[int, int]]:
        """Compute goal cells for pathfinding using internal map knowledge."""
        if not reach_adjacent:
            return [target]

        goals = []
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = target[0] + dr, target[1] + dc
            # Accept FREE cells, and also UNKNOWN cells (might be reachable)
            if self._is_traversable(state, nr, nc, allow_unknown=True):
                goals.append((nr, nc))

        return goals

    def _shortest_path(
        self,
        state: AgentState,
        start: tuple[int, int],
        goals: list[tuple[int, int]],
        allow_unknown: bool = False,
        avoid_agents: bool = True,
    ) -> list[tuple[int, int]]:
        """A* pathfinding from start to any goal, navigating around agents.

        Uses the internal map built from previous observations. Prefers known paths
        but can traverse unknown cells if allow_unknown=True.

        Args:
            state: Agent state with internal map
            start: Starting position
            goals: List of goal positions
            allow_unknown: If True, treat UNKNOWN cells as potentially traversable
            avoid_agents: If True, treat agent positions as obstacles (default True)

        Note: Goal cells are reachable even if they are obstacles (for walking into objects).
        """
        goal_set = set(goals)
        if not goals:
            return []

        # Use minimum manhattan distance to any goal as heuristic
        def heuristic(pos: tuple[int, int]) -> int:
            return min(abs(pos[0] - g[0]) + abs(pos[1] - g[1]) for g in goals)

        # Priority queue: (f_score, tie_breaker, position)
        # tie_breaker ensures consistent ordering when f_scores are equal
        tie_breaker = 0
        open_set: list[tuple[int, int, tuple[int, int]]] = [(heuristic(start), tie_breaker, start)]
        came_from: dict[tuple[int, int], Optional[tuple[int, int]]] = {start: None}
        g_score: dict[tuple[int, int], int] = {start: 0}

        while open_set:
            _, _, current = heapq.heappop(open_set)

            if current in goal_set:
                return self._reconstruct_path(came_from, current)

            # Skip if we've found a better path to this node already
            current_g = g_score.get(current, float("inf"))
            if isinstance(current_g, float):
                continue

            for nr, nc in self._get_neighbors(state, current):
                neighbor = (nr, nc)

                # Allow reaching goal cells even if they're obstacles (objects to use)
                is_goal = neighbor in goal_set
                if not is_goal and not self._is_traversable(
                    state, nr, nc, allow_unknown=allow_unknown, check_agents=avoid_agents
                ):
                    continue

                tentative_g = current_g + 1

                if tentative_g < g_score.get(neighbor, float("inf")):
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g
                    f_score = tentative_g + heuristic(neighbor)
                    tie_breaker += 1
                    heapq.heappush(open_set, (f_score, tie_breaker, neighbor))

        return []

    def _reconstruct_path(
        self, came_from: dict[tuple[int, int], Optional[tuple[int, int]]], current: tuple[int, int]
    ) -> list[tuple[int, int]]:
        """Reconstruct path from BFS came_from dict."""
        path = []
        while came_from[current] is not None:
            path.append(current)
            prev = came_from[current]
            assert prev is not None
            current = prev
        path.reverse()
        return path

    def _get_neighbors(self, state: AgentState, pos: tuple[int, int]) -> list[tuple[int, int]]:
        """Get valid neighboring positions."""
        r, c = pos
        candidates = [(r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)]
        return [(nr, nc) for nr, nc in candidates if self._is_in_bounds(state, nr, nc)]

    def _is_in_bounds(self, state: AgentState, r: int, c: int) -> bool:
        """Check if position is within map bounds."""
        return 0 <= r < state.map.grid_size and 0 <= c < state.map.grid_size

    def _is_traversable(
        self, state: AgentState, r: int, c: int, allow_unknown: bool = False, check_agents: bool = True
    ) -> bool:
        """Check if a cell is traversable.

        Args:
            state: Agent state
            r: Row coordinate
            c: Column coordinate
            allow_unknown: If True, treat UNKNOWN cells as potentially traversable (for exploration)
            check_agents: If True, treat cells with agents as non-traversable (default True)

        Returns:
            True if the cell can be moved into
        """
        if not self._is_in_bounds(state, r, c):
            if DEBUG and state.step == 10 and state.agent_id == 0:
                print(f"[NAV] ({r},{c}) out of bounds")
            return False

        if check_agents:
            pos = (r, c)
            # Check current observation (definite agent position)
            if pos in state.map.agent_occupancy:
                if DEBUG and state.step == 10 and state.agent_id == 0:
                    print(f"[NAV] ({r},{c}) has agent (current obs)")
                return False

            # Check recently-seen agents (may still be there)
            # Only block if agent was seen very recently (within 5 steps)
            if pos in state.map.recent_agents:
                sighting = state.map.recent_agents[pos]
                if state.step - sighting.last_seen_step <= 5:
                    if DEBUG and state.step == 10 and state.agent_id == 0:
                        print(f"[NAV] ({r},{c}) recent agent ({state.step - sighting.last_seen_step} ago)")
                    return False

        occ = state.map.occupancy[r][c]
        is_free = occ == CellType.FREE.value
        is_unknown = occ == CellType.UNKNOWN.value

        # Allow traversal if FREE, or if UNKNOWN and exploration is allowed
        traversable = is_free or (allow_unknown and is_unknown)

        if DEBUG and state.step == 10 and state.agent_id == 0 and not traversable:
            print(f"[NAV] ({r},{c}) occ={occ}, FREE={CellType.FREE.value}, UNKNOWN={CellType.UNKNOWN.value}")
        return traversable

    def _get_cached_path(
        self, state: AgentState, target: tuple[int, int], reach_adjacent: bool
    ) -> Optional[list[tuple[int, int]]]:
        """Get cached path if still valid.

        Invalidates the cached path if:
        - Target changed
        - reach_adjacent mode changed
        - Next step in path is blocked (by obstacle or agent)
        - Any cell in the path is now occupied by an agent
        """
        if (
            state.nav.cached_path
            and state.nav.cached_path_target == target
            and state.nav.cached_path_reach_adjacent == reach_adjacent
        ):
            # Check if any cell in the path is blocked by an agent
            for pos in state.nav.cached_path:
                if pos in state.map.agent_occupancy:
                    if DEBUG:
                        print(f"[A{state.agent_id}] NAV: Cached path blocked by agent at {pos}")
                    return None

            # Check if next step is traversable
            next_pos = state.nav.cached_path[0]
            if self._is_traversable(state, next_pos[0], next_pos[1]):
                return state.nav.cached_path
        return None

    # === Escape Mode Handling ===
    # Generalized stuck detection and escape for all behaviors

    def check_and_handle_escape(self, state: AgentState) -> Optional[Action]:
        """Check if agent is stuck and handle escape mode.

        This should be called at the start of each behavior's act() method.
        Returns an escape action if in escape mode or stuck, None otherwise.

        When stuck is detected:
        1. Calculates escape direction away from center of recent positions
        2. Enters escape mode, committing to escape for several steps
        3. Clears navigation state and position history

        Args:
            state: Agent state

        Returns:
            Action if escaping, None if not stuck and not in escape mode
        """
        # Track stuck detection: count consecutive steps at same position
        if state.pos == state.last_position:
            state.steps_at_same_position += 1
        else:
            state.steps_at_same_position = 0
            state.last_position = state.pos

        # Check if we're already in escape mode
        if state.escape_direction is not None and state.step < state.escape_until_step:
            escape_action = self._execute_escape(state)
            if escape_action:
                return escape_action
            # Escape blocked, end escape mode early
            state.escape_direction = None

        # Check for stuck patterns
        stuck_reason = self._check_stuck_patterns(state)

        if stuck_reason:
            if DEBUG:
                print(f"[A{state.agent_id}] NAV: STUCK ({stuck_reason}), entering escape mode")
            state.steps_at_same_position = 0

            # Clear navigation state to force fresh pathfinding
            state.nav.cached_path = None
            state.nav.cached_path_target = None

            # Calculate escape direction - move AWAY from center of recent positions
            escape_direction = self._calculate_escape_direction(state)

            # Enter escape mode
            state.escape_direction = escape_direction
            state.escape_until_step = state.step + self.ESCAPE_COMMITMENT_STEPS

            # Clear position history for fresh stuck detection after escape
            state.nav.position_history.clear()

            if DEBUG:
                print(f"[A{state.agent_id}] NAV: Escaping {escape_direction} for {self.ESCAPE_COMMITMENT_STEPS} steps")

            # Execute the first escape step
            escape_action = self._execute_escape(state)
            if escape_action:
                return escape_action

            # Escape direction completely blocked, clear escape mode
            state.escape_direction = None

        return None

    def _check_stuck_patterns(self, state: AgentState) -> Optional[str]:
        """Check for various stuck patterns.

        Returns a reason string if stuck, None otherwise.
        """
        # Check 1: Same position for too long
        if state.steps_at_same_position >= self.STUCK_THRESHOLD:
            return f"same_pos_{state.steps_at_same_position}"

        # Check 2: Circular pattern - revisiting positions in recent history
        if len(state.nav.position_history) >= 10:
            recent_history = state.nav.position_history[-self.POSITION_HISTORY_SIZE :]
            current_pos = state.pos
            revisit_count = recent_history.count(current_pos)
            if revisit_count >= self.CIRCULAR_STUCK_THRESHOLD:
                return f"circular_{revisit_count}x"

        # Check 3: Too few unique positions in recent history (tight circles)
        if len(state.nav.position_history) >= self.TIGHT_LOOP_HISTORY:
            recent = state.nav.position_history[-self.TIGHT_LOOP_HISTORY :]
            unique_positions = len(set(recent))
            if unique_positions <= self.TIGHT_LOOP_UNIQUE_MIN:
                return f"tight_loop_{unique_positions}_unique"

        return None

    def _execute_escape(self, state: AgentState) -> Optional[Action]:
        """Execute one step of escape movement.

        Tries to move in the escape direction, with fallbacks to perpendicular directions.
        Returns None if completely blocked.
        """
        if state.escape_direction is None:
            return None

        escape_dir = state.escape_direction
        dr, dc = self.MOVE_DELTAS[escape_dir]

        # Try primary escape direction
        nr, nc = state.row + dr, state.col + dc
        if self._is_traversable(state, nr, nc, allow_unknown=True, check_agents=True):
            return Action(name=f"move_{escape_dir}")

        # Primary blocked - try perpendicular directions
        if escape_dir in ("north", "south"):
            perpendicular = ["east", "west"]
        else:
            perpendicular = ["north", "south"]

        random.shuffle(perpendicular)
        for alt_dir in perpendicular:
            alt_dr, alt_dc = self.MOVE_DELTAS[alt_dir]
            alt_r, alt_c = state.row + alt_dr, state.col + alt_dc
            if self._is_traversable(state, alt_r, alt_c, allow_unknown=True, check_agents=True):
                return Action(name=f"move_{alt_dir}")

        # Try opposite direction as last resort
        opposite = {"north": "south", "south": "north", "east": "west", "west": "east"}
        opp_dir = opposite[escape_dir]
        opp_dr, opp_dc = self.MOVE_DELTAS[opp_dir]
        opp_r, opp_c = state.row + opp_dr, state.col + opp_dc
        if self._is_traversable(state, opp_r, opp_c, allow_unknown=True, check_agents=True):
            # Switch escape direction since we're blocked
            state.escape_direction = opp_dir
            return Action(name=f"move_{opp_dir}")

        return None

    def _calculate_escape_direction(self, state: AgentState) -> str:
        """Calculate the best direction to escape from a stuck position.

        Strategy: Move AWAY from the center of mass of recent positions.
        This prevents oscillating back into the same area.
        """
        history = state.nav.position_history
        if len(history) < 3:
            return random.choice(self.DIRECTIONS)

        # Calculate center of mass of recent positions
        recent = history[-min(len(history), 15) :]
        avg_row = sum(pos[0] for pos in recent) / len(recent)
        avg_col = sum(pos[1] for pos in recent) / len(recent)

        # Calculate direction away from center of mass
        dr = state.row - avg_row
        dc = state.col - avg_col

        # Escape perpendicular to our oscillation axis
        if abs(dr) < abs(dc):
            # Oscillating more east-west, escape north or south
            return "south" if dr >= 0 else "north"
        else:
            # Oscillating more north-south, escape east or west
            return "east" if dc >= 0 else "west"

    def get_escape_debug_info(self, state: AgentState, stuck_reason: str = "") -> dict:
        """Get debug info dict for escape mode.

        Useful for behaviors to populate their debug_info when escaping.
        """
        return {
            "mode": "escape",
            "goal": f"escape_{state.escape_direction}" if state.escape_direction else "escape",
            "target_object": "-",
            "signal": stuck_reason or f"until_step_{state.escape_until_step}",
        }
