"""Stem goal — select a role based on map and collective state."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cogames_agents.policy.scripted_agent.planky.goal import Goal
from mettagrid.simulator import Action

if TYPE_CHECKING:
    from cogames_agents.policy.scripted_agent.planky.context import PlankyContext


class SelectRoleGoal(Goal):
    """Evaluate map + collective inventory to select a role.

    Once a role is selected, the agent's goal list is replaced with
    the selected role's goal list. This is a one-time decision.
    """

    name = "SelectRole"

    def __init__(self, role_goal_lists: dict) -> None:
        """
        Args:
            role_goal_lists: dict mapping role name to list[Goal]
                e.g. {"miner": [...], "scout": [...], "aligner": [...], "scrambler": [...]}
        """
        self._role_goal_lists = role_goal_lists
        self._selected = False

    def is_satisfied(self, ctx: PlankyContext) -> bool:
        return self._selected

    def execute(self, ctx: PlankyContext) -> Action:
        role = self._select_role(ctx)
        ctx.blackboard["selected_role"] = role
        ctx.blackboard["goal_list"] = self._role_goal_lists[role]
        self._selected = True

        if ctx.trace:
            ctx.trace.activate(self.name, f"selected={role}")

        # Change vibe to match selected role
        vibe_action_name = f"change_vibe_{role}"
        if vibe_action_name in ctx.action_names:
            return Action(name=vibe_action_name)
        return Action(name="noop")

    def _select_role(self, ctx: PlankyContext) -> str:
        """Decide role based on map knowledge and collective resources."""
        state = ctx.state

        # Count known structures
        extractors = ctx.map.find(type_contains="extractor")
        neutral_junctions = [
            (p, e) for p, e in ctx.map.find(type_contains="junction") if e.properties.get("alignment") is None
        ] + [(p, e) for p, e in ctx.map.find(type_contains="charger") if e.properties.get("alignment") is None]
        enemy_junctions = [
            (p, e) for p, e in ctx.map.find(type_contains="junction") if e.properties.get("alignment") == "clips"
        ] + [(p, e) for p, e in ctx.map.find(type_contains="charger") if e.properties.get("alignment") == "clips"]

        explored_count = len(ctx.map.explored)

        # Heuristic scoring
        scores: dict[str, float] = {
            "miner": 0.0,
            "scout": 0.0,
            "aligner": 0.0,
            "scrambler": 0.0,
        }

        # If very little explored, prioritize scouting
        if explored_count < 100:
            scores["scout"] += 5.0

        # More extractors → more miners needed
        scores["miner"] += len(extractors) * 1.0

        # More neutral junctions → more aligners needed
        scores["aligner"] += len(neutral_junctions) * 2.0

        # More enemy junctions → more scramblers needed
        scores["scrambler"] += len(enemy_junctions) * 3.0

        # Low collective resources → prioritize mining
        total_collective = (
            state.collective_carbon + state.collective_oxygen + state.collective_germanium + state.collective_silicon
        )
        if total_collective < 20:
            scores["miner"] += 3.0

        # If no extractors known yet, be a scout to find them
        if len(extractors) == 0:
            scores["scout"] += 3.0

        # Default bias toward miner if tied
        scores["miner"] += 0.1

        best_role = max(scores, key=lambda r: scores[r])
        return best_role
