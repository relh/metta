from __future__ import annotations

MOVE_DELTAS: dict[str, tuple[int, int]] = {
    "north": (-1, 0),
    "south": (1, 0),
    "east": (0, 1),
    "west": (0, -1),
}

DIRECTIONS = ["north", "south", "east", "west"]


def manhattan(a: tuple[int, int], b: tuple[int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def manhattan_distance(a: tuple[int, int], b: tuple[int, int]) -> int:
    return manhattan(a, b)


def is_adjacent(pos1: tuple[int, int], pos2: tuple[int, int]) -> bool:
    dr = abs(pos1[0] - pos2[0])
    dc = abs(pos1[1] - pos2[1])
    return (dr == 1 and dc == 0) or (dr == 0 and dc == 1)
