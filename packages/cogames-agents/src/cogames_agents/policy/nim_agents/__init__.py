"""Nim-based agent policies for CoGames."""

from cogames_agents.policy.nim_agents import agents  # noqa: F401

__all__ = [
    "RandomAgentsMultiPolicy",
    "ThinkyAgentsMultiPolicy",
    "RaceCarAgentsMultiPolicy",
    "CogsguardAlignAllAgentsMultiPolicy",
]

# Re-export the policy classes for convenience
from cogames_agents.policy.nim_agents.agents import (  # noqa: F401
    CogsguardAlignAllAgentsMultiPolicy,
    RaceCarAgentsMultiPolicy,
    RandomAgentsMultiPolicy,
    ThinkyAgentsMultiPolicy,
)
