"""Food variant: adds food resource, agent inventory, and fed reward."""

from __future__ import annotations

from cogames.core import CoGameMissionVariant
from mettagrid.config.mettagrid_config import MettaGridConfig, RenderHudConfig, ResourceLimitsConfig
from mettagrid.config.reward_config import inventoryReward


class FoodVariant(CoGameMissionVariant):
    """Add food resource, agent inventory limits/initial, and fed reward."""

    name: str = "food"
    description: str = "Food resource, inventory, and fed reward (1/max_steps per step when food ≥ 1)."

    def modify_env(self, mission, env: MettaGridConfig) -> None:
        env.game.resource_names = list(env.game.resource_names) + ["food"]

        for agent in env.game.agents:
            inv = agent.inventory
            inv.limits["food"] = ResourceLimitsConfig(min=100, resources=["food"])
            inv.initial["food"] = 20
            agent.rewards["food"] = inventoryReward(
                "food",
                weight=1.0 / env.game.max_steps,
                max=1.0 / env.game.max_steps,
                per_tick=True,
            )

        env.game.render.hud1 = RenderHudConfig(resource="food", short_name="F", max=100)
