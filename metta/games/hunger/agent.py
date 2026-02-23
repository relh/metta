"""Agent configuration for the Hunger game."""

from __future__ import annotations

from metta.games.hunger.config import HungerConfig
from mettagrid.config.game_value import InventoryValue
from mettagrid.config.handler_config import Handler, actorHas, targetHas, updateActor, updateTarget, withdraw
from mettagrid.config.mettagrid_config import AgentConfig, InventoryConfig, ResourceLimitsConfig
from mettagrid.config.mutation.game_value_mutation import SetGameValueMutation
from mettagrid.config.mutation.mutation import EntityTarget
from mettagrid.config.reward_config import reward


def agent_config(max_steps: int) -> AgentConfig:
    """Create an agent config for the Hunger game.

    Agents start gearless. Once they pick up scrambler or scout gear, their energy
    and solar limits are modified accordingly.
    """
    return AgentConfig(
        inventory=InventoryConfig(
            limits={
                "gear": ResourceLimitsConfig(min=1, max=1, resources=HungerConfig.GEAR),
                "hp": ResourceLimitsConfig(min=100, resources=["hp"]),
                "egg": ResourceLimitsConfig(min=1, resources=["egg"]),
                "kid": ResourceLimitsConfig(min=100, resources=["kid"]),
                "energy": ResourceLimitsConfig(
                    min=100,
                    resources=["energy"],
                    modifiers={"scrambler": 400, "scout": 100},
                ),
                "solar": ResourceLimitsConfig(
                    min=1,
                    resources=["solar"],
                    modifiers={"scout": 2},
                ),
            },
            initial={"hp": 20, "energy": 100, "solar": 1},
        ),
        on_use_handlers={
            "scrambler_hunts_scout": Handler(
                filters=[actorHas({"scrambler": 1}), targetHas({"scout": 1})],
                mutations=[withdraw({"hp": 9999}), updateTarget({"egg": -1})],
            ),
            "scrambler_tags_scrambler": Handler(
                filters=[actorHas({"scrambler": 1}), targetHas({"scrambler": 1})],
                mutations=[updateActor({"egg": -1}), updateTarget({"egg": -1})],
            ),
        },
        on_tick={
            "solar_to_energy": Handler(
                mutations=[
                    SetGameValueMutation(
                        value=InventoryValue(item="energy"),
                        source=InventoryValue(item="solar"),
                        target=EntityTarget.ACTOR,
                    )
                ]
            ),
        },
        rewards={
            "kids": reward(InventoryValue(item="kid"), weight=1.0 / max_steps),
        },
    )
