from __future__ import annotations

import pytest
from mettagrid_sdk.games.cogsguard import (
    COGSGUARD_BOOTSTRAP_HUB_OFFSETS,
    COGSGUARD_GEAR_COSTS,
    COGSGUARD_JUNCTION_ALIGN_DISTANCE,
    COGSGUARD_ROLE_NAMES,
    CogsguardPromptAdapter,
    CogsguardStateAdapter,
)
from mettagrid_sdk.runtime.observation import ObservationEnvelope

from mettagrid.simulator.simulator import Simulation


def test_cogsguard_state_adapter_extracts_semantic_state(
    cogsguard_env_info,
    make_observation,
    make_tag_token,
    make_token,
) -> None:
    center_row = cogsguard_env_info.obs_height // 2
    center_col = cogsguard_env_info.obs_width // 2
    adapter = CogsguardStateAdapter()

    obs = make_observation(
        cogsguard_env_info,
        [
            make_tag_token(cogsguard_env_info, "team:cogs", row=center_row, col=center_col),
            make_tag_token(cogsguard_env_info, "type:agent", row=center_row, col=center_col),
            make_token(cogsguard_env_info, "inv:energy", 80, row=center_row, col=center_col),
            make_token(cogsguard_env_info, "inv:heart", 1, row=center_row, col=center_col),
            make_token(cogsguard_env_info, "inv:aligner", 1, row=center_row, col=center_col),
            make_token(cogsguard_env_info, "inv:carbon", 34, row=center_row, col=center_col),
            make_token(cogsguard_env_info, "inv:carbon:p1", 1, row=center_row, col=center_col),
            make_token(cogsguard_env_info, "agent:group", 0, row=center_row, col=center_col),
            make_token(cogsguard_env_info, "agent_id", 0, row=center_row, col=center_col),
            make_tag_token(cogsguard_env_info, "type:hub", row=center_row, col=center_col + 2),
            make_tag_token(cogsguard_env_info, "team:cogs", row=center_row, col=center_col + 2),
            make_tag_token(cogsguard_env_info, "net:cogs", row=center_row, col=center_col + 2),
            make_token(cogsguard_env_info, "inv:oxygen", 24, row=center_row, col=center_col + 2),
            make_tag_token(cogsguard_env_info, "type:junction", row=center_row - 2, col=center_col),
            make_tag_token(cogsguard_env_info, "type:c:aligner", row=center_row + 1, col=center_col),
            make_tag_token(cogsguard_env_info, "type:agent", row=center_row, col=center_col - 2),
            make_tag_token(cogsguard_env_info, "team:clips", row=center_row, col=center_col - 2),
            make_token(cogsguard_env_info, "inv:scrambler", 1, row=center_row, col=center_col - 2),
            make_token(cogsguard_env_info, "inv:heart", 1, row=center_row, col=center_col - 2),
            make_token(cogsguard_env_info, "agent_id", 3, row=center_row, col=center_col - 2),
            make_tag_token(cogsguard_env_info, "type:agent", row=center_row + 1, col=center_col - 1),
            make_tag_token(cogsguard_env_info, "team:cogs", row=center_row + 1, col=center_col - 1),
            make_token(cogsguard_env_info, "inv:miner", 1, row=center_row + 1, col=center_col - 1),
            make_token(cogsguard_env_info, "agent_id", 2, row=center_row + 1, col=center_col - 1),
            make_token(cogsguard_env_info, "team:oxygen", 200, is_global=True),
            make_token(cogsguard_env_info, "team:carbon", 12, is_global=True),
        ],
    )

    state = adapter.build_state(ObservationEnvelope(raw_observation=obs, policy_env_info=cogsguard_env_info, step=9))

    assert state.step == 9
    assert state.self_state.position.x == 0
    assert state.self_state.position.y == 0
    assert state.self_state.role == "aligner"
    assert state.self_state.inventory["carbon"] == 290
    assert "has_heart" in state.self_state.status
    assert state.team_summary is not None
    assert state.team_summary.team_id == "cogs"
    assert state.team_summary.shared_inventory["oxygen"] == 200

    entity_types = {entity.entity_type for entity in state.visible_entities}
    assert "hub" in entity_types
    assert "junction" in entity_types
    assert "aligner_station" in entity_types
    assert "agent" in entity_types

    hub = next(entity for entity in state.visible_entities if entity.entity_type == "hub")
    assert hub.position.x == 2
    assert hub.attributes["owner"] == "cogs"
    assert "friendly" in hub.labels

    junction = next(entity for entity in state.visible_entities if entity.entity_type == "junction")
    assert "neutral" in junction.labels

    enemy = next(
        entity
        for entity in state.visible_entities
        if entity.entity_type == "agent" and entity.attributes.get("team") == "clips"
    )
    assert enemy.attributes["role"] == "scrambler"
    assert "enemy" in enemy.labels

    teammate = next(member for member in state.team_summary.members if member.entity_id == "agent-2")
    assert teammate.role == "miner"


def test_cogsguard_state_adapter_handles_live_observation(cogsguard_env_info) -> None:
    make_cogsguard_mission = pytest.importorskip(
        "cogames.games.cogs_vs_clips.missions.machina_1"
    ).make_cogsguard_mission
    mission = make_cogsguard_mission(num_agents=4, max_steps=10)
    sim = Simulation(mission.make_env())
    adapter = CogsguardStateAdapter()

    state = adapter.build_state(
        ObservationEnvelope(
            raw_observation=sim.agent(0).observation,
            policy_env_info=cogsguard_env_info,
            step=1,
        )
    )

    assert state.game == "cogsguard"
    assert state.self_state.inventory["energy"] == 100
    assert state.team_summary is not None
    assert state.team_summary.team_id == "cogs"


def test_cogsguard_state_adapter_tolerates_visible_agents_without_agent_id(
    cogsguard_env_info,
    make_observation,
    make_tag_token,
    make_token,
) -> None:
    center_row = cogsguard_env_info.obs_height // 2
    center_col = cogsguard_env_info.obs_width // 2
    adapter = CogsguardStateAdapter()

    obs = make_observation(
        cogsguard_env_info,
        [
            make_tag_token(cogsguard_env_info, "team:cogs", row=center_row, col=center_col),
            make_tag_token(cogsguard_env_info, "type:agent", row=center_row, col=center_col),
            make_token(cogsguard_env_info, "inv:energy", 100, row=center_row, col=center_col),
            make_token(cogsguard_env_info, "agent:group", 0, row=center_row, col=center_col),
            make_token(cogsguard_env_info, "agent_id", 7, row=center_row, col=center_col),
            make_tag_token(cogsguard_env_info, "team:clips", row=center_row, col=center_col + 1),
            make_tag_token(cogsguard_env_info, "type:agent", row=center_row, col=center_col + 1),
            make_token(cogsguard_env_info, "inv:energy", 100, row=center_row, col=center_col + 1),
        ],
        agent_id=7,
    )

    state = adapter.build_state(ObservationEnvelope(raw_observation=obs, policy_env_info=cogsguard_env_info, step=4))

    enemy = next(entity for entity in state.visible_entities if entity.entity_type == "agent")
    assert enemy.entity_id == "agent@1,0"
    assert enemy.attributes["role"] == "unknown"
    assert "enemy" in enemy.labels


def test_cogsguard_state_adapter_preserves_extractor_features(
    cogsguard_env_info,
    make_observation,
    make_tag_token,
    make_token,
) -> None:
    center_row = cogsguard_env_info.obs_height // 2
    center_col = cogsguard_env_info.obs_width // 2
    adapter = CogsguardStateAdapter()

    obs = make_observation(
        cogsguard_env_info,
        [
            make_tag_token(cogsguard_env_info, "team:cogs", row=center_row, col=center_col),
            make_tag_token(cogsguard_env_info, "type:agent", row=center_row, col=center_col),
            make_token(cogsguard_env_info, "inv:energy", 100, row=center_row, col=center_col),
            make_token(cogsguard_env_info, "agent:group", 0, row=center_row, col=center_col),
            make_token(cogsguard_env_info, "agent_id", 0, row=center_row, col=center_col),
            make_tag_token(cogsguard_env_info, "type:carbon_extractor", row=center_row, col=center_col + 1),
        ],
    )

    state = adapter.build_state(ObservationEnvelope(raw_observation=obs, policy_env_info=cogsguard_env_info, step=4))

    extractor = next(entity for entity in state.visible_entities if entity.entity_type == "carbon_extractor")
    assert extractor.entity_type == "carbon_extractor"


def test_cogsguard_state_adapter_exposes_freeze_status(
    cogsguard_env_info,
    make_observation,
    make_tag_token,
    make_token,
) -> None:
    center_row = cogsguard_env_info.obs_height // 2
    center_col = cogsguard_env_info.obs_width // 2
    adapter = CogsguardStateAdapter()

    obs = make_observation(
        cogsguard_env_info,
        [
            make_tag_token(cogsguard_env_info, "team:cogs", row=center_row, col=center_col),
            make_tag_token(cogsguard_env_info, "type:agent", row=center_row, col=center_col),
            make_token(cogsguard_env_info, "agent_id", 0, row=center_row, col=center_col),
            make_token(cogsguard_env_info, "agent:frozen", 2, row=center_row, col=center_col),
            make_tag_token(cogsguard_env_info, "team:clips", row=center_row, col=center_col + 1),
            make_tag_token(cogsguard_env_info, "type:agent", row=center_row, col=center_col + 1),
            make_token(cogsguard_env_info, "agent_id", 3, row=center_row, col=center_col + 1),
            make_token(cogsguard_env_info, "agent:frozen", 1, row=center_row, col=center_col + 1),
        ],
    )

    state = adapter.build_state(ObservationEnvelope(raw_observation=obs, policy_env_info=cogsguard_env_info, step=4))

    assert "frozen" in state.self_state.status
    assert state.self_state.attributes["frozen"] is True
    assert state.self_state.attributes["freeze_remaining"] == 2

    enemy = next(entity for entity in state.visible_entities if entity.entity_type == "agent")
    assert enemy.attributes["frozen"] is True
    assert enemy.attributes["freeze_remaining"] == 1


def test_cogsguard_prompt_adapter_renders_semantic_snapshot(
    cogsguard_env_info,
    make_observation,
    make_tag_token,
    make_token,
) -> None:
    center_row = cogsguard_env_info.obs_height // 2
    center_col = cogsguard_env_info.obs_width // 2
    adapter = CogsguardStateAdapter()
    prompt_adapter = CogsguardPromptAdapter()

    obs = make_observation(
        cogsguard_env_info,
        [
            make_tag_token(cogsguard_env_info, "team:cogs", row=center_row, col=center_col),
            make_tag_token(cogsguard_env_info, "type:agent", row=center_row, col=center_col),
            make_token(cogsguard_env_info, "inv:energy", 90, row=center_row, col=center_col),
            make_token(cogsguard_env_info, "inv:aligner", 1, row=center_row, col=center_col),
            make_token(cogsguard_env_info, "agent:group", 0, row=center_row, col=center_col),
            make_token(cogsguard_env_info, "agent_id", 0, row=center_row, col=center_col),
            make_tag_token(cogsguard_env_info, "type:junction", row=center_row - 1, col=center_col),
        ],
    )
    state = adapter.build_state(ObservationEnvelope(raw_observation=obs, policy_env_info=cogsguard_env_info, step=3))

    rendered = prompt_adapter.render_state(state)

    assert "SELF" in rendered
    assert "role: aligner" in rendered
    assert "shared_inventory:" in rendered
    assert "shared_objectives:" in rendered
    assert "junction" in rendered


def test_cogsguard_prompt_adapter_handles_missing_team_summary(
    cogsguard_env_info,
    make_observation,
    make_tag_token,
    make_token,
) -> None:
    center_row = cogsguard_env_info.obs_height // 2
    center_col = cogsguard_env_info.obs_width // 2
    adapter = CogsguardStateAdapter()
    prompt_adapter = CogsguardPromptAdapter()

    obs = make_observation(
        cogsguard_env_info,
        [
            make_tag_token(cogsguard_env_info, "team:cogs", row=center_row, col=center_col),
            make_tag_token(cogsguard_env_info, "type:agent", row=center_row, col=center_col),
            make_token(cogsguard_env_info, "inv:energy", 90, row=center_row, col=center_col),
            make_token(cogsguard_env_info, "agent:group", 0, row=center_row, col=center_col),
            make_token(cogsguard_env_info, "agent_id", 0, row=center_row, col=center_col),
        ],
    )
    state = adapter.build_state(ObservationEnvelope(raw_observation=obs, policy_env_info=cogsguard_env_info, step=3))

    rendered = prompt_adapter.render_state(state.model_copy(update={"team_summary": None}))

    assert "team: unknown" in rendered


def test_cogsguard_public_constants_capture_shared_mechanics() -> None:
    assert COGSGUARD_ROLE_NAMES == ("miner", "aligner", "scrambler", "scout")
    assert COGSGUARD_GEAR_COSTS["aligner"]["carbon"] == 3
    assert COGSGUARD_BOOTSTRAP_HUB_OFFSETS[5] == (-3, 0)
    assert COGSGUARD_JUNCTION_ALIGN_DISTANCE == 15


def test_cogsguard_prompt_adapter_exposes_skill_library() -> None:
    library = CogsguardPromptAdapter().render_skill_library()

    assert library.startswith("SKILLS")
    assert "resource_coverage" in library
    assert "focused_extractor_lock" in library
    assert "region_reanchor" in library
    assert "heart_gated_alignment" in library
    assert "CONTROL_PRIMITIVES" in library
    assert "target_entity_id: strongest focus primitive" in library
    assert "resource_bias: resource-type preference among viable extractors" in library
    assert "BEST_PRACTICES" in library
    assert 'sdk.helpers.nearest_visible_entity(entity_type="junction", label="neutral")' in library
    assert "sdk.helpers.shared_inventory() and sdk.helpers.recent_event_types()" in library
