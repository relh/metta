from __future__ import annotations

import pytest

from mettagrid.policy.policy_env_interface import PolicyEnvInterface


@pytest.fixture
def cogsguard_env_info() -> PolicyEnvInterface:
    make_cogsguard_mission = pytest.importorskip(
        "cogames.games.cogs_vs_clips.missions.machina_1"
    ).make_cogsguard_mission
    mission = make_cogsguard_mission(num_agents=4, max_steps=50)
    return PolicyEnvInterface.from_mg_cfg(mission.make_env())
