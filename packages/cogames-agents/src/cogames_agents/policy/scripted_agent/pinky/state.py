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

    # Exploration state
    exploration_direction: Optional[str] = None
    exploration_direction_step: int = 0

    # Stuck detection
    position_history: list[tuple[int, int]] = field(default_factory=list)

    # Track last action for position updates
    last_action: Action = field(default_factory=lambda: Action(name="noop"))
    last_action_executed: Optional[str] = None
    using_object_this_step: bool = False


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
    agent_occupancy: set[tuple[int, int]] = field(default_factory=set)

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
