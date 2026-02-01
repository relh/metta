"""Sparse entity map for Cogas policy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Entity:
    """An object on the map."""

    type: str  # e.g. "carbon_extractor", "miner_station", "wall", "agent"
    properties: dict  # alignment, remaining_uses, inventory_amount, cooldown, etc.
    last_seen: int = 0


class EntityMap:
    """Sparse map of entities. Only stores non-empty cells."""

    def __init__(self) -> None:
        self.entities: dict[tuple[int, int], Entity] = {}
        self.explored: set[tuple[int, int]] = set()

    def update_from_observation(
        self,
        agent_pos: tuple[int, int],
        obs_half_height: int,
        obs_half_width: int,
        visible_entities: dict[tuple[int, int], Entity],
        step: int,
    ) -> None:
        """Update map from current observation window.

        All cells in the observation window are marked as explored.
        Entities in the window are overwritten with fresh data.
        Entities no longer visible in the window are removed.
        """
        # Mark all cells in observation window as explored
        for obs_r in range(2 * obs_half_height + 1):
            for obs_c in range(2 * obs_half_width + 1):
                r = obs_r - obs_half_height + agent_pos[0]
                c = obs_c - obs_half_width + agent_pos[1]
                self.explored.add((r, c))

        # Remove entities in observation window that are no longer visible
        window_min_r = agent_pos[0] - obs_half_height
        window_max_r = agent_pos[0] + obs_half_height
        window_min_c = agent_pos[1] - obs_half_width
        window_max_c = agent_pos[1] + obs_half_width

        to_remove = []
        for pos in self.entities:
            if window_min_r <= pos[0] <= window_max_r and window_min_c <= pos[1] <= window_max_c:
                if pos not in visible_entities:
                    to_remove.append(pos)
        for pos in to_remove:
            del self.entities[pos]

        # Add/update visible entities
        for pos, entity in visible_entities.items():
            entity.last_seen = step
            self.entities[pos] = entity

    def find(
        self,
        type: Optional[str] = None,
        type_contains: Optional[str] = None,
        property_filter: Optional[dict] = None,
    ) -> list[tuple[tuple[int, int], Entity]]:
        """Query entities by type and/or properties.

        Args:
            type: Exact type match
            type_contains: Substring match on type
            property_filter: Dict of property key-value pairs that must match
        """
        results = []
        for pos, entity in self.entities.items():
            if type is not None and entity.type != type:
                continue
            if type_contains is not None and type_contains not in entity.type:
                continue
            if property_filter is not None:
                match = all(entity.properties.get(k) == v for k, v in property_filter.items())
                if not match:
                    continue
            results.append((pos, entity))
        return results

    def find_nearest(
        self,
        from_pos: tuple[int, int],
        type: Optional[str] = None,
        type_contains: Optional[str] = None,
        property_filter: Optional[dict] = None,
        max_dist: Optional[int] = None,
    ) -> Optional[tuple[tuple[int, int], Entity]]:
        """Find nearest entity matching criteria."""
        matches = self.find(type=type, type_contains=type_contains, property_filter=property_filter)
        if not matches:
            return None

        best = None
        best_dist = float("inf")
        for pos, entity in matches:
            dist = abs(pos[0] - from_pos[0]) + abs(pos[1] - from_pos[1])
            if max_dist is not None and dist > max_dist:
                continue
            if dist < best_dist:
                best = (pos, entity)
                best_dist = dist
        return best

    def is_passable(self, pos: tuple[int, int]) -> bool:
        """Check if a position is passable (explored and not a wall/obstacle)."""
        if pos not in self.explored:
            return False
        entity = self.entities.get(pos)
        if entity is None:
            return True  # Explored empty cell
        # Agents are temporary obstacles, everything else is permanent
        if entity.type == "agent":
            return False
        # Walls are obstacles
        if entity.type == "wall":
            return False
        # Structures are obstacles (stations, extractors, junctions, etc.)
        # But we don't block pathfinding through them — goals that need adjacency
        # handle that via reach_adjacent=True
        return True  # Structures are passable for pathfinding

    def is_wall(self, pos: tuple[int, int]) -> bool:
        """Check if position is a wall."""
        entity = self.entities.get(pos)
        return entity is not None and entity.type == "wall"

    def is_structure(self, pos: tuple[int, int]) -> bool:
        """Check if position has a structure (non-wall, non-agent entity)."""
        entity = self.entities.get(pos)
        if entity is None:
            return False
        return entity.type not in ("wall", "agent")

    def is_free(self, pos: tuple[int, int]) -> bool:
        """Check if position is explored and has no entity."""
        return pos in self.explored and pos not in self.entities

    def has_agent(self, pos: tuple[int, int]) -> bool:
        """Check if position has an agent."""
        entity = self.entities.get(pos)
        return entity is not None and entity.type == "agent"
