from __future__ import annotations

from mettagrid_sdk.games.cogsguard import CogsguardStateAdapter
from mettagrid_sdk.runtime.observation import ObservationEnvelope


def test_cogsguard_state_adapter_returns_semantic_state(
    cogsguard_env_info,
    make_observation,
    make_tag_token,
    make_token,
) -> None:
    adapter = CogsguardStateAdapter()
    center_row = cogsguard_env_info.obs_height // 2
    center_col = cogsguard_env_info.obs_width // 2
    observation = make_observation(
        cogsguard_env_info,
        [
            make_tag_token(cogsguard_env_info, "team:cogs", row=center_row, col=center_col),
            make_tag_token(cogsguard_env_info, "type:agent", row=center_row, col=center_col),
            make_token(cogsguard_env_info, "agent:group", 0, row=center_row, col=center_col),
            make_token(cogsguard_env_info, "agent_id", 0, row=center_row, col=center_col),
        ],
    )

    state = adapter.build_state(
        ObservationEnvelope(raw_observation=observation, policy_env_info=cogsguard_env_info, step=1)
    )

    assert state.game == "cogsguard"
    assert state.self_state.entity_type == "agent"
