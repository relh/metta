from __future__ import annotations

from typing import Optional


def select_primary_tag(tags: list[str], *, priority_objects: Optional[set[str]] = None) -> str:
    if not tags:
        return "unknown"

    for tag in tags:
        if tag.startswith("type:"):
            return tag.split(":", 1)[1]

    if priority_objects:
        for tag in tags:
            if tag and not tag.startswith("collective:") and tag in priority_objects:
                return tag

    for tag in tags:
        if tag and not tag.startswith("collective:"):
            return tag

    for tag in tags:
        if tag:
            return tag

    return "unknown"


def derive_alignment(
    obj_name: str,
    clipped: int,
    collective_id: Optional[int],
    *,
    cogs_collective_id: Optional[int],
    clips_collective_id: Optional[int],
) -> Optional[str]:
    if collective_id is not None:
        if collective_id == cogs_collective_id:
            return "cogs"
        if collective_id == clips_collective_id:
            return "clips"

    if "cogs" in obj_name:
        return "cogs"
    if "clips" in obj_name or clipped > 0:
        return "clips"
    return None
