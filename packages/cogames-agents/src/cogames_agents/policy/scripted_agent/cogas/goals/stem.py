"""Stem goal — select a role based on map and collective state."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cogames_agents.policy.scripted_agent.cogas.goal import Goal
from mettagrid.simulator import Action

if TYPE_CHECKING:
    from cogames_agents.policy.scripted_agent.cogas.context import CogasContext


class SelectRoleGoal(Goal):
    """Evaluate map + collective inventory to select a role.

    Once a role is selected, the agent's goal list is replaced with
    the selected role's goal list. This is a one-time decision.
    """

    name = "SelectRole"

    def __init__(self, role_goal_lists: dict | None = None) -> None:
        """
        Args:
            role_goal_lists: Deprecated, ignored. Roles are now vibe-driven.
        """
        self._selected = False

    def is_satisfied(self, ctx: CogasContext) -> bool:
        return self._selected

    def execute(self, ctx: CogasContext) -> Action:
        role = self._select_role(ctx)
        ctx.blackboard["selected_role"] = role
        ctx.blackboard["change_role"] = role
        self._selected = True

        if ctx.trace:
            ctx.trace.activate(self.name, f"selected={role}")

        # Return change_vibe action to immediately start the new role
        return Action(name=f"change_vibe_{role}")

    def _select_role(self, ctx: CogasContext) -> str:
        """Distribute roles to match planky's defaults: 3 miners + 5 aligners.

        For small teams, prioritize mining since resources are needed for hearts.
        Uses planky's exact distribution pattern, tiled across agent IDs.
        """
        agent_id = ctx.agent_id

        # Planky's default pattern: [miner, miner, miner, aligner, aligner, aligner, aligner, aligner]
        # Index into this pattern based on agent_id
        planky_pattern_size = 8  # 3 miners + 5 aligners
        pattern_index = agent_id % planky_pattern_size

        if pattern_index < 3:
            return "miner"
        return "aligner"
