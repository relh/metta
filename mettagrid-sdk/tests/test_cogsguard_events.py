from __future__ import annotations

from mettagrid_sdk.games.cogsguard import CogsguardEventExtractor, CogsguardStateAdapter
from mettagrid_sdk.runtime.observation import ObservationEnvelope


def test_cogsguard_event_extractor_emits_inventory_and_visibility_events(
    cogsguard_env_info,
    make_observation,
    make_tag_token,
    make_token,
) -> None:
    center_row = cogsguard_env_info.obs_height // 2
    center_col = cogsguard_env_info.obs_width // 2
    adapter = CogsguardStateAdapter()
    extractor = CogsguardEventExtractor()

    previous_obs = make_observation(
        cogsguard_env_info,
        [
            make_tag_token(cogsguard_env_info, "team:cogs", row=center_row, col=center_col),
            make_tag_token(cogsguard_env_info, "type:agent", row=center_row, col=center_col),
            make_token(cogsguard_env_info, "inv:energy", 90, row=center_row, col=center_col),
            make_token(cogsguard_env_info, "inv:aligner", 1, row=center_row, col=center_col),
            make_token(cogsguard_env_info, "agent:group", 0, row=center_row, col=center_col),
            make_token(cogsguard_env_info, "agent_id", 0, row=center_row, col=center_col),
            make_tag_token(cogsguard_env_info, "type:junction", row=center_row - 2, col=center_col),
        ],
    )
    current_obs = make_observation(
        cogsguard_env_info,
        [
            make_tag_token(cogsguard_env_info, "team:cogs", row=center_row, col=center_col),
            make_tag_token(cogsguard_env_info, "type:agent", row=center_row, col=center_col),
            make_token(cogsguard_env_info, "inv:energy", 85, row=center_row, col=center_col),
            make_token(cogsguard_env_info, "inv:heart", 1, row=center_row, col=center_col),
            make_token(cogsguard_env_info, "inv:aligner", 1, row=center_row, col=center_col),
            make_token(cogsguard_env_info, "agent:group", 0, row=center_row, col=center_col),
            make_token(cogsguard_env_info, "agent_id", 0, row=center_row, col=center_col),
            make_tag_token(cogsguard_env_info, "type:junction", row=center_row - 2, col=center_col),
            make_tag_token(cogsguard_env_info, "team:cogs", row=center_row - 2, col=center_col),
            make_tag_token(cogsguard_env_info, "type:agent", row=center_row, col=center_col - 2),
            make_tag_token(cogsguard_env_info, "team:clips", row=center_row, col=center_col - 2),
            make_token(cogsguard_env_info, "inv:scrambler", 1, row=center_row, col=center_col - 2),
            make_token(cogsguard_env_info, "agent_id", 9, row=center_row, col=center_col - 2),
        ],
    )

    previous_state = adapter.build_state(
        ObservationEnvelope(raw_observation=previous_obs, policy_env_info=cogsguard_env_info, step=7)
    )
    current_state = adapter.build_state(
        ObservationEnvelope(raw_observation=current_obs, policy_env_info=cogsguard_env_info, step=8)
    )

    events = extractor.extract_events(previous_state, current_state)
    event_types = {event.event_type for event in events}

    assert "heart_acquired" in event_types
    assert "extractor_seen" not in event_types
    assert "gear_lost" not in event_types
    assert "enemy_seen" in event_types
    assert "junction_owner_changed" in event_types


def test_cogsguard_event_extractor_handles_missing_team_summary(
    cogsguard_env_info,
    make_observation,
    make_tag_token,
    make_token,
) -> None:
    center_row = cogsguard_env_info.obs_height // 2
    center_col = cogsguard_env_info.obs_width // 2
    adapter = CogsguardStateAdapter()
    extractor = CogsguardEventExtractor()

    previous_obs = make_observation(
        cogsguard_env_info,
        [
            make_tag_token(cogsguard_env_info, "team:cogs", row=center_row, col=center_col),
            make_tag_token(cogsguard_env_info, "type:agent", row=center_row, col=center_col),
            make_token(cogsguard_env_info, "agent:group", 0, row=center_row, col=center_col),
            make_token(cogsguard_env_info, "agent_id", 0, row=center_row, col=center_col),
        ],
    )
    current_obs = make_observation(
        cogsguard_env_info,
        [
            make_tag_token(cogsguard_env_info, "team:cogs", row=center_row, col=center_col),
            make_tag_token(cogsguard_env_info, "type:agent", row=center_row, col=center_col),
            make_token(cogsguard_env_info, "agent:group", 0, row=center_row, col=center_col),
            make_token(cogsguard_env_info, "agent_id", 0, row=center_row, col=center_col),
            make_tag_token(cogsguard_env_info, "type:agent", row=center_row, col=center_col - 2),
            make_tag_token(cogsguard_env_info, "team:clips", row=center_row, col=center_col - 2),
            make_token(cogsguard_env_info, "agent_id", 9, row=center_row, col=center_col - 2),
        ],
    )

    previous_state = adapter.build_state(
        ObservationEnvelope(raw_observation=previous_obs, policy_env_info=cogsguard_env_info, step=7)
    ).model_copy(update={"team_summary": None})
    current_state = adapter.build_state(
        ObservationEnvelope(raw_observation=current_obs, policy_env_info=cogsguard_env_info, step=8)
    ).model_copy(update={"team_summary": None})

    assert extractor.extract_events(previous_state, current_state) == []


def test_cogsguard_event_extractor_tracks_junction_across_self_movement(
    cogsguard_env_info,
    make_observation,
    make_tag_token,
    make_token,
) -> None:
    center_row = cogsguard_env_info.obs_height // 2
    center_col = cogsguard_env_info.obs_width // 2
    adapter = CogsguardStateAdapter()
    extractor = CogsguardEventExtractor()

    previous_obs = make_observation(
        cogsguard_env_info,
        [
            make_tag_token(cogsguard_env_info, "team:cogs", row=center_row, col=center_col),
            make_tag_token(cogsguard_env_info, "type:agent", row=center_row, col=center_col),
            make_token(cogsguard_env_info, "agent_id", 0, row=center_row, col=center_col),
            make_token(cogsguard_env_info, "lp:east", 10, is_global=True),
            make_tag_token(cogsguard_env_info, "type:junction", row=center_row, col=center_col + 2),
            make_tag_token(cogsguard_env_info, "team:clips", row=center_row, col=center_col + 2),
        ],
    )
    current_obs = make_observation(
        cogsguard_env_info,
        [
            make_tag_token(cogsguard_env_info, "team:cogs", row=center_row, col=center_col),
            make_tag_token(cogsguard_env_info, "type:agent", row=center_row, col=center_col),
            make_token(cogsguard_env_info, "agent_id", 0, row=center_row, col=center_col),
            make_token(cogsguard_env_info, "lp:east", 11, is_global=True),
            make_tag_token(cogsguard_env_info, "type:junction", row=center_row, col=center_col + 1),
            make_tag_token(cogsguard_env_info, "team:cogs", row=center_row, col=center_col + 1),
        ],
    )

    previous_state = adapter.build_state(
        ObservationEnvelope(raw_observation=previous_obs, policy_env_info=cogsguard_env_info, step=10)
    )
    current_state = adapter.build_state(
        ObservationEnvelope(raw_observation=current_obs, policy_env_info=cogsguard_env_info, step=11)
    )

    events = extractor.extract_events(previous_state, current_state)

    assert any(event.event_type == "junction_owner_changed" for event in events)


def test_cogsguard_event_extractor_tolerates_visible_enemy_without_team_attribute(
    cogsguard_env_info,
    make_observation,
    make_tag_token,
    make_token,
) -> None:
    center_row = cogsguard_env_info.obs_height // 2
    center_col = cogsguard_env_info.obs_width // 2
    adapter = CogsguardStateAdapter()
    extractor = CogsguardEventExtractor()

    previous_obs = make_observation(
        cogsguard_env_info,
        [
            make_tag_token(cogsguard_env_info, "team:cogs", row=center_row, col=center_col),
            make_tag_token(cogsguard_env_info, "type:agent", row=center_row, col=center_col),
            make_token(cogsguard_env_info, "agent_id", 0, row=center_row, col=center_col),
        ],
    )
    current_obs = make_observation(
        cogsguard_env_info,
        [
            make_tag_token(cogsguard_env_info, "team:cogs", row=center_row, col=center_col),
            make_tag_token(cogsguard_env_info, "type:agent", row=center_row, col=center_col),
            make_token(cogsguard_env_info, "agent_id", 0, row=center_row, col=center_col),
            make_tag_token(cogsguard_env_info, "type:agent", row=center_row, col=center_col - 2),
            make_token(cogsguard_env_info, "agent_id", 9, row=center_row, col=center_col - 2),
        ],
    )

    previous_state = adapter.build_state(
        ObservationEnvelope(raw_observation=previous_obs, policy_env_info=cogsguard_env_info, step=7)
    )
    current_state = adapter.build_state(
        ObservationEnvelope(raw_observation=current_obs, policy_env_info=cogsguard_env_info, step=8)
    )

    events = extractor.extract_events(previous_state, current_state)

    assert any(event.event_type == "enemy_seen" for event in events)


def test_cogsguard_event_extractor_emits_loss_and_discovery_events(
    cogsguard_env_info,
    make_observation,
    make_tag_token,
    make_token,
) -> None:
    center_row = cogsguard_env_info.obs_height // 2
    center_col = cogsguard_env_info.obs_width // 2
    adapter = CogsguardStateAdapter()
    extractor = CogsguardEventExtractor()

    previous_obs = make_observation(
        cogsguard_env_info,
        [
            make_tag_token(cogsguard_env_info, "team:cogs", row=center_row, col=center_col),
            make_tag_token(cogsguard_env_info, "type:agent", row=center_row, col=center_col),
            make_token(cogsguard_env_info, "inv:heart", 1, row=center_row, col=center_col),
            make_token(cogsguard_env_info, "inv:aligner", 1, row=center_row, col=center_col),
            make_token(cogsguard_env_info, "agent_id", 0, row=center_row, col=center_col),
        ],
    )
    current_obs = make_observation(
        cogsguard_env_info,
        [
            make_tag_token(cogsguard_env_info, "team:cogs", row=center_row, col=center_col),
            make_tag_token(cogsguard_env_info, "type:agent", row=center_row, col=center_col),
            make_token(cogsguard_env_info, "inv:heart", 0, row=center_row, col=center_col),
            make_token(cogsguard_env_info, "inv:aligner", 0, row=center_row, col=center_col),
            make_token(cogsguard_env_info, "agent_id", 0, row=center_row, col=center_col),
            make_tag_token(cogsguard_env_info, "type:carbon_extractor", row=center_row - 1, col=center_col),
            make_tag_token(cogsguard_env_info, "type:junction", row=center_row, col=center_col + 1),
        ],
    )

    previous_state = adapter.build_state(
        ObservationEnvelope(raw_observation=previous_obs, policy_env_info=cogsguard_env_info, step=12)
    )
    current_state = adapter.build_state(
        ObservationEnvelope(raw_observation=current_obs, policy_env_info=cogsguard_env_info, step=13)
    )

    event_types = {event.event_type for event in extractor.extract_events(previous_state, current_state)}

    assert "heart_lost" in event_types
    assert "gear_lost" in event_types
    assert "extractor_seen" in event_types
    assert "neutral_junction_seen" in event_types
