"""Scrambler goals — neutralize enemy junctions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from cogames_agents.policy.scripted_agent.planky.goal import Goal
from cogames_agents.policy.scripted_agent.planky.navigator import _manhattan
from mettagrid.simulator import Action

from .gear import GetGearGoal

if TYPE_CHECKING:
    from cogames_agents.policy.scripted_agent.planky.context import PlankyContext

JUNCTION_AOE_RANGE = 10


class GetScramblerGearGoal(GetGearGoal):
    """Get scrambler gear."""

    def __init__(self) -> None:
        super().__init__(
            gear_attr="scrambler_gear",
            station_type="scrambler_station",
            goal_name="GetScramblerGear",
        )


class ScrambleJunctionGoal(Goal):
    """Find and scramble enemy (clips) junctions.

    Tracks attempts per junction to avoid getting stuck.
    """

    name = "ScrambleJunction"
    MAX_ATTEMPTS_PER_TARGET = 5
    COOLDOWN_STEPS = 50

    def is_satisfied(self, ctx: PlankyContext) -> bool:
        # Never satisfied — always try to scramble more
        return False

    def execute(self, ctx: PlankyContext) -> Optional[Action]:
        target = self._find_best_target(ctx)
        if target is None:
            # Explore aggressively toward map edges
            return ctx.navigator.explore(
                ctx.state.position,
                ctx.map,
                direction_bias=["north", "east", "south", "west"][ctx.agent_id % 4],
            )

        if ctx.trace:
            ctx.trace.nav_target = target

        dist = _manhattan(ctx.state.position, target)
        if dist <= 1:
            # Track attempts on this specific junction
            attempts_key = f"scramble_attempts_{target}"
            attempts = ctx.blackboard.get(attempts_key, 0) + 1
            ctx.blackboard[attempts_key] = attempts

            if attempts > self.MAX_ATTEMPTS_PER_TARGET:
                # Mark this junction as failed temporarily
                failed_key = f"scramble_failed_{target}"
                ctx.blackboard[failed_key] = ctx.step
                ctx.blackboard[attempts_key] = 0
                if ctx.trace:
                    ctx.trace.activate(self.name, f"giving up on {target}")
                return ctx.navigator.explore(
                    ctx.state.position,
                    ctx.map,
                    direction_bias=["north", "east", "south", "west"][ctx.agent_id % 4],
                )

            if ctx.trace:
                ctx.trace.activate(self.name, f"bump {attempts}/{self.MAX_ATTEMPTS_PER_TARGET}")
            return _move_toward(ctx.state.position, target)

        # Not adjacent - reset attempts for this target
        attempts_key = f"scramble_attempts_{target}"
        ctx.blackboard[attempts_key] = 0
        return ctx.navigator.get_action(ctx.state.position, target, ctx.map, reach_adjacent=True)

    def _find_best_target(self, ctx: PlankyContext) -> tuple[int, int] | None:
        """Find enemy junction to scramble, prioritized by blocking count."""
        pos = ctx.state.position

        def recently_failed(p: tuple[int, int]) -> bool:
            failed_step = ctx.blackboard.get(f"scramble_failed_{p}", -9999)
            return ctx.step - failed_step < self.COOLDOWN_STEPS

        # Get clips junctions
        enemy: list[tuple[tuple[int, int], dict]] = []
        for jpos, e in ctx.map.find(type_contains="junction", property_filter={"alignment": "clips"}):
            if not recently_failed(jpos):
                enemy.append((jpos, e.properties))
        for cpos, e in ctx.map.find(type_contains="charger", property_filter={"alignment": "clips"}):
            if not recently_failed(cpos):
                enemy.append((cpos, e.properties))

        if not enemy:
            return None

        # Get neutral junctions for scoring
        neutral_positions: list[tuple[int, int]] = []
        for jpos, e in ctx.map.find(type_contains="junction"):
            if e.properties.get("alignment") is None:
                neutral_positions.append(jpos)
        for cpos, e in ctx.map.find(type_contains="charger"):
            if e.properties.get("alignment") is None:
                neutral_positions.append(cpos)

        # Score by: how many neutrals this enemy blocks, then by distance
        scored: list[tuple[int, int, tuple[int, int]]] = []
        for epos, _ in enemy:
            blocked = sum(1 for np in neutral_positions if _manhattan(epos, np) <= JUNCTION_AOE_RANGE)
            dist = _manhattan(pos, epos)
            scored.append((-blocked, dist, epos))  # Negative blocked for descending sort

        scored.sort()
        return scored[0][2]


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
