"""Scout goals — explore the map."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cogames_agents.policy.scripted_agent.planky.goal import Goal
from mettagrid.simulator import Action

from .gear import GetGearGoal

if TYPE_CHECKING:
    from cogames_agents.policy.scripted_agent.planky.context import PlankyContext


class GetScoutGearGoal(GetGearGoal):
    """Get scout gear."""

    def __init__(self) -> None:
        super().__init__(
            gear_attr="scout_gear",
            station_type="scout_station",
            goal_name="GetScoutGear",
        )


class ExploreGoal(Goal):
    """Explore the map by navigating to frontier cells."""

    name = "Explore"

    def is_satisfied(self, ctx: PlankyContext) -> bool:
        # Never satisfied — always explore
        return False

    def execute(self, ctx: PlankyContext) -> Action:
        directions = ["north", "east", "south", "west"]
        direction_bias = directions[ctx.agent_id % 4]
        return ctx.navigator.explore(ctx.state.position, ctx.map, direction_bias=direction_bias)
