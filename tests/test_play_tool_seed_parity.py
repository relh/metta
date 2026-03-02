from __future__ import annotations

import random
from typing import Any

import numpy as np
import torch

from metta.sim.simulation_config import SimulationConfig
from metta.tools import play as play_module
from metta.tools.play import PlayTool
from mettagrid import MettaGridConfig
from mettagrid.policy.policy import PolicySpec


def test_play_tool_seeds_global_rng_from_seed(monkeypatch) -> None:
    samples: list[tuple[float, float, float]] = []

    monkeypatch.setattr(
        play_module,
        "policy_spec_from_uri",
        lambda *_args, **_kwargs: PolicySpec(class_path="mettagrid.policy.random_agent.RandomMultiAgentPolicy"),
    )

    def _capture_rng(*_args: Any, **_kwargs: Any):  # type: ignore[no-untyped-def]
        samples.append((random.random(), float(np.random.rand()), float(torch.rand(1).item())))
        return type("Result", (), {"rewards": [0.0], "steps": 1})(), None

    monkeypatch.setattr(play_module, "run_episode_local", _capture_rng)

    tool = PlayTool(
        sim=SimulationConfig(suite="test", name="seeded", env=MettaGridConfig.EmptyRoom(num_agents=1)),
        policy_uri="metta://policy/random",
        render="none",
        autostart=True,
        seed=42,
    )

    tool.invoke({})
    tool.invoke({})

    assert len(samples) == 2
    assert samples[0] == samples[1]
