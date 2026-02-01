"""Context and state snapshot for Cogas policy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from .entity_map import EntityMap
    from .navigator import Navigator
    from .trace import TraceLog


@dataclass
class StateSnapshot:
    """Rebuilt every tick from observation tokens. Observation is source of truth."""

    position: tuple[int, int] = (0, 0)

    # Inventory
    carbon: int = 0
    oxygen: int = 0
    germanium: int = 0
    silicon: int = 0
    heart: int = 0
    influence: int = 0
    hp: int = 100
    energy: int = 100

    # Gear flags
    miner_gear: bool = False
    scout_gear: bool = False
    aligner_gear: bool = False
    scrambler_gear: bool = False

    # Vibe
    vibe: str = "default"

    # Collective inventory
    collective_carbon: int = 0
    collective_oxygen: int = 0
    collective_germanium: int = 0
    collective_silicon: int = 0
    collective_heart: int = 0
    collective_influence: int = 0

    @property
    def cargo_total(self) -> int:
        return self.carbon + self.oxygen + self.germanium + self.silicon

    @property
    def cargo_capacity(self) -> int:
        return 40 if self.miner_gear else 4


@dataclass
class CogasContext:
    """Passed to all goals, bundles everything needed for decision-making."""

    state: StateSnapshot
    map: EntityMap
    blackboard: dict[str, Any]
    navigator: Navigator
    trace: Optional[TraceLog]
    action_names: list[str]
    agent_id: int
    step: int
    my_collective_id: Optional[int] = None
