import sys
import types

import pytest
from cogames_agents.policy.scripted_agent.cogsguard.debug_agent import DebugHarness

from cogames.games.cogs_vs_clips.missions.arena import make_basic_mission


@pytest.fixture
def debug_recipe_module(monkeypatch: pytest.MonkeyPatch) -> str:
    module_name = "test_debug_recipe_module"
    module = types.ModuleType(module_name)

    def make_env(*, num_agents: int, max_steps: int):
        return make_basic_mission(num_cogs=num_agents, max_steps=max_steps).make_env()

    module.make_env = make_env
    monkeypatch.setitem(sys.modules, module_name, module)
    return module_name


def test_debug_harness_reads_hub_inventory(debug_recipe_module: str) -> None:
    harness = DebugHarness.from_recipe(
        recipe_module=debug_recipe_module,
        num_agents=2,
        max_steps=10,
        seed=1,
        policy_uri="metta://policy/role?miner=1&aligner=1",
    )

    [hub] = harness.get_objects_by_type("hub")

    assert hub["inv:oxygen"] > 0
    assert hub["inv:carbon"] > 0
    assert hub["inv:silicon"] > 0
    assert hub["inv:germanium"] > 0
    assert hub["inv:heart"] > 0
