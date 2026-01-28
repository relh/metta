"""GetGearGoal — navigate to a station to acquire gear."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from cogames_agents.policy.scripted_agent.planky.goal import Goal
from cogames_agents.policy.scripted_agent.planky.navigator import _manhattan
from mettagrid.simulator import Action

if TYPE_CHECKING:
    from cogames_agents.policy.scripted_agent.planky.context import PlankyContext


class GetGearGoal(Goal):
    """Navigate to a station to acquire gear for a role.

    If the team lacks resources to produce gear, the station won't give any.
    This goal will give up after MAX_ADJACENT_ATTEMPTS bumps and let the agent
    continue with other goals (mining). It will retry after RETRY_INTERVAL steps.
    """

    # How many times to bump the station before giving up
    MAX_ADJACENT_ATTEMPTS = 5
    # How many steps to wait before trying again
    RETRY_INTERVAL = 100

    def __init__(self, gear_attr: str, station_type: str, goal_name: str) -> None:
        self.name = goal_name
        self._gear_attr = gear_attr  # e.g. "miner_gear"
        self._station_type = station_type  # e.g. "miner_station"
        self._bb_attempts_key = f"{goal_name}_adjacent_attempts"
        self._bb_giveup_step_key = f"{goal_name}_giveup_step"

    def is_satisfied(self, ctx: PlankyContext) -> bool:
        # Satisfied if we have the gear
        if getattr(ctx.state, self._gear_attr, False):
            return True
        # Also "satisfied" (skip) if we gave up recently
        giveup_step = ctx.blackboard.get(self._bb_giveup_step_key, -9999)
        if ctx.step - giveup_step < self.RETRY_INTERVAL:
            return True
        return False

    def execute(self, ctx: PlankyContext) -> Optional[Action]:
        # Find station by type (stations are near team spawn, so we find our own first)
        result = ctx.map.find_nearest(ctx.state.position, type=self._station_type)
        if result is None:
            # Station not discovered yet — explore
            if ctx.trace:
                ctx.trace.activate(self.name, f"exploring for {self._station_type}")
            return ctx.navigator.explore(
                ctx.state.position,
                ctx.map,
                direction_bias=_agent_direction_bias(ctx.agent_id),
            )

        station_pos, _ = result
        if ctx.trace:
            ctx.trace.nav_target = station_pos

        # Navigate to station (reach adjacent, then bump into it)
        dist = _manhattan(ctx.state.position, station_pos)
        if dist <= 1:
            # Adjacent or on it — track attempts and bump
            attempts = ctx.blackboard.get(self._bb_attempts_key, 0) + 1
            ctx.blackboard[self._bb_attempts_key] = attempts

            if attempts > self.MAX_ADJACENT_ATTEMPTS:
                # Give up - team probably lacks resources
                ctx.blackboard[self._bb_giveup_step_key] = ctx.step
                ctx.blackboard[self._bb_attempts_key] = 0
                if ctx.trace:
                    ctx.trace.activate(self.name, "giving up, will retry later")
                return None  # Skip to next goal

            if ctx.trace:
                ctx.trace.activate(self.name, f"bump {attempts}/{self.MAX_ADJACENT_ATTEMPTS}")
            return _move_toward(ctx.state.position, station_pos)

        # Not adjacent yet - reset attempts counter and navigate
        ctx.blackboard[self._bb_attempts_key] = 0
        return ctx.navigator.get_action(ctx.state.position, station_pos, ctx.map, reach_adjacent=True)


def _agent_direction_bias(agent_id: int) -> str:
    # Gear stations are typically south of spawn in the hub area
    # All agents should explore south first to find gear faster
    return "south"


def _move_toward(current: tuple[int, int], target: tuple[int, int]) -> Action:
    """Move one step toward target."""
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
    # On target — bump into it
    return Action(name="move_north")
