"""Energy variant: movement costs 1 energy per step."""

from __future__ import annotations

from cogames.core import CoGameMissionVariant
from mettagrid.config.mettagrid_config import MettaGridConfig, ResourceLimitsConfig
from mettagrid.config.render_config import RenderHudConfig, RenderStatusBarConfig


class EnergyVariant(CoGameMissionVariant):
    """Add energy resource and make movement cost 1 energy per step."""

    name: str = "energy"
    description: str = "Movement costs 1 energy per step."

    def modify_env(self, mission, env: MettaGridConfig) -> None:
        if "energy" not in env.game.resource_names:
            env.game.resource_names = list(env.game.resource_names) + ["energy"]

        env.game.actions.move.consumed_resources = {"energy": 1}

        for agent in env.game.agents:
            inv = agent.inventory
            inv.limits["energy"] = ResourceLimitsConfig(min=100, resources=["energy"])
            inv.initial["energy"] = 100

        env.game.render.agent_huds["energy"] = RenderHudConfig(resource="energy", max=100, rank=1)
        env.game.render.object_status["agent"]["energy"] = RenderStatusBarConfig(
            resource="energy",
            short_name="E",
            max=100,
            divisions=20,
            rank=1,
        )
