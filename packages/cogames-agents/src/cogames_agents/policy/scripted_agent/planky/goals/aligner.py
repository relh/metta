"""Aligner goals — align neutral junctions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from cogames_agents.policy.scripted_agent.planky.goal import Goal
from cogames_agents.policy.scripted_agent.planky.navigator import _manhattan
from mettagrid.simulator import Action

from .gear import GetGearGoal

if TYPE_CHECKING:
    from cogames_agents.policy.scripted_agent.planky.context import PlankyContext

JUNCTION_AOE_RANGE = 10


class GetAlignerGearGoal(GetGearGoal):
    """Get aligner gear."""

    def __init__(self) -> None:
        super().__init__(
            gear_attr="aligner_gear",
            station_type="aligner_station",
            goal_name="GetAlignerGear",
        )


class AlignJunctionGoal(Goal):
    """Find and align a neutral junction to cogs.

    Tracks attempts per junction to avoid getting stuck on one that
    can't be captured (e.g., already aligned but map hasn't updated).
    """

    name = "AlignJunction"
    MAX_ATTEMPTS_PER_TARGET = 5
    COOLDOWN_STEPS = 50

    def is_satisfied(self, ctx: PlankyContext) -> bool:
        # Never satisfied — always try to align more
        return False

    def execute(self, ctx: PlankyContext) -> Optional[Action]:
        target = self._find_best_target(ctx)
        if target is None:
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
            attempts_key = f"align_attempts_{target}"
            attempts = ctx.blackboard.get(attempts_key, 0) + 1
            ctx.blackboard[attempts_key] = attempts

            if attempts > self.MAX_ATTEMPTS_PER_TARGET:
                # Mark this junction as failed temporarily
                failed_key = f"align_failed_{target}"
                ctx.blackboard[failed_key] = ctx.step
                ctx.blackboard[attempts_key] = 0
                if ctx.trace:
                    ctx.trace.activate(self.name, f"giving up on {target}")
                # Clear and try a different junction next tick
                return ctx.navigator.explore(
                    ctx.state.position,
                    ctx.map,
                    direction_bias=["north", "east", "south", "west"][ctx.agent_id % 4],
                )

            if ctx.trace:
                ctx.trace.activate(self.name, f"bump {attempts}/{self.MAX_ATTEMPTS_PER_TARGET}")
            return _move_toward(ctx.state.position, target)

        # Not adjacent - reset attempts for this target
        attempts_key = f"align_attempts_{target}"
        ctx.blackboard[attempts_key] = 0
        return ctx.navigator.get_action(ctx.state.position, target, ctx.map, reach_adjacent=True)

    def _find_best_target(self, ctx: PlankyContext) -> tuple[int, int] | None:
        """Find nearest neutral junction NOT in enemy AOE and not recently failed."""
        pos = ctx.state.position

        # Get enemy junctions for AOE check
        clips_junctions = []
        for jpos, _e in ctx.map.find(type_contains="junction", property_filter={"alignment": "clips"}):
            clips_junctions.append(jpos)
        for cpos, _e in ctx.map.find(type_contains="charger", property_filter={"alignment": "clips"}):
            clips_junctions.append(cpos)

        def in_enemy_aoe(p: tuple[int, int]) -> bool:
            return any(_manhattan(p, ej) <= JUNCTION_AOE_RANGE for ej in clips_junctions)

        def recently_failed(p: tuple[int, int]) -> bool:
            failed_step = ctx.blackboard.get(f"align_failed_{p}", -9999)
            return ctx.step - failed_step < self.COOLDOWN_STEPS

        # Find neutral junctions
        candidates: list[tuple[int, tuple[int, int]]] = []

        for jpos, e in ctx.map.find(type_contains="junction"):
            alignment = e.properties.get("alignment")
            if alignment is not None:
                continue  # Not neutral
            if in_enemy_aoe(jpos):
                continue
            if recently_failed(jpos):
                continue
            candidates.append((_manhattan(pos, jpos), jpos))

        for cpos, e in ctx.map.find(type_contains="charger"):
            alignment = e.properties.get("alignment")
            if alignment is not None:
                continue
            if in_enemy_aoe(cpos):
                continue
            if recently_failed(cpos):
                continue
            candidates.append((_manhattan(pos, cpos), cpos))

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
