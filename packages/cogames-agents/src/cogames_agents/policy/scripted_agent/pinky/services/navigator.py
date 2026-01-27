"""
Navigator service for Pinky policy.

Handles pathfinding, movement, stuck detection, and exploration.
"""

from __future__ import annotations

import random
from collections import deque
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

        Uses the map built from previous observations. First tries to find a path
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

        # Check cached path (invalidate if path goes through now-blocked cells)
        path = self._get_cached_path(state, target, reach_adjacent)

        # Compute new path if needed
        if path is None:
            # First try to find path through known terrain only
            path = self._shortest_path(state, start, goal_cells, allow_unknown=False)

            # If no known path, try allowing unknown cells (exploration)
            if not path:
                if DEBUG:
                    print(f"[A{state.agent_id}] NAV: No known path to {target}, trying through unknown")
                path = self._shortest_path(state, start, goal_cells, allow_unknown=True)

            state.nav.cached_path = path.copy() if path else None
            state.nav.cached_path_target = target
            state.nav.cached_path_reach_adjacent = reach_adjacent

        if not path:
            if DEBUG:
                print(f"[A{state.agent_id}] NAV: No path to {target}, exploring")
            return self.explore(state)

        next_pos = path[0]

        # Advance cached path
        if state.nav.cached_path:
            state.nav.cached_path = state.nav.cached_path[1:]
            if not state.nav.cached_path:
                state.nav.cached_path = None
                state.nav.cached_path_target = None

        return self._move_toward(state, next_pos)

    def explore(self, state: AgentState) -> Action:
        """Systematic exploration - prioritize moving toward unknown areas.

        Uses the internal map to prefer directions that lead to unexplored territory.
        """
        # Check for stuck loop
        if self._is_stuck(state):
            action = self._break_stuck(state)
            if action:
                return action

        # Continue in current direction if set and heading toward unknown
        if state.nav.exploration_direction:
            steps_in_direction = state.step - state.nav.exploration_direction_step
            if steps_in_direction < 8:  # Explore 8 steps before turning (covers observation radius)
                dr, dc = self.MOVE_DELTAS.get(state.nav.exploration_direction, (0, 0))
                next_r, next_c = state.row + dr, state.col + dc
                # Allow moving into unknown cells during exploration
                if self._is_traversable(state, next_r, next_c, allow_unknown=True):
                    return Action(name=f"move_{state.nav.exploration_direction}")

        # Pick next direction - prioritize directions leading to unknown territory
        direction_cycle = ["east", "south", "west", "north"]
        current_dir = state.nav.exploration_direction
        if current_dir in direction_cycle:
            idx = direction_cycle.index(current_dir)
            next_idx = (idx + 1) % 4
        else:
            next_idx = 0

        # Score each direction by how much unknown territory it leads to
        direction_scores: list[tuple[int, str]] = []
        for direction in direction_cycle:
            dr, dc = self.MOVE_DELTAS[direction]
            next_r, next_c = state.row + dr, state.col + dc

            if not self._is_traversable(state, next_r, next_c, allow_unknown=True):
                continue

            # Count unknown cells in this direction (look ahead several cells)
            unknown_count = 0
            for dist in range(1, 6):
                check_r, check_c = state.row + dr * dist, state.col + dc * dist
                if self._is_in_bounds(state, check_r, check_c):
                    if state.map.occupancy[check_r][check_c] == CellType.UNKNOWN.value:
                        unknown_count += 1

            direction_scores.append((unknown_count, direction))

        # Sort by unknown count (descending) - prefer directions with more unknown territory
        direction_scores.sort(key=lambda x: -x[0])

        if DEBUG and state.step == 10 and state.agent_id == 0:
            print(f"[NAV] Exploration scores: {direction_scores}")

        # Try directions in order of score, then fall back to cycle order
        tried_directions = {d for _, d in direction_scores}
        for _, direction in direction_scores:
            dr, dc = self.MOVE_DELTAS[direction]
            next_r, next_c = state.row + dr, state.col + dc
            if self._is_traversable(state, next_r, next_c, allow_unknown=True):
                state.nav.exploration_direction = direction
                state.nav.exploration_direction_step = state.step
                return Action(name=f"move_{direction}")

        # Fall back to cycle order for any remaining directions
        for i in range(4):
            direction = direction_cycle[(next_idx + i) % 4]
            if direction in tried_directions:
                continue
            dr, dc = self.MOVE_DELTAS[direction]
            next_r, next_c = state.row + dr, state.col + dc
            traversable = self._is_traversable(state, next_r, next_c)
            if DEBUG and state.step == 10 and state.agent_id == 0:
                print(f"[NAV] Trying {direction}: pos={state.pos}+({dr},{dc})={next_r},{next_c} trav={traversable}")
            if traversable:
                state.nav.exploration_direction = direction
                state.nav.exploration_direction_step = state.step
                return Action(name=f"move_{direction}")

        return Action(name="noop")

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
        """Detect if agent is oscillating between positions (A→B→A→B).

        Only detects oscillation (exactly 2 positions), not staying still.
        Staying at 1 position might be intentional (using object repeatedly).
        """
        history = state.nav.position_history
        if len(history) < 6:
            return False

        # Check last 6 positions for oscillation
        recent = history[-6:]
        unique_positions = set(recent)

        # Only consider stuck if oscillating between exactly 2 positions
        # 1 position = intentional (using object), 3+ = making progress
        if len(unique_positions) == 2:
            if DEBUG:
                print(f"[A{state.agent_id}] NAV: Stuck! Oscillating between {unique_positions}")
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

        # Try random direction, allowing unknown cells to escape
        directions = list(self.DIRECTIONS)
        random.shuffle(directions)
        for direction in directions:
            dr, dc = self.MOVE_DELTAS[direction]
            nr, nc = state.row + dr, state.col + dc
            if self._is_traversable(state, nr, nc, allow_unknown=True):
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
        """Try to move around an obstacle toward target using internal map."""
        # Try directions, allowing unknown cells for exploration
        directions = list(self.DIRECTIONS)
        random.shuffle(directions)
        for direction in directions:
            dr, dc = self.MOVE_DELTAS[direction]
            nr, nc = state.row + dr, state.col + dc
            if self._is_traversable(state, nr, nc, allow_unknown=True):
                return Action(name=f"move_{direction}")
        return Action(name="noop")

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
    ) -> list[tuple[int, int]]:
        """BFS to find shortest path from start to any goal.

        Uses the internal map built from previous observations. Prefers known paths
        but can traverse unknown cells if allow_unknown=True.

        Args:
            state: Agent state with internal map
            start: Starting position
            goals: List of goal positions
            allow_unknown: If True, treat UNKNOWN cells as potentially traversable

        Note: Goal cells are reachable even if they are obstacles (for walking into objects).
        """
        goal_set = set(goals)
        queue: deque[tuple[int, int]] = deque([start])
        came_from: dict[tuple[int, int], Optional[tuple[int, int]]] = {start: None}

        while queue:
            current = queue.popleft()
            if current in goal_set:
                return self._reconstruct_path(came_from, current)

            for nr, nc in self._get_neighbors(state, current):
                if (nr, nc) in came_from:
                    continue
                # Allow reaching goal cells even if they're obstacles (objects to use)
                is_goal = (nr, nc) in goal_set
                if is_goal or self._is_traversable(state, nr, nc, allow_unknown=allow_unknown):
                    came_from[(nr, nc)] = current
                    queue.append((nr, nc))

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

    def _is_traversable(self, state: AgentState, r: int, c: int, allow_unknown: bool = False) -> bool:
        """Check if a cell is traversable.

        Args:
            state: Agent state
            r: Row coordinate
            c: Column coordinate
            allow_unknown: If True, treat UNKNOWN cells as potentially traversable (for exploration)

        Returns:
            True if the cell can be moved into
        """
        if not self._is_in_bounds(state, r, c):
            if DEBUG and state.step == 10 and state.agent_id == 0:
                print(f"[NAV] ({r},{c}) out of bounds")
            return False
        if (r, c) in state.map.agent_occupancy:
            if DEBUG and state.step == 10 and state.agent_id == 0:
                print(f"[NAV] ({r},{c}) has agent")
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
        """Get cached path if still valid."""
        if (
            state.nav.cached_path
            and state.nav.cached_path_target == target
            and state.nav.cached_path_reach_adjacent == reach_adjacent
        ):
            next_pos = state.nav.cached_path[0]
            if self._is_traversable(state, next_pos[0], next_pos[1]):
                return state.nav.cached_path
        return None
