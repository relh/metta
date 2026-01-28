"""Shared goals used by multiple roles."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cogames_agents.policy.scripted_agent.planky.goal import Goal
from cogames_agents.policy.scripted_agent.planky.navigator import _manhattan
from mettagrid.simulator import Action

if TYPE_CHECKING:
    from cogames_agents.policy.scripted_agent.planky.context import PlankyContext


class GetHeartsGoal(Goal):
    """Navigate to a chest to acquire hearts."""

    name = "GetHearts"

    def __init__(self, min_hearts: int = 1) -> None:
        self._min_hearts = min_hearts

    def is_satisfied(self, ctx: PlankyContext) -> bool:
        return ctx.state.heart >= self._min_hearts

    def execute(self, ctx: PlankyContext) -> Action:
        # Find chest
        result = ctx.map.find_nearest(ctx.state.position, type="chest")
        if result is None:
            # Try assembler as fallback
            result = ctx.map.find_nearest(ctx.state.position, type="assembler")
        if result is None:
            return ctx.navigator.explore(ctx.state.position, ctx.map)

        chest_pos, _ = result
        if ctx.trace:
            ctx.trace.nav_target = chest_pos

        dist = _manhattan(ctx.state.position, chest_pos)
        if dist <= 1:
            return _move_toward(ctx.state.position, chest_pos)
        return ctx.navigator.get_action(ctx.state.position, chest_pos, ctx.map, reach_adjacent=True)


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
