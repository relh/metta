"""Shared goals used by multiple roles."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cogames_agents.policy.scripted_agent.cogas.goal import Goal
from cogames_agents.policy.scripted_agent.cogas.navigator import _manhattan
from mettagrid.simulator import Action

if TYPE_CHECKING:
    from cogames_agents.policy.scripted_agent.cogas.context import CogasContext


class GetHeartsGoal(Goal):
    """Navigate to a chest to acquire hearts.

    Hearts cost 1 of each element from the collective. Skip if the
    collective can't afford it to avoid wasting time at the chest.
    """

    name = "GetHearts"
    # Cost per heart: 1 of each element
    HEART_COST = {"carbon": 1, "oxygen": 1, "germanium": 1, "silicon": 1}

    def __init__(self, min_hearts: int = 1) -> None:
        self._min_hearts = min_hearts

    # Minimum collective resource reserve — don't consume below this level
    # Reduced from 3 to 1 to allow earlier heart acquisition
    RESOURCE_RESERVE = 1

    def _collective_can_afford_heart(self, ctx: CogasContext) -> bool:
        s = ctx.state
        r = self.RESOURCE_RESERVE
        return (
            s.collective_carbon >= 1 + r
            and s.collective_oxygen >= 1 + r
            and s.collective_germanium >= 1 + r
            and s.collective_silicon >= 1 + r
        )

    def is_satisfied(self, ctx: CogasContext) -> bool:
        if ctx.state.heart >= self._min_hearts:
            return True
        # Skip if collective can't afford a heart
        if not self._collective_can_afford_heart(ctx):
            if ctx.trace:
                ctx.trace.skip(self.name, "collective lacks resources for heart")
            return True
        return False

    def execute(self, ctx: CogasContext) -> Action:
        # Find own team's chest
        pf = {"collective_id": ctx.my_collective_id} if ctx.my_collective_id is not None else None
        result = ctx.map.find_nearest(ctx.state.position, type_contains="chest", property_filter=pf)
        if result is None:
            # Try hub as fallback
            result = ctx.map.find_nearest(ctx.state.position, type_contains="hub", property_filter=pf)
        if result is None:
            return ctx.navigator.explore(ctx.state.position, ctx.map)

        chest_pos, _ = result
        if ctx.trace:
            ctx.trace.nav_target = chest_pos

        dist = _manhattan(ctx.state.position, chest_pos)
        if dist <= 1:
            return _move_toward(ctx.state.position, chest_pos)
        return ctx.navigator.get_action(ctx.state.position, chest_pos, ctx.map, reach_adjacent=True)


class FallbackMineGoal(Goal):
    """Fallback: mine resources when combat roles can't act.

    Used at the bottom of aligner/scrambler goal lists so they contribute
    to the economy instead of idling when they lack gear or hearts.

    NEVER satisfied - always provides something to do rather than noop.
    """

    name = "FallbackMine"

    def is_satisfied(self, ctx: CogasContext) -> bool:
        # Never satisfied - always mine/explore as fallback to avoid noops
        # This ensures aligners/scramblers always have productive work
        return False

    def execute(self, ctx: CogasContext) -> Action:
        from .miner import RESOURCE_TYPES, _extractor_recently_failed

        # If carrying resources, deposit first
        if ctx.state.cargo_total > 0:
            depot_pos = _find_deposit(ctx)
            if depot_pos is not None:
                if ctx.trace:
                    ctx.trace.nav_target = depot_pos
                dist = _manhattan(ctx.state.position, depot_pos)
                if dist <= 1:
                    return _move_toward(ctx.state.position, depot_pos)
                return ctx.navigator.get_action(ctx.state.position, depot_pos, ctx.map, reach_adjacent=True)

        # Find nearest usable extractor (any resource type)
        best: tuple[int, tuple[int, int]] | None = None
        for resource in RESOURCE_TYPES:
            for pos, e in ctx.map.find(type=f"{resource}_extractor"):
                if e.properties.get("remaining_uses", 999) <= 0:
                    continue
                if e.properties.get("inventory_amount", -1) == 0:
                    continue
                if _extractor_recently_failed(ctx, pos):
                    continue
                d = _manhattan(ctx.state.position, pos)
                if best is None or d < best[0]:
                    best = (d, pos)

        if best is not None:
            if ctx.trace:
                ctx.trace.nav_target = best[1]
            dist = best[0]
            if dist <= 1:
                return _move_toward(ctx.state.position, best[1])
            return ctx.navigator.get_action(ctx.state.position, best[1], ctx.map, reach_adjacent=True)

        # No extractors known — explore
        return ctx.navigator.explore(
            ctx.state.position,
            ctx.map,
            direction_bias=["north", "east", "south", "west"][ctx.agent_id % 4],
        )


def _find_deposit(ctx: "CogasContext") -> tuple[int, int] | None:
    """Find nearest cogs-aligned depot for depositing resources."""
    pos = ctx.state.position
    hub_filter = {"collective_id": ctx.my_collective_id} if ctx.my_collective_id is not None else None
    candidates: list[tuple[int, tuple[int, int]]] = []
    for apos, _ in ctx.map.find(type_contains="hub", property_filter=hub_filter):
        candidates.append((_manhattan(pos, apos), apos))
    for jpos, _ in ctx.map.find(type_contains="junction", property_filter={"alignment": "cogs"}):
        candidates.append((_manhattan(pos, jpos), jpos))
    if not candidates:
        return None
    candidates.sort()
    return candidates[0][1]


def _move_toward(current: tuple[int, int], target: tuple[int, int]) -> Action:
    dr = target[0] - current[0]
    dc = target[1] - current[1]
    if abs(dr) >= abs(dc):
        if dr > 0:
            return Action(name="move_south")
        elif dr < 0:
            return Action(name="move_north")
    if dc > 0:
        return Action(name="move_east")
    elif dc < 0:
        return Action(name="move_west")
    return Action(name="move_north")
