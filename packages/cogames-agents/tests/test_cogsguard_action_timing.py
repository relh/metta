from __future__ import annotations

import pytest
from cogames_agents.policy.scripted_agent.cogsguard.policy import CogsguardAgentPolicyImpl
from cogames_agents.policy.scripted_agent.cogsguard.types import CogsguardAgentState, Role
from cogames_agents.policy.scripted_agent.types import CellType

from mettagrid.policy.policy_env_interface import PolicyEnvInterface
from mettagrid.simulator import Action


@pytest.fixture
def policy_env_info() -> PolicyEnvInterface:
    return PolicyEnvInterface(
        obs_features=[],
        tags=[],
        action_names=["noop", "move_north", "move_south", "move_east", "move_west"],
        num_agents=1,
        observation_shape=(1, 1),
        egocentric_shape=(3, 3),
        assembler_protocols=[],
    )


def _make_state(
    *,
    map_size: int = 5,
    row: int = 2,
    col: int = 2,
) -> CogsguardAgentState:
    occupancy = [[CellType.FREE.value] * map_size for _ in range(map_size)]
    explored = [[False] * map_size for _ in range(map_size)]
    return CogsguardAgentState(
        agent_id=0,
        role=Role.MINER,
        map_height=map_size,
        map_width=map_size,
        occupancy=occupancy,
        explored=explored,
        row=row,
        col=col,
    )


def test_position_updates_from_executed_action(policy_env_info: PolicyEnvInterface) -> None:
    policy = CogsguardAgentPolicyImpl(policy_env_info, agent_id=0, role=Role.MINER)
    state = _make_state()

    state.last_action = Action(name="move_north")
    state.last_action_executed = "move_south"

    policy._update_agent_position(state)

    assert (state.row, state.col) == (3, 2)
