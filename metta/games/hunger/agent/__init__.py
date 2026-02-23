"""Agent configuration and scripted policy for the Hunger game."""

from metta.games.hunger.agent.config import agent_config
from metta.games.hunger.agent.hunger_agent.policy import HungerPolicy  # noqa: F401 — registers via metaclass

__all__ = ["agent_config", "HungerPolicy"]
