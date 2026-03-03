"""Canonical CogsGuard recipe."""

from __future__ import annotations

from collections.abc import Sequence

import metta.tools as tools
from recipes.game import cogs_vs_clips

DEFAULT_ENV_NAME = "cogsguard_8agents"


def play(
    policy_uri: str | None = None,
    env_name: str = DEFAULT_ENV_NAME,
    num_agents: int | None = None,
    cogs: int | None = None,
    max_steps: int | None = None,
    variants: Sequence[str] | None = None,
) -> tools.PlayTool:
    return cogs_vs_clips.play(
        policy_uri=policy_uri,
        env_name=env_name,
        num_agents=num_agents,
        cogs=cogs,
        max_steps=max_steps,
        variants=variants,
    )


def train(
    env_name: str = DEFAULT_ENV_NAME,
    num_agents: int | None = None,
    cogs: int | None = None,
    max_steps: int | None = None,
    variants: Sequence[str] | None = None,
) -> tools.TrainTool:
    return cogs_vs_clips.train(
        env_name=env_name,
        num_agents=num_agents,
        cogs=cogs,
        max_steps=max_steps,
        variants=variants,
    )
