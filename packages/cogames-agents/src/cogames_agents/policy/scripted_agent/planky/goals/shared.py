"""Shared goals used by multiple roles."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cogames_agents.policy.scripted_agent.planky.goal import Goal
from cogames_agents.policy.scripted_agent.planky.navigator import _manhattan
from mettagrid.simulator import Action

if TYPE_CHECKING:
    from cogames_agents.policy.scripted_agent.planky.context import PlankyContext


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
    RESOURCE_RESERVE = 3

    def _collective_can_afford_heart(self, ctx: PlankyContext) -> bool:
        s = ctx.state
        r = self.RESOURCE_RESERVE
        return (
            s.collective_carbon >= 1 + r
            and s.collective_oxygen >= 1 + r
            and s.collective_germanium >= 1 + r
            and s.collective_silicon >= 1 + r
        )

    def is_satisfied(self, ctx: PlankyContext) -> bool:
        if ctx.state.heart >= self._min_hearts:
            return True
        # Skip if collective can't afford a heart
        if not self._collective_can_afford_heart(ctx):
            if ctx.trace:
                ctx.trace.skip(self.name, "collective lacks resources for heart")
            return True
        return False

    def execute(self, ctx: PlankyContext) -> Action:
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


class EmergencyMineGoal(Goal):
    """Emergency mining: all cogs mine when any resource is critically low.

    Activates when any resource < CRITICAL_LOW and agent has no hearts.
    Stays active until all resources > RECOVERY_THRESHOLD.
    Agents with hearts should use them (hearts are valuable), so they skip this.
    """

    name = "EmergencyMine"
    CRITICAL_LOW = 10  # Trigger emergency when any resource below this
    RECOVERY_THRESHOLD = 20  # Exit emergency when all resources above this

    def is_satisfied(self, ctx: PlankyContext) -> bool:
        # Agents with hearts should use them, not mine
        if ctx.state.heart > 0:
            if ctx.trace:
                ctx.trace.skip(self.name, f"has {ctx.state.heart} hearts")
            return True

        s = ctx.state
        resources = [s.collective_carbon, s.collective_oxygen, s.collective_germanium, s.collective_silicon]
        min_resource = min(resources)

        # Check if we're in emergency mode (tracked in blackboard)
        in_emergency = ctx.blackboard.get("_emergency_mine_active", False)

        if in_emergency:
            # Stay in emergency until all resources > RECOVERY_THRESHOLD
            if all(r > self.RECOVERY_THRESHOLD for r in resources):
                ctx.blackboard["_emergency_mine_active"] = False
                if ctx.trace:
                    ctx.trace.skip(self.name, f"recovered, all resources > {self.RECOVERY_THRESHOLD}")
                return True
            # Still in emergency
            return False
        else:
            # Enter emergency if any resource < CRITICAL_LOW
            if min_resource < self.CRITICAL_LOW:
                ctx.blackboard["_emergency_mine_active"] = True
                return False
            return True

    def execute(self, ctx: PlankyContext) -> Action:
        from .miner import RESOURCE_TYPES, _extractor_recently_failed  # noqa: PLC0415

        s = ctx.state
        collective = {
            "carbon": s.collective_carbon,
            "oxygen": s.collective_oxygen,
            "germanium": s.collective_germanium,
            "silicon": s.collective_silicon,
        }

        # Find the lowest resource
        lowest_resource = min(RESOURCE_TYPES, key=lambda r: collective[r])

        if ctx.trace:
            ctx.trace.activate(self.name, f"EMERGENCY: {lowest_resource}={collective[lowest_resource]}")

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

        # Find extractor for the lowest resource
        target_pos: tuple[int, int] | None = None
        best_dist = 9999
        for pos, e in ctx.map.find(type=f"{lowest_resource}_extractor"):
            if e.properties.get("remaining_uses", 999) <= 0:
                continue
            if e.properties.get("inventory_amount", -1) == 0:
                continue
            if _extractor_recently_failed(ctx, pos):
                continue
            d = _manhattan(ctx.state.position, pos)
            if d < best_dist:
                best_dist = d
                target_pos = pos

        # If no extractor for lowest resource, try any extractor
        if target_pos is None:
            for resource in RESOURCE_TYPES:
                for pos, e in ctx.map.find(type=f"{resource}_extractor"):
                    if e.properties.get("remaining_uses", 999) <= 0:
                        continue
                    if e.properties.get("inventory_amount", -1) == 0:
                        continue
                    if _extractor_recently_failed(ctx, pos):
                        continue
                    d = _manhattan(ctx.state.position, pos)
                    if d < best_dist:
                        best_dist = d
                        target_pos = pos

        if target_pos is not None:
            if ctx.trace:
                ctx.trace.nav_target = target_pos
            if best_dist <= 1:
                return _move_toward(ctx.state.position, target_pos)
            return ctx.navigator.get_action(ctx.state.position, target_pos, ctx.map, reach_adjacent=True)

        # No extractors known — explore
        return ctx.navigator.explore(
            ctx.state.position,
            ctx.map,
            direction_bias=["north", "east", "south", "west"][ctx.agent_id % 4],
        )


class FallbackMineGoal(Goal):
    """Fallback: mine resources when combat roles can't act.

    Used at the bottom of aligner/scrambler goal lists so they contribute
    to the economy instead of idling when they lack gear or hearts.
    """

    name = "FallbackMine"

    def is_satisfied(self, ctx: PlankyContext) -> bool:
        from .miner import _collective_resources_sufficient  # noqa: PLC0415

        # Stop fallback mining when collective is well-stocked
        if _collective_resources_sufficient(ctx) and ctx.state.cargo_total == 0:
            return True
        return False

    def execute(self, ctx: PlankyContext) -> Action:
        from .miner import RESOURCE_TYPES, _extractor_recently_failed  # noqa: PLC0415

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


def _find_deposit(ctx: "PlankyContext") -> tuple[int, int] | None:
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
