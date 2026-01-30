"""
Types and constants for Pinky policy.

Enums, StructureInfo, and role-related definitions.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from cogames_agents.policy.scripted_agent.common import roles as common_roles

Role = common_roles.Role
ROLE_TO_STATION = common_roles.ROLE_TO_STATION
VIBE_TO_ROLE = common_roles.VIBE_TO_ROLE


class RiskTolerance(Enum):
    """Risk tolerance levels for different roles."""

    CONSERVATIVE = "conservative"  # Miners - stay in safe zones
    MODERATE = "moderate"  # Aligners - venture out carefully
    AGGRESSIVE = "aggressive"  # Scouts, Scramblers - deep territory


# Map roles to their risk tolerance
ROLE_RISK_TOLERANCE: dict[Role, RiskTolerance] = {
    Role.MINER: RiskTolerance.CONSERVATIVE,
    Role.SCOUT: RiskTolerance.AGGRESSIVE,
    Role.ALIGNER: RiskTolerance.MODERATE,
    Role.SCRAMBLER: RiskTolerance.AGGRESSIVE,
}


class CellType(Enum):
    """Occupancy map cell states."""

    UNKNOWN = 0  # Not yet explored
    FREE = 1  # Passable (can walk through)
    OBSTACLE = 2  # Impassable (walls, stations, extractors)


class StructureType(Enum):
    """Types of structures in the game."""

    HUB = "hub"  # Main hub / resource deposit point (cogs nexus)
    JUNCTION = "junction"  # Territory control point (charger/supply depot)
    MINER_STATION = "miner_station"
    SCOUT_STATION = "scout_station"
    ALIGNER_STATION = "aligner_station"
    SCRAMBLER_STATION = "scrambler_station"
    EXTRACTOR = "extractor"  # Resource source
    CHEST = "chest"  # Heart source
    WALL = "wall"
    UNKNOWN = "unknown"


@dataclass
class StructureInfo:
    """Information about a discovered structure."""

    position: tuple[int, int]
    structure_type: StructureType
    name: str  # Original object name

    # When we last saw this structure
    last_seen_step: int = 0

    # Alignment: "cogs", "clips", or None (neutral)
    alignment: Optional[str] = None

    # Extractor-specific attributes
    resource_type: Optional[str] = None  # carbon, oxygen, germanium, silicon
    remaining_uses: int = 999
    cooldown_remaining: int = 0
    inventory_amount: int = -1  # -1 = unknown (protocol-based), 0+ = chest-based with that amount
    has_inventory: bool = False  # True once we've seen inv: tokens for this extractor

    def is_usable_extractor(self) -> bool:
        """Check if this is a usable extractor (not depleted, has resources).

        Protocol-based extractors: Only check remaining_uses > 0
        Chest-based extractors: Also check inventory_amount > 0
        """
        if self.structure_type != StructureType.EXTRACTOR:
            return False
        if self.remaining_uses <= 0:
            return False
        # If we've never seen inventory tokens, assume protocol-based (usable if remaining_uses > 0)
        if not self.has_inventory:
            return True
        # Chest-based: must have inventory > 0
        return self.inventory_amount > 0

    def is_cogs_aligned(self) -> bool:
        """Check if this structure is aligned to cogs."""
        return self.alignment == "cogs"

    def is_clips_aligned(self) -> bool:
        """Check if this structure is aligned to clips."""
        return self.alignment == "clips"

    def is_neutral(self) -> bool:
        """Check if this structure is neutral (unaligned)."""
        return self.alignment is None


# Game constants
JUNCTION_AOE_RANGE = 10  # AOE range of junctions
HP_DRAIN_OUTSIDE_SAFE_ZONE = 1  # HP lost per step outside safe zone
HP_DRAIN_NEAR_ENEMY = 1  # Additional HP lost near enemy junctions
ENERGY_MOVE_COST = 2  # Energy cost per move
HP_SAFETY_MARGIN = 10  # Buffer HP to keep before retreating


# Debug flag (legacy, now controlled via URI param)
DEBUG = False


@dataclass
class DebugInfo:
    """Structured debug info about agent's current intent."""

    mode: str = "idle"  # Current behavior mode (e.g., "mine", "deposit", "retreat")
    goal: str = ""  # Current goal description
    target_object: str = ""  # Object being targeted
    target_pos: Optional[tuple[int, int]] = None  # Target position
    signal: str = ""  # Event signal (e.g., "extract_failed_cargo_full", "hp_too_low")

    def format(self, role: str, action_name: str) -> str:
        """Format as role:mode:goal:target:action[:signal]."""
        target = self.target_object or (str(self.target_pos) if self.target_pos else "-")
        base = f"{role}:{self.mode}:{self.goal or '-'}:{target}:{action_name}"
        if self.signal:
            return f"{base}:{self.signal}"
        return base
