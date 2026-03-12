from __future__ import annotations

from mettagrid_sdk.runtime.observation import ObservationEnvelope, decode_observation

from mettagrid.config.id_map import ObservationFeatureSpec
from mettagrid.policy.policy_env_interface import PolicyEnvInterface
from mettagrid.simulator import AgentObservation


def test_decoded_observation_self_cell_exists_for_empty_center() -> None:
    policy_env_info = PolicyEnvInterface(
        obs_features=[ObservationFeatureSpec(id=0, name="tag", normalization=1)],
        tags=["type:junction"],
        action_names=[],
        num_agents=1,
        observation_shape=(0, 0),
        egocentric_shape=(5, 5),
    )
    observation = AgentObservation(agent_id=0, tokens=[])

    decoded = decode_observation(
        ObservationEnvelope(
            raw_observation=observation,
            policy_env_info=policy_env_info,
            step=3,
        )
    )

    assert decoded.self_cell.row == 2
    assert decoded.self_cell.col == 2
    assert decoded.self_cell.x == 0
    assert decoded.self_cell.y == 0
    assert decoded.self_cell.tags == ()
    assert decoded.self_cell.features == {}
