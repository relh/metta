from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID


@dataclass
class GroupedMatchRows:
    assignments: list[int]
    players: list[tuple[int, float | None, UUID]] = field(default_factory=list)
    episode_id: UUID | None = None


def group_match_rows(rows: list[Any], *, include_episode_id: bool = False) -> dict[UUID, GroupedMatchRows]:
    grouped: dict[UUID, GroupedMatchRows] = {}
    for row in rows:
        match_id = row.match_id
        entry = grouped.get(match_id)
        if entry is None:
            entry = GroupedMatchRows(assignments=row.assignments or [])
            if include_episode_id and row.episode_id:
                entry.episode_id = UUID(str(row.episode_id))
            grouped[match_id] = entry
        entry.players.append((row.policy_index, row.score, row.policy_version_id))
    return grouped
