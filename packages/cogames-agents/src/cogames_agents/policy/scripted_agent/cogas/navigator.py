"""Optimized A* navigator for CoGas agent.

Enhanced pathfinding with path caching, escalating stuck recovery,
multi-agent collision avoidance, frontier exploration, and waypoint system.
"""

from __future__ import annotations

import heapq
import random
from collections import deque
from enum import Enum, auto
from typing import TYPE_CHECKING, Optional

from mettagrid.simulator import Action

if TYPE_CHECKING:
    from cogames_agents.policy.scripted_agent.planky.entity_map import EntityMap

MOVE_DELTAS: dict[str, tuple[int, int]] = {
    "north": (-1, 0),
    "south": (1, 0),
    "east": (0, 1),
    "west": (0, -1),
}

DIRECTIONS = ["north", "south", "east", "west"]


class RecoveryStage(Enum):
    """Escalating stuck recovery stages."""

    NONE = auto()
    RANDOM_WALK = auto()
    SPIRAL = auto()
    RESET = auto()


class Navigator:
    """A* pathfinding with caching, stuck recovery, collision avoidance,
    frontier exploration, and waypoint system."""

    def __init__(self) -> None:
        # Path cache
        self._cached_path: Optional[list[tuple[int, int]]] = None
        self._cached_target: Optional[tuple[int, int]] = None
        self._cached_reach_adjacent: bool = False

        # Stuck detection
        self._position_history: list[tuple[int, int]] = []
        self._recovery_stage = RecoveryStage.NONE
        self._recovery_steps_remaining = 0
        self._spiral_direction_idx = 0
        self._spiral_leg_length = 1
        self._spiral_steps_in_leg = 0
        self._spiral_legs_done = 0

        # Waypoint system
        self._waypoints: dict[str, tuple[int, int]] = {}
        self._route_cache: dict[tuple[str, str], list[tuple[int, int]]] = {}

        # Multi-agent collision tracking
        self._agent_wait_count: dict[tuple[int, int], int] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_action(
        self,
        current: tuple[int, int],
        target: tuple[int, int],
        map: EntityMap,
        reach_adjacent: bool = False,
    ) -> Action:
        """Navigate from current to target using A*."""
        self._track_position(current)

        # Handle recovery mode
        if self._recovery_stage != RecoveryStage.NONE:
            action = self._execute_recovery(current, map)
            if action:
                return action

        # Check stuck
        if self._is_stuck():
            action = self._escalate_recovery(current, map)
            if action:
                return action

        # Already at target
        if current == target and not reach_adjacent:
            return Action(name="noop")

        # Adjacent to target in reach_adjacent mode
        if reach_adjacent and _manhattan(current, target) == 1:
            return Action(name="noop")

        # Get or compute path
        path = self._get_path(current, target, map, reach_adjacent)

        if not path:
            return self._move_toward_greedy(current, target, map)

        next_pos = path[0]

        # Multi-agent collision avoidance
        if map.has_agent(next_pos):
            return self._handle_agent_collision(current, next_pos, target, map)

        # Clear wait count for this direction
        self._agent_wait_count.pop(next_pos, None)

        # Advance along path
        self._cached_path = path[1:] if len(path) > 1 else None
        return _move_action(current, next_pos)

    def explore(
        self,
        current: tuple[int, int],
        map: EntityMap,
        direction_bias: Optional[str] = None,
    ) -> Action:
        """Navigate toward unexplored frontier cells."""
        self._track_position(current)

        if self._recovery_stage != RecoveryStage.NONE:
            action = self._execute_recovery(current, map)
            if action:
                return action

        if self._is_stuck():
            action = self._escalate_recovery(current, map)
            if action:
                return action

        frontier = self._find_frontier(current, map, direction_bias)
        if frontier:
            return self.get_action(current, frontier, map)

        return self._random_move(current, map)

    # ------------------------------------------------------------------
    # Waypoint system
    # ------------------------------------------------------------------

    def set_waypoint(self, name: str, pos: tuple[int, int]) -> None:
        """Register a named waypoint (e.g. 'base', 'extractor', 'junction')."""
        self._waypoints[name] = pos
        # Invalidate route cache involving this waypoint
        to_remove = [k for k in self._route_cache if name in k]
        for k in to_remove:
            del self._route_cache[k]

    def get_waypoint(self, name: str) -> Optional[tuple[int, int]]:
        """Get a registered waypoint position."""
        return self._waypoints.get(name)

    def navigate_waypoint(
        self,
        current: tuple[int, int],
        waypoint_name: str,
        map: EntityMap,
        reach_adjacent: bool = False,
    ) -> Action:
        """Navigate to a named waypoint."""
        target = self._waypoints.get(waypoint_name)
        if target is None:
            return self._random_move(current, map)
        return self.get_action(current, target, map, reach_adjacent=reach_adjacent)

    def navigate_route(
        self,
        current: tuple[int, int],
        waypoint_names: list[str],
        map: EntityMap,
        reach_adjacent: bool = False,
    ) -> Action:
        """Navigate along a sequence of waypoints. Returns action for the
        first waypoint that hasn't been reached yet."""
        for name in waypoint_names:
            target = self._waypoints.get(name)
            if target is None:
                continue
            dist = _manhattan(current, target)
            threshold = 1 if reach_adjacent else 0
            if dist > threshold:
                return self.get_action(current, target, map, reach_adjacent=reach_adjacent)
        # All waypoints reached
        return Action(name="noop")

    # ------------------------------------------------------------------
    # Path computation and caching
    # ------------------------------------------------------------------

    def _get_path(
        self,
        start: tuple[int, int],
        target: tuple[int, int],
        map: EntityMap,
        reach_adjacent: bool,
    ) -> Optional[list[tuple[int, int]]]:
        """Get cached path or compute new one."""
        if self._cached_path and self._cached_target == target and self._cached_reach_adjacent == reach_adjacent:
            # Verify first step is still valid (lightweight check)
            if self._cached_path and not map.has_agent(self._cached_path[0]):
                first = self._cached_path[0]
                if not map.is_wall(first) and not map.is_structure(first):
                    return self._cached_path

        # Compute new path
        goal_cells = self._compute_goals(target, map, reach_adjacent)
        if not goal_cells:
            return None

        # Try known terrain first
        path = self._astar(start, goal_cells, map, allow_unknown=False)
        if not path:
            path = self._astar(start, goal_cells, map, allow_unknown=True)

        self._cached_path = path.copy() if path else None
        self._cached_target = target
        self._cached_reach_adjacent = reach_adjacent
        return path

    def invalidate_cache(self) -> None:
        """Force recomputation on next get_action call."""
        self._cached_path = None
        self._cached_target = None

    def _compute_goals(
        self,
        target: tuple[int, int],
        map: EntityMap,
        reach_adjacent: bool,
    ) -> list[tuple[int, int]]:
        if not reach_adjacent:
            return [target]
        goals = []
        for dr, dc in MOVE_DELTAS.values():
            pos = (target[0] + dr, target[1] + dc)
            if self._is_traversable(pos, map, allow_unknown=True):
                goals.append(pos)
        return goals

    # ------------------------------------------------------------------
    # A* search
    # ------------------------------------------------------------------

    def _astar(
        self,
        start: tuple[int, int],
        goals: list[tuple[int, int]],
        map: EntityMap,
        allow_unknown: bool,
    ) -> list[tuple[int, int]]:
        """A* pathfinding with iteration limit."""
        goal_set = set(goals)
        if not goals:
            return []

        def h(pos: tuple[int, int]) -> int:
            return min(_manhattan(pos, g) for g in goals)

        tie = 0
        iterations = 0
        max_iterations = 5000

        open_set: list[tuple[int, int, tuple[int, int]]] = [(h(start), tie, start)]
        came_from: dict[tuple[int, int], Optional[tuple[int, int]]] = {start: None}
        g_score: dict[tuple[int, int], int] = {start: 0}

        while open_set and iterations < max_iterations:
            iterations += 1
            _, _, current = heapq.heappop(open_set)

            if current in goal_set:
                return self._reconstruct(came_from, current)

            current_g = g_score.get(current, float("inf"))
            if isinstance(current_g, float):
                continue

            for dr, dc in MOVE_DELTAS.values():
                neighbor = (current[0] + dr, current[1] + dc)
                is_goal = neighbor in goal_set
                if not is_goal and not self._is_traversable(neighbor, map, allow_unknown):
                    continue

                tentative_g = current_g + 1
                if tentative_g < g_score.get(neighbor, float("inf")):
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g
                    f = tentative_g + h(neighbor)
                    tie += 1
                    heapq.heappush(open_set, (f, tie, neighbor))

        return []

    def _reconstruct(
        self,
        came_from: dict[tuple[int, int], Optional[tuple[int, int]]],
        current: tuple[int, int],
    ) -> list[tuple[int, int]]:
        path = []
        while came_from[current] is not None:
            path.append(current)
            prev = came_from[current]
            assert prev is not None
            current = prev
        path.reverse()
        return path

    def _is_traversable(
        self,
        pos: tuple[int, int],
        map: EntityMap,
        allow_unknown: bool = False,
    ) -> bool:
        if map.is_wall(pos) or map.is_structure(pos):
            return False
        if map.has_agent(pos):
            return False
        if pos in map.explored:
            return pos not in map.entities or map.entities[pos].type == "agent"
        return allow_unknown

    # ------------------------------------------------------------------
    # Multi-agent collision avoidance
    # ------------------------------------------------------------------

    def _handle_agent_collision(
        self,
        current: tuple[int, int],
        blocked: tuple[int, int],
        target: tuple[int, int],
        map: EntityMap,
    ) -> Action:
        """Handle collision with another agent using escalating strategy."""
        wait_count = self._agent_wait_count.get(blocked, 0)
        self._agent_wait_count[blocked] = wait_count + 1

        # First encounter: try sidestep
        if wait_count < 2:
            sidestep = self._find_sidestep(current, blocked, target, map)
            if sidestep:
                self._cached_path = None
                return _move_action(current, sidestep)
            return Action(name="noop")

        # After waiting twice: force repath avoiding that cell
        self._cached_path = None
        self._agent_wait_count.pop(blocked, None)

        # Try alternate path
        sidestep = self._find_sidestep(current, blocked, target, map)
        if sidestep:
            return _move_action(current, sidestep)

        return self._random_move(current, map)

    def _find_sidestep(
        self,
        current: tuple[int, int],
        blocked: tuple[int, int],
        target: tuple[int, int],
        map: EntityMap,
    ) -> Optional[tuple[int, int]]:
        """Find sidestep around blocking agent."""
        current_dist = _manhattan(current, target)
        candidates = []
        for d in DIRECTIONS:
            dr, dc = MOVE_DELTAS[d]
            pos = (current[0] + dr, current[1] + dc)
            if pos == blocked:
                continue
            if not self._is_traversable(pos, map, allow_unknown=True):
                continue
            new_dist = _manhattan(pos, target)
            score = new_dist - current_dist
            candidates.append((score, pos))

        if not candidates:
            return None
        candidates.sort()
        if candidates[0][0] <= 2:
            return candidates[0][1]
        return None

    # ------------------------------------------------------------------
    # Stuck detection with escalating recovery
    # ------------------------------------------------------------------

    def _track_position(self, pos: tuple[int, int]) -> None:
        self._position_history.append(pos)
        if len(self._position_history) > 30:
            self._position_history.pop(0)

    def _is_stuck(self) -> bool:
        history = self._position_history
        if len(history) < 6:
            return False
        recent = history[-6:]
        if len(set(recent)) <= 2:
            return True
        if len(history) >= 20:
            current = history[-1]
            earlier = history[:-10]
            if earlier.count(current) >= 2:
                return True
        return False

    def _escalate_recovery(self, current: tuple[int, int], map: EntityMap) -> Optional[Action]:
        """Escalate to the next recovery stage."""
        self._cached_path = None
        self._cached_target = None

        if self._recovery_stage == RecoveryStage.NONE:
            self._recovery_stage = RecoveryStage.RANDOM_WALK
            self._recovery_steps_remaining = 5
        elif self._recovery_stage == RecoveryStage.RANDOM_WALK:
            self._recovery_stage = RecoveryStage.SPIRAL
            self._recovery_steps_remaining = 12
            self._spiral_direction_idx = random.randint(0, 3)
            self._spiral_leg_length = 1
            self._spiral_steps_in_leg = 0
            self._spiral_legs_done = 0
        else:
            self._recovery_stage = RecoveryStage.RESET
            self._recovery_steps_remaining = 1

        self._position_history.clear()
        return self._execute_recovery(current, map)

    def _execute_recovery(self, current: tuple[int, int], map: EntityMap) -> Optional[Action]:
        """Execute current recovery strategy."""
        if self._recovery_steps_remaining <= 0:
            self._recovery_stage = RecoveryStage.NONE
            return None

        self._recovery_steps_remaining -= 1

        if self._recovery_stage == RecoveryStage.RANDOM_WALK:
            return self._random_move(current, map)

        if self._recovery_stage == RecoveryStage.SPIRAL:
            return self._spiral_move(current, map)

        if self._recovery_stage == RecoveryStage.RESET:
            # Full reset: clear all state and do random move
            self._position_history.clear()
            self._cached_path = None
            self._cached_target = None
            self._agent_wait_count.clear()
            self._recovery_stage = RecoveryStage.NONE
            return self._random_move(current, map)

        self._recovery_stage = RecoveryStage.NONE
        return None

    def _spiral_move(self, current: tuple[int, int], map: EntityMap) -> Action:
        """Move in a spiral pattern to escape confined areas."""
        d = DIRECTIONS[self._spiral_direction_idx % 4]
        dr, dc = MOVE_DELTAS[d]
        pos = (current[0] + dr, current[1] + dc)

        self._spiral_steps_in_leg += 1

        # Advance spiral: after completing a leg, turn right and
        # increase leg length every two turns
        if self._spiral_steps_in_leg >= self._spiral_leg_length:
            self._spiral_steps_in_leg = 0
            self._spiral_direction_idx += 1
            self._spiral_legs_done += 1
            if self._spiral_legs_done % 2 == 0:
                self._spiral_leg_length += 1

        if self._is_traversable(pos, map, allow_unknown=True):
            return Action(name=f"move_{d}")

        # Can't move in spiral direction, try random
        return self._random_move(current, map)

    # ------------------------------------------------------------------
    # Frontier exploration
    # ------------------------------------------------------------------

    def _find_frontier(
        self,
        from_pos: tuple[int, int],
        map: EntityMap,
        direction_bias: Optional[str] = None,
    ) -> Optional[tuple[int, int]]:
        """BFS to find nearest unexplored cell adjacent to explored free cell."""
        if direction_bias == "north":
            deltas = [(-1, 0), (0, -1), (0, 1), (1, 0)]
        elif direction_bias == "south":
            deltas = [(1, 0), (0, -1), (0, 1), (-1, 0)]
        elif direction_bias == "east":
            deltas = [(0, 1), (-1, 0), (1, 0), (0, -1)]
        elif direction_bias == "west":
            deltas = [(0, -1), (-1, 0), (1, 0), (0, 1)]
        else:
            deltas = [(-1, 0), (1, 0), (0, -1), (0, 1)]

        visited: set[tuple[int, int]] = {from_pos}
        queue: deque[tuple[int, int, int]] = deque([(from_pos[0], from_pos[1], 0)])

        while queue:
            r, c, dist = queue.popleft()
            if dist > 50:
                continue

            for dr, dc in deltas:
                nr, nc = r + dr, c + dc
                pos = (nr, nc)
                if pos in visited:
                    continue
                visited.add(pos)

                if pos not in map.explored:
                    for dr2, dc2 in deltas:
                        adj = (nr + dr2, nc + dc2)
                        if adj in map.explored and map.is_free(adj):
                            return pos
                    continue

                if map.is_free(pos):
                    queue.append((nr, nc, dist + 1))

        return None

    # ------------------------------------------------------------------
    # Basic movement helpers
    # ------------------------------------------------------------------

    def _random_move(self, current: tuple[int, int], map: EntityMap) -> Action:
        dirs = list(DIRECTIONS)
        random.shuffle(dirs)
        for d in dirs:
            dr, dc = MOVE_DELTAS[d]
            pos = (current[0] + dr, current[1] + dc)
            if pos in map.explored and not map.is_wall(pos) and not map.is_structure(pos):
                return Action(name=f"move_{d}")
        for d in dirs:
            dr, dc = MOVE_DELTAS[d]
            pos = (current[0] + dr, current[1] + dc)
            if not map.is_wall(pos):
                return Action(name=f"move_{d}")
        return Action(name="noop")

    def _move_toward_greedy(self, current: tuple[int, int], target: tuple[int, int], map: EntityMap) -> Action:
        """Move greedily toward target without pathfinding."""
        dr = target[0] - current[0]
        dc = target[1] - current[1]

        if abs(dr) >= abs(dc):
            primary = "south" if dr > 0 else "north"
            secondary = "east" if dc > 0 else "west"
        else:
            primary = "east" if dc > 0 else "west"
            secondary = "south" if dr > 0 else "north"

        for d in [primary, secondary]:
            ddr, ddc = MOVE_DELTAS[d]
            pos = (current[0] + ddr, current[1] + ddc)
            if not map.is_wall(pos) and not map.is_structure(pos) and not map.has_agent(pos):
                return Action(name=f"move_{d}")

        return self._random_move(current, map)


def _manhattan(a: tuple[int, int], b: tuple[int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _move_action(current: tuple[int, int], target: tuple[int, int]) -> Action:
    """Return move action from current to adjacent target."""
    dr = target[0] - current[0]
    dc = target[1] - current[1]
    if dr == -1 and dc == 0:
        return Action(name="move_north")
    if dr == 1 and dc == 0:
        return Action(name="move_south")
    if dr == 0 and dc == 1:
        return Action(name="move_east")
    if dr == 0 and dc == -1:
        return Action(name="move_west")
    return Action(name="noop")
