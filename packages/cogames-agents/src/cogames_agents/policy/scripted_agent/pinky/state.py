"""
State classes for Pinky policy.

AgentState, MapKnowledge, and NavigationState dataclasses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from mettagrid.simulator import Action

if TYPE_CHECKING:
    from mettagrid.simulator.interface import AgentObservation

from .types import CellType, DebugInfo, Role, StructureInfo, StructureType


@dataclass
class NavigationState:
    """Navigation-related state managed by Navigator service."""

    # Path caching
    cached_path: Optional[list[tuple[int, int]]] = None
    cached_path_target: Optional[tuple[int, int]] = None
    cached_path_reach_adjacent: bool = False

    # Exploration state (expanding box pattern)
    explore_origin: Optional[tuple[int, int]] = None
    explore_start_step: int = 0
    explore_radius: int = 15  # Initial exploration radius, grows by 10% when area exhausted
    explore_last_mineral_step: int = 0  # Last step we saw a mineral
    # Resource rotation for miners - track recently gathered resources
    last_resource_types: list[str] = field(default_factory=list)  # Most recent first, max 4
    # Current extractor target - track to detect stuck/empty situations
    current_extractor_target: Optional[tuple[int, int]] = None
    steps_at_current_extractor: int = 0  # Steps spent at/near current target without cargo gain
    failed_extractors: set[tuple[int, int]] = field(default_factory=set)  # Extractors that gave nothing
    # Legacy fields (kept for compatibility)
    exploration_direction: Optional[str] = None
    exploration_direction_step: int = 0

    # Stuck detection
    position_history: list[tuple[int, int]] = field(default_factory=list)

    # Track last action for position updates
    last_action: Action = field(default_factory=lambda: Action(name="noop"))
    last_action_executed: Optional[str] = None
    using_object_this_step: bool = False


@dataclass
class AgentSighting:
    """Information about a sighted agent."""

    position: tuple[int, int]
    last_seen_step: int


@dataclass
class MapKnowledge:
    """What the agent has discovered about the world."""

    grid_size: int = 200

    # Occupancy grid: CellType.FREE or CellType.OBSTACLE
    occupancy: list[list[int]] = field(default_factory=list)

    # Which cells have been observed
    explored: list[list[bool]] = field(default_factory=list)

    # All discovered structures: position -> StructureInfo
    structures: dict[tuple[int, int], StructureInfo] = field(default_factory=dict)

    # Quick lookups (station_name -> position)
    stations: dict[str, tuple[int, int]] = field(default_factory=dict)

    # Other agents' positions (for collision avoidance)
    # Current observation: positions of agents seen this step
    agent_occupancy: set[tuple[int, int]] = field(default_factory=set)

    # Recently seen agents with last-known positions
    # Cleared when observation window passes over their position without seeing them
    recent_agents: dict[tuple[int, int], AgentSighting] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Initialize grids if empty."""
        if not self.occupancy:
            # Initialize to UNKNOWN - cells become FREE/OBSTACLE when observed
            self.occupancy = [[CellType.UNKNOWN.value] * self.grid_size for _ in range(self.grid_size)]
        if not self.explored:
            self.explored = [[False] * self.grid_size for _ in range(self.grid_size)]

    # === Structure query methods ===

    def get_structures_by_type(self, structure_type: StructureType) -> list[StructureInfo]:
        """Get all structures of a given type."""
        return [s for s in self.structures.values() if s.structure_type == structure_type]

    def get_junctions(self) -> list[StructureInfo]:
        """Get all known junctions."""
        return self.get_structures_by_type(StructureType.JUNCTION)

    def get_extractors(self) -> list[StructureInfo]:
        """Get all known extractors."""
        return self.get_structures_by_type(StructureType.EXTRACTOR)

    def get_usable_extractors(self) -> list[StructureInfo]:
        """Get all usable extractors (not depleted)."""
        return [s for s in self.structures.values() if s.is_usable_extractor()]

    def get_cogs_junctions(self) -> list[StructureInfo]:
        """Get all cogs-aligned junctions (safe zones)."""
        return [j for j in self.get_junctions() if j.is_cogs_aligned()]

    def get_clips_junctions(self) -> list[StructureInfo]:
        """Get all clips-aligned junctions (enemy zones)."""
        return [j for j in self.get_junctions() if j.is_clips_aligned()]

    def get_neutral_junctions(self) -> list[StructureInfo]:
        """Get all neutral junctions."""
        return [j for j in self.get_junctions() if j.is_neutral()]

    def get_structure_at(self, pos: tuple[int, int]) -> Optional[StructureInfo]:
        """Get structure at a specific position."""
        return self.structures.get(pos)

    def find_nearest_unexplored(
        self, from_pos: tuple[int, int], max_dist: int = 50, direction_bias: Optional[str] = None
    ) -> Optional[tuple[int, int]]:
        """Find the nearest unexplored frontier cell.

        A frontier cell is an unexplored cell adjacent to an explored FREE cell.
        This guides exploration toward the edges of known territory.

        Args:
            from_pos: Starting position (row, col)
            max_dist: Maximum search distance
            direction_bias: Optional bias direction ('north', 'south', 'east', 'west')
                           to spread agents across the map

        Returns:
            Position of nearest frontier cell, or None if none found
        """
        from collections import deque

        r, c = from_pos
        visited = set()
        queue: deque[tuple[int, int, int]] = deque([(r, c, 0)])  # (row, col, distance)
        visited.add((r, c))

        # Direction deltas with bias ordering
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

        while queue:
            cr, cc, dist = queue.popleft()

            if dist > max_dist:
                continue

            for dr, dc in deltas:
                nr, nc = cr + dr, cc + dc

                if (nr, nc) in visited:
                    continue
                if not (0 <= nr < self.grid_size and 0 <= nc < self.grid_size):
                    continue

                visited.add((nr, nc))

                # Check if this is a frontier cell (unexplored, adjacent to explored FREE)
                if not self.explored[nr][nc]:
                    # Check if any neighbor is explored and FREE
                    for dr2, dc2 in deltas:
                        nnr, nnc = nr + dr2, nc + dc2
                        if 0 <= nnr < self.grid_size and 0 <= nnc < self.grid_size:
                            if self.explored[nnr][nnc] and self.occupancy[nnr][nnc] == CellType.FREE.value:
                                return (nr, nc)

                # Only expand through explored FREE cells
                if self.explored[cr][cc] and self.occupancy[cr][cc] == CellType.FREE.value:
                    queue.append((nr, nc, dist + 1))

        return None


@dataclass
class AgentState:
    """Complete state for a Pinky agent."""

    agent_id: int
    role: Role = Role.MINER

    # Current vibe (read from observation)
    vibe: str = "default"

    # Step counter
    step: int = 0

    # Position (relative to spawn, stored at grid center)
    row: int = 100
    col: int = 100

    # Inventory
    energy: int = 100
    hp: int = 100
    carbon: int = 0
    oxygen: int = 0
    germanium: int = 0
    silicon: int = 0
    heart: int = 0
    influence: int = 0

    # Collective inventory (observed from stats tokens)
    collective_carbon: int = 0
    collective_oxygen: int = 0
    collective_germanium: int = 0
    collective_silicon: int = 0

    # Gear (presence = equipped)
    miner_gear: bool = False
    scout_gear: bool = False
    aligner_gear: bool = False
    scrambler_gear: bool = False

    # Map knowledge
    map: MapKnowledge = field(default_factory=MapKnowledge)

    # Navigation state
    nav: NavigationState = field(default_factory=NavigationState)

    # Recently visited extractor positions (for cooldown avoidance)
    recently_mined: list[tuple[int, int]] = field(default_factory=list)

    # Track cargo changes to detect extraction failure (inventory full)
    prev_total_cargo: int = 0
    steps_without_cargo_gain: int = 0  # Consecutive steps where cargo didn't increase

    # Gear retry tracking: when gear is lost, track retry timing
    # If station doesn't give gear, explore/mine for 200 ticks then retry
    last_gear_attempt_step: int = 0  # Step when we last tried to get gear from station
    had_gear_last_step: bool = False  # Whether we had gear last step (detect gear loss)

    # Stuck detection: track consecutive steps at same position
    last_position: tuple[int, int] = (100, 100)
    steps_at_same_position: int = 0

    # Escape mode: when stuck, commit to escaping for several steps
    escape_direction: Optional[str] = None  # Direction to escape (north/south/east/west)
    escape_until_step: int = 0  # Keep escaping until this step

    # Aligner target tracking: current junction being targeted
    aligner_target: Optional[tuple[int, int]] = None

    # Last observation (for relative direction calculations)
    last_obs: Optional["AgentObservation"] = None

    # Debug info (populated by behaviors when debug is enabled)
    debug_info: DebugInfo = field(default_factory=DebugInfo)

    # === Computed properties ===

    @property
    def pos(self) -> tuple[int, int]:
        """Current position as tuple."""
        return (self.row, self.col)

    @property
    def total_cargo(self) -> int:
        """Total resources currently carried."""
        return self.carbon + self.oxygen + self.germanium + self.silicon

    @property
    def cargo_capacity(self) -> int:
        """Cargo capacity (base 4, +40 with miner gear)."""
        return 4 + (40 if self.miner_gear else 0)

    def has_gear(self, role: Optional[Role] = None) -> bool:
        """Check if agent has gear for the specified role (or their own role)."""
        check_role = role or self.role
        if check_role == Role.MINER:
            return self.miner_gear
        elif check_role == Role.SCOUT:
            return self.scout_gear
        elif check_role == Role.ALIGNER:
            return self.aligner_gear
        elif check_role == Role.SCRAMBLER:
            return self.scrambler_gear
        return False
