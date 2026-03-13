from __future__ import annotations

from cog_cyborg.policy import MettagridSemanticPolicy
from cog_cyborg.policy.semantic_cog import _GEAR_COSTS, _HUB_OFFSETS, SharedWorldModel, _phase_name
from mettagrid_sdk.games.cogsguard import COGSGUARD_BOOTSTRAP_HUB_OFFSETS, COGSGUARD_GEAR_COSTS
from mettagrid_sdk.games.cogsguard.prompt_adapter import CogsguardPromptAdapter
from mettagrid_sdk.sdk import GridPosition, MacroDirective, MettagridState, SelfState, SemanticEntity, TeamSummary

from cogames.games.cogs_vs_clips.missions.machina_1 import make_cogsguard_mission
from mettagrid.simulator.simulator import Simulation


class _DirectivePolicy(MettagridSemanticPolicy):
    def agent_policy(self, agent_id: int):
        policy = super().agent_policy(agent_id)
        policy._macro_directive = lambda state: MacroDirective(  # type: ignore[method-assign]
            role="miner",
            resource_bias="oxygen",
            objective="resource_coverage",
            note="test-opening",
        )
        return policy


class _TargetDirectivePolicy(MettagridSemanticPolicy):
    def agent_policy(self, agent_id: int):
        policy = super().agent_policy(agent_id)
        policy._macro_directive = lambda state: MacroDirective(  # type: ignore[method-assign]
            role="aligner",
            target_entity_id="junction@6,0",
            target_region="west_lane",
            note="push the west lane target",
        )
        return policy


def test_semantic_policy_produces_valid_action_on_live_observation(cogsguard_env_info) -> None:
    mission = make_cogsguard_mission(num_agents=8, max_steps=20)
    sim = Simulation(mission.make_env())
    policy = MettagridSemanticPolicy(cogsguard_env_info)

    action = policy.agent_policy(0).step(sim.agent(0).observation)

    assert action.name in cogsguard_env_info.action_names


def test_semantic_policy_registers_short_name(cogsguard_env_info) -> None:
    policy = MettagridSemanticPolicy(cogsguard_env_info)

    agent_policy = policy.agent_policy(1)

    assert isinstance(agent_policy, object)
    assert "preferred_role" not in agent_policy.infos


def test_semantic_policy_applies_typed_macro_directive(cogsguard_env_info) -> None:
    policy = _DirectivePolicy(cogsguard_env_info)
    mission = make_cogsguard_mission(num_agents=8, max_steps=20)
    sim = Simulation(mission.make_env())

    agent_policy = policy.agent_policy(0)
    action = agent_policy.step(sim.agent(0).observation)

    assert action.name in cogsguard_env_info.action_names
    assert agent_policy.infos["directive_role"] == "miner"
    assert agent_policy.infos["directive_resource_bias"] == "oxygen"
    assert agent_policy.infos["directive_objective"] == "resource_coverage"
    assert agent_policy.infos["directive_note"] == "test-opening"


def test_semantic_policy_surfaces_tactical_skill_library(cogsguard_env_info) -> None:
    library = MettagridSemanticPolicy(cogsguard_env_info).agent_policy(0).render_skill_library()

    assert library == CogsguardPromptAdapter().render_skill_library()
    assert "resource_coverage" in library
    assert "focused_extractor_lock" in library
    assert "lane_pressure" in library


def test_semantic_policy_unsticks_two_cell_extractor_oscillation(cogsguard_env_info) -> None:
    policy = MettagridSemanticPolicy(cogsguard_env_info).agent_policy(0)
    for position in ((0, 0), (1, 0), (0, 0), (1, 0)):
        policy._current_target_kind = "germanium_extractor"
        policy._current_target_position = (2, 0)
        policy._record_navigation_observation(position, "mine_germanium")

    state = MettagridState(
        game="cogsguard",
        step=20,
        self_state=SelfState(
            entity_id="agent-0",
            entity_type="agent",
            position=GridPosition(x=1, y=0),
            attributes={"global_x": 1, "global_y": 0, "team": "cogs"},
            inventory={"hp": 100},
        ),
        visible_entities=[],
        team_summary=TeamSummary(team_id="cogs"),
    )

    action, summary = policy._choose_action(state, "miner")

    assert policy._oscillation_steps == 4
    assert summary == "unstick_miner"
    assert action.name in cogsguard_env_info.action_names


def test_semantic_policy_resets_resource_bias_after_directive_step(cogsguard_env_info) -> None:
    mission = make_cogsguard_mission(num_agents=8, max_steps=20)
    sim = Simulation(mission.make_env())
    agent_policy = MettagridSemanticPolicy(cogsguard_env_info).agent_policy(0)
    directives = iter((MacroDirective(resource_bias="oxygen"), MacroDirective()))
    agent_policy._macro_directive = lambda state: next(directives)  # type: ignore[method-assign]

    first_action = agent_policy.step(sim.agent(0).observation)
    second_action = agent_policy.step(sim.agent(0).observation)

    assert first_action.name in cogsguard_env_info.action_names
    assert second_action.name in cogsguard_env_info.action_names
    assert agent_policy.infos["directive_resource_bias"] == ""
    assert agent_policy._resource_bias == "carbon"


def test_semantic_policy_uses_independent_world_models(cogsguard_env_info) -> None:
    policy = MettagridSemanticPolicy(cogsguard_env_info)

    agent_zero = policy.agent_policy(0)
    agent_one = policy.agent_policy(1)

    assert agent_zero is not agent_one
    assert agent_zero._world_model is not agent_one._world_model


def test_semantic_policy_reuses_sdk_cogsguard_constants() -> None:
    assert _GEAR_COSTS is COGSGUARD_GEAR_COSTS
    assert _HUB_OFFSETS is COGSGUARD_BOOTSTRAP_HUB_OFFSETS


def test_shared_world_model_prunes_missing_extractors_in_visible_window() -> None:
    world_model = SharedWorldModel()
    initial_state = MettagridState(
        game="cogsguard",
        step=1,
        self_state=SelfState(entity_id="agent-0", entity_type="agent", position=GridPosition(x=0, y=0)),
        visible_entities=[
            SemanticEntity(
                entity_id="germanium_extractor@5,0",
                entity_type="germanium_extractor",
                position=GridPosition(x=5, y=0),
                attributes={"global_x": 5, "global_y": 0},
            )
        ],
    )
    world_model.update(initial_state)

    world_model.prune_missing_extractors(
        current_position=(0, 0),
        visible_entities=[],
        obs_width=13,
        obs_height=13,
    )

    assert world_model.nearest(position=(0, 0), entity_type="germanium_extractor") is None


def test_agent_policy_reset_clears_world_model(cogsguard_env_info) -> None:
    policy = MettagridSemanticPolicy(cogsguard_env_info).agent_policy(0)
    state = MettagridState(
        game="cogsguard",
        step=1,
        self_state=SelfState(
            entity_id="agent-0",
            entity_type="agent",
            position=GridPosition(x=0, y=0),
            attributes={"global_x": 0, "global_y": 0},
        ),
        visible_entities=[
            SemanticEntity(
                entity_id="hub@0,3",
                entity_type="hub",
                position=GridPosition(x=0, y=3),
                attributes={"global_x": 0, "global_y": 3, "team": "cogs", "owner": "cogs"},
            )
        ],
    )
    policy._world_model.update(state)

    policy.reset()

    assert policy._world_model.nearest(position=(0, 0), entity_type="hub") is None


def test_aligner_batches_hearts_when_adjacent_to_hub(cogsguard_env_info) -> None:
    world_model = SharedWorldModel()
    policy = MettagridSemanticPolicy(cogsguard_env_info).agent_policy(0)
    policy._world_model = world_model

    state = MettagridState(
        game="cogsguard",
        step=250,
        self_state=SelfState(
            entity_id="agent-0",
            entity_type="agent",
            position=GridPosition(x=0, y=4),
            attributes={"global_x": 0, "global_y": 4, "team": "cogs"},
            inventory={"aligner": 1, "heart": 1, "hp": 100},
        ),
        visible_entities=[
            SemanticEntity(
                entity_id="hub@0,3",
                entity_type="hub",
                position=GridPosition(x=0, y=3),
                attributes={"global_x": 0, "global_y": 3, "team": "cogs", "owner": "cogs"},
            )
        ],
        team_summary=TeamSummary(
            team_id="cogs",
            shared_inventory={"heart": 1, "carbon": 40, "oxygen": 40, "germanium": 40, "silicon": 40},
        ),
    )
    world_model.update(state)

    action, summary = policy._aligner_action(state)

    assert summary == "batch_hearts"
    assert action.name.startswith("move_")
    assert policy._current_target_kind == "hub"


def test_aligner_target_claims_reduce_same_junction_collisions(cogsguard_env_info) -> None:
    policy = MettagridSemanticPolicy(cogsguard_env_info)
    agent_zero = policy.agent_policy(0)
    agent_one = policy.agent_policy(1)

    state = MettagridState(
        game="cogsguard",
        step=250,
        self_state=SelfState(
            entity_id="agent-1",
            entity_type="agent",
            position=GridPosition(x=0, y=1),
            attributes={"global_x": 0, "global_y": 1, "team": "cogs"},
            inventory={"aligner": 1, "heart": 5, "hp": 100},
        ),
        visible_entities=[
            SemanticEntity(
                entity_id="hub@0,0",
                entity_type="hub",
                position=GridPosition(x=0, y=0),
                attributes={"global_x": 0, "global_y": 0, "team": "cogs", "owner": "cogs"},
            ),
            SemanticEntity(
                entity_id="junction@5,0",
                entity_type="junction",
                position=GridPosition(x=5, y=0),
                attributes={"global_x": 5, "global_y": 0},
            ),
            SemanticEntity(
                entity_id="junction@6,0",
                entity_type="junction",
                position=GridPosition(x=6, y=0),
                attributes={"global_x": 6, "global_y": 0},
            ),
        ],
        team_summary=TeamSummary(team_id="cogs"),
    )
    agent_zero._world_model.update(state)
    agent_one._world_model.update(state)
    agent_zero._step_index = 100
    agent_one._step_index = 100
    agent_zero._claim_target((5, 0))

    target = agent_one._nearest_alignable_neutral_junction(state)

    assert target is not None
    assert target.position == (6, 0)


def test_semantic_policy_uses_directive_target_entity_for_aligner_choice(cogsguard_env_info) -> None:
    policy = _TargetDirectivePolicy(cogsguard_env_info).agent_policy(0)
    state = MettagridState(
        game="cogsguard",
        step=250,
        self_state=SelfState(
            entity_id="agent-0",
            entity_type="agent",
            position=GridPosition(x=0, y=1),
            attributes={"global_x": 0, "global_y": 1, "team": "cogs"},
            inventory={"aligner": 1, "heart": 5, "hp": 100},
        ),
        visible_entities=[
            SemanticEntity(
                entity_id="hub@0,0",
                entity_type="hub",
                position=GridPosition(x=0, y=0),
                attributes={"global_x": 0, "global_y": 0, "team": "cogs", "owner": "cogs"},
            ),
            SemanticEntity(
                entity_id="junction@5,0",
                entity_type="junction",
                position=GridPosition(x=5, y=0),
                labels=["east_lane"],
                attributes={"global_x": 5, "global_y": 0},
            ),
            SemanticEntity(
                entity_id="junction@6,0",
                entity_type="junction",
                position=GridPosition(x=6, y=0),
                labels=["west_lane"],
                attributes={"global_x": 6, "global_y": 0},
            ),
        ],
        team_summary=TeamSummary(team_id="cogs"),
    )
    policy._world_model.update(state)
    policy._current_directive = MacroDirective(target_entity_id="junction@6,0", target_region="west_lane")

    target = policy._nearest_alignable_neutral_junction(state)

    assert target is not None
    assert target.position == (6, 0)


def test_semantic_policy_uses_directive_target_entity_for_miner_choice(cogsguard_env_info) -> None:
    agent = MettagridSemanticPolicy(cogsguard_env_info).agent_policy(0)
    state = MettagridState(
        game="cogsguard",
        step=250,
        self_state=SelfState(
            entity_id="agent-0",
            entity_type="agent",
            position=GridPosition(x=0, y=0),
            attributes={"global_x": 0, "global_y": 0, "team": "cogs"},
            inventory={"miner": 1, "hp": 100},
        ),
        visible_entities=[
            SemanticEntity(
                entity_id="carbon_extractor@0,-2",
                entity_type="carbon_extractor",
                position=GridPosition(x=0, y=-2),
                attributes={"global_x": 0, "global_y": -2, "remaining_uses": 7},
            ),
            SemanticEntity(
                entity_id="carbon_extractor@5,0",
                entity_type="carbon_extractor",
                position=GridPosition(x=5, y=0),
                attributes={"global_x": 5, "global_y": 0, "remaining_uses": 7},
                labels=["east_lane"],
            ),
        ],
        team_summary=TeamSummary(
            team_id="cogs",
            shared_inventory={"carbon": 0, "oxygen": 20, "germanium": 20, "silicon": 20},
        ),
    )
    agent._world_model.update(state)
    agent._resource_bias = "carbon"
    agent._current_directive = MacroDirective(role="miner", target_entity_id="carbon_extractor@5,0")

    action, summary = agent._miner_action(state)

    assert summary == "mine_carbon"
    assert action.name == "move_east"
    assert agent._current_target_position == (5, 0)


def test_pressure_budget_keeps_old_opening_until_economy_unlocks_fifth_pressure_role(cogsguard_env_info) -> None:
    policy = MettagridSemanticPolicy(cogsguard_env_info)
    opening_state = MettagridState(
        game="cogsguard",
        step=25,
        self_state=SelfState(entity_id="agent-0", entity_type="agent", position=GridPosition(x=0, y=0)),
        team_summary=TeamSummary(
            team_id="cogs",
            shared_inventory={"carbon": 0, "oxygen": 0, "germanium": 0, "silicon": 0},
        ),
    )
    locked_mid_state = opening_state.model_copy(
        update={
            "step": 50,
            "self_state": SelfState(entity_id="agent-3", entity_type="agent", position=GridPosition(x=0, y=0)),
        }
    )
    promoted_mid_state = locked_mid_state.model_copy(
        update={
            "team_summary": TeamSummary(
                team_id="cogs",
                shared_inventory={"carbon": 20, "oxygen": 20, "germanium": 20, "silicon": 20},
            )
        }
    )

    assert policy.agent_policy(0)._desired_role(opening_state) == "miner"
    assert (
        policy.agent_policy(4)._desired_role(
            opening_state.model_copy(
                update={
                    "self_state": SelfState(entity_id="agent-4", entity_type="agent", position=GridPosition(x=0, y=0))
                }
            )
        )
        == "aligner"
    )
    assert (
        policy.agent_policy(7)._desired_role(
            opening_state.model_copy(
                update={
                    "self_state": SelfState(entity_id="agent-7", entity_type="agent", position=GridPosition(x=0, y=0))
                }
            )
        )
        == "aligner"
    )
    assert (
        policy.agent_policy(3)._desired_role(
            opening_state.model_copy(
                update={
                    "self_state": SelfState(entity_id="agent-3", entity_type="agent", position=GridPosition(x=0, y=0))
                }
            )
        )
        == "miner"
    )
    assert policy.agent_policy(3)._desired_role(locked_mid_state) == "miner"
    assert policy.agent_policy(3)._desired_role(promoted_mid_state) == "aligner"


def test_pressure_budget_enables_scramblers_then_demotes_extra_pressure_roles(cogsguard_env_info) -> None:
    policy = MettagridSemanticPolicy(cogsguard_env_info)
    agent_three = policy.agent_policy(3)
    agent_seven = policy.agent_policy(7)
    mid_pressure_state = MettagridState(
        game="cogsguard",
        step=2_000,
        self_state=SelfState(entity_id="agent-3", entity_type="agent", position=GridPosition(x=0, y=0)),
        visible_entities=[
            SemanticEntity(
                entity_id="hub@0,0",
                entity_type="hub",
                position=GridPosition(x=0, y=0),
                attributes={"global_x": 0, "global_y": 0, "team": "cogs", "owner": "cogs"},
            ),
            SemanticEntity(
                entity_id="junction@10,0",
                entity_type="junction",
                position=GridPosition(x=10, y=0),
                attributes={"global_x": 10, "global_y": 0},
            ),
            SemanticEntity(
                entity_id="junction@10,10",
                entity_type="junction",
                position=GridPosition(x=10, y=10),
                attributes={"global_x": 10, "global_y": 10},
            ),
            SemanticEntity(
                entity_id="junction@20,10",
                entity_type="junction",
                position=GridPosition(x=20, y=10),
                attributes={"global_x": 20, "global_y": 10},
            ),
            SemanticEntity(
                entity_id="junction@12,10",
                entity_type="junction",
                position=GridPosition(x=12, y=10),
                attributes={"global_x": 12, "global_y": 10, "owner": "clips"},
            ),
        ],
        team_summary=TeamSummary(
            team_id="cogs",
            shared_inventory={"heart": 0, "carbon": 28, "oxygen": 28, "germanium": 28, "silicon": 28},
        ),
    )
    late_starved_state = mid_pressure_state.model_copy(
        update={
            "step": 4_500,
            "team_summary": TeamSummary(
                team_id="cogs",
                shared_inventory={"heart": 0, "carbon": 6, "oxygen": 6, "germanium": 6, "silicon": 6},
            ),
        }
    )
    agent_three._world_model.update(mid_pressure_state)
    agent_seven._world_model.update(mid_pressure_state)
    agent_three._world_model.update(late_starved_state)
    agent_seven._world_model.update(late_starved_state)

    assert agent_three._desired_role(mid_pressure_state) == "aligner"
    assert (
        agent_seven._desired_role(
            mid_pressure_state.model_copy(
                update={
                    "self_state": SelfState(entity_id="agent-7", entity_type="agent", position=GridPosition(x=0, y=0))
                }
            )
        )
        == "scrambler"
    )
    assert agent_three._desired_role(late_starved_state) == "miner"


def test_aligners_fan_out_to_different_explore_spokes(cogsguard_env_info) -> None:
    policy = MettagridSemanticPolicy(cogsguard_env_info)
    agent_four = policy.agent_policy(4)
    agent_five = policy.agent_policy(5)
    state = MettagridState(
        game="cogsguard",
        step=25,
        self_state=SelfState(
            entity_id="agent-4",
            entity_type="agent",
            position=GridPosition(x=0, y=0),
            attributes={"global_x": 0, "global_y": 0, "team": "cogs"},
            inventory={"aligner": 1, "hp": 100},
        ),
        visible_entities=[
            SemanticEntity(
                entity_id="hub@0,0",
                entity_type="hub",
                position=GridPosition(x=0, y=0),
                attributes={"global_x": 0, "global_y": 0, "team": "cogs", "owner": "cogs"},
            )
        ],
        team_summary=TeamSummary(team_id="cogs"),
    )

    agent_four._explore_action(state, role="aligner", summary="explore")
    agent_five._explore_action(state, role="aligner", summary="explore")

    assert agent_four._current_target_position != agent_five._current_target_position


def test_aligners_keep_sticky_target_until_a_materially_better_one_exists(cogsguard_env_info) -> None:
    policy = MettagridSemanticPolicy(cogsguard_env_info)
    agent = policy.agent_policy(4)
    state = MettagridState(
        game="cogsguard",
        step=250,
        self_state=SelfState(
            entity_id="agent-4",
            entity_type="agent",
            position=GridPosition(x=0, y=1),
            attributes={"global_x": 0, "global_y": 1, "team": "cogs"},
            inventory={"aligner": 1, "heart": 4, "hp": 100},
        ),
        visible_entities=[
            SemanticEntity(
                entity_id="hub@0,0",
                entity_type="hub",
                position=GridPosition(x=0, y=0),
                attributes={"global_x": 0, "global_y": 0, "team": "cogs", "owner": "cogs"},
            ),
            SemanticEntity(
                entity_id="junction@5,0",
                entity_type="junction",
                position=GridPosition(x=5, y=0),
                attributes={"global_x": 5, "global_y": 0},
            ),
            SemanticEntity(
                entity_id="junction@6,0",
                entity_type="junction",
                position=GridPosition(x=6, y=0),
                attributes={"global_x": 6, "global_y": 0},
            ),
        ],
        team_summary=TeamSummary(team_id="cogs"),
    )
    agent._world_model.update(state)
    agent._set_sticky_target((6, 0), "junction")

    target = agent._preferred_alignable_neutral_junction(state)

    assert target is not None
    assert target.position == (6, 0)


def test_miners_keep_sticky_extractor_target_until_a_materially_better_one_exists(cogsguard_env_info) -> None:
    agent = MettagridSemanticPolicy(cogsguard_env_info).agent_policy(0)
    state = MettagridState(
        game="cogsguard",
        step=250,
        self_state=SelfState(
            entity_id="agent-0",
            entity_type="agent",
            position=GridPosition(x=0, y=0),
            attributes={"global_x": 0, "global_y": 0, "team": "cogs"},
            inventory={"miner": 1, "hp": 100},
        ),
        visible_entities=[
            SemanticEntity(
                entity_id="germanium_extractor@5,0",
                entity_type="germanium_extractor",
                position=GridPosition(x=5, y=0),
                attributes={"global_x": 5, "global_y": 0, "remaining_uses": 7},
            ),
            SemanticEntity(
                entity_id="germanium_extractor@6,0",
                entity_type="germanium_extractor",
                position=GridPosition(x=6, y=0),
                attributes={"global_x": 6, "global_y": 0, "remaining_uses": 7},
            ),
        ],
        team_summary=TeamSummary(
            team_id="cogs",
            shared_inventory={"carbon": 20, "oxygen": 20, "germanium": 0, "silicon": 20},
        ),
    )
    agent._world_model.update(state)
    agent._resource_bias = "germanium"
    agent._set_sticky_target((6, 0), "germanium_extractor")

    action, summary = agent._choose_action(state, "miner")

    assert summary == "mine_germanium"
    assert action.name == "move_east"
    assert agent._current_target_position == (6, 0)


def test_miner_ignores_depleted_extractors(cogsguard_env_info) -> None:
    world_model = SharedWorldModel()
    agent = MettagridSemanticPolicy(cogsguard_env_info).agent_policy(0)
    agent._world_model = world_model
    state = MettagridState(
        game="cogsguard",
        step=250,
        self_state=SelfState(
            entity_id="agent-0",
            entity_type="agent",
            position=GridPosition(x=0, y=0),
            attributes={"global_x": 0, "global_y": 0, "team": "cogs"},
            inventory={"miner": 1, "hp": 100},
        ),
        visible_entities=[
            SemanticEntity(
                entity_id="carbon_extractor@2,0",
                entity_type="carbon_extractor",
                position=GridPosition(x=2, y=0),
                attributes={"global_x": 2, "global_y": 0, "remaining_uses": 0},
            ),
            SemanticEntity(
                entity_id="carbon_extractor@5,0",
                entity_type="carbon_extractor",
                position=GridPosition(x=5, y=0),
                attributes={"global_x": 5, "global_y": 0, "remaining_uses": 7},
            ),
        ],
        team_summary=TeamSummary(
            team_id="cogs",
            shared_inventory={"carbon": 0, "oxygen": 20, "germanium": 20, "silicon": 20},
        ),
    )
    world_model.update(state)

    action, summary = agent._miner_action(state)

    assert summary == "mine_carbon"
    assert action.name == "move_east"
    assert agent._current_target_position == (5, 0)


def test_miner_ignores_stale_extractors(cogsguard_env_info) -> None:
    world_model = SharedWorldModel()
    agent = MettagridSemanticPolicy(cogsguard_env_info).agent_policy(0)
    agent._world_model = world_model
    stale_state = MettagridState(
        game="cogsguard",
        step=1,
        self_state=SelfState(
            entity_id="agent-0",
            entity_type="agent",
            position=GridPosition(x=0, y=0),
            attributes={"global_x": 0, "global_y": 0, "team": "cogs"},
            inventory={"miner": 1, "hp": 100},
        ),
        visible_entities=[
            SemanticEntity(
                entity_id="carbon_extractor@2,0",
                entity_type="carbon_extractor",
                position=GridPosition(x=2, y=0),
                attributes={"global_x": 2, "global_y": 0, "remaining_uses": 7},
            ),
        ],
        team_summary=TeamSummary(
            team_id="cogs",
            shared_inventory={"carbon": 0, "oxygen": 20, "germanium": 20, "silicon": 20},
        ),
    )
    current_state = stale_state.model_copy(update={"step": 700})
    world_model.update(stale_state)

    action, summary = agent._miner_action(current_state)

    assert summary == "find_extractors"
    assert action.name in {"move_north", "move_south", "move_east", "move_west"}


def test_miner_resets_remembered_extractor_targets_when_stalled_at_hub(cogsguard_env_info) -> None:
    agent = MettagridSemanticPolicy(cogsguard_env_info).agent_policy(0)
    previous_state = MettagridState(
        game="cogsguard",
        step=10,
        self_state=SelfState(
            entity_id="agent-0",
            entity_type="agent",
            position=GridPosition(x=0, y=0),
            attributes={"global_x": 0, "global_y": 0, "team": "cogs"},
            inventory={"miner": 1, "hp": 100},
        ),
        visible_entities=[
            SemanticEntity(
                entity_id="hub@0,0",
                entity_type="hub",
                position=GridPosition(x=0, y=0),
                attributes={"global_x": 0, "global_y": 0, "team": "cogs", "owner": "cogs"},
            ),
            SemanticEntity(
                entity_id="germanium_extractor@6,0",
                entity_type="germanium_extractor",
                position=GridPosition(x=6, y=0),
                attributes={"global_x": 6, "global_y": 0, "remaining_uses": 8},
            ),
        ],
        team_summary=TeamSummary(team_id="cogs"),
    )
    current_state = MettagridState(
        game="cogsguard",
        step=40,
        self_state=SelfState(
            entity_id="agent-0",
            entity_type="agent",
            position=GridPosition(x=0, y=0),
            attributes={"global_x": 0, "global_y": 0, "team": "cogs"},
            inventory={"miner": 1, "hp": 100},
        ),
        visible_entities=[
            SemanticEntity(
                entity_id="hub@0,0",
                entity_type="hub",
                position=GridPosition(x=0, y=0),
                attributes={"global_x": 0, "global_y": 0, "team": "cogs", "owner": "cogs"},
            )
        ],
        team_summary=TeamSummary(team_id="cogs"),
    )

    agent._world_model.update(previous_state)
    agent._world_model.update(current_state)
    agent._stalled_steps = 12
    agent._set_sticky_target((6, 0), "germanium_extractor")

    action, summary = agent._miner_action(current_state)

    assert summary == "find_extractors"
    assert action.name in {"move_north", "move_south", "move_east", "move_west"}
    assert agent._sticky_target_kind is None


def test_aligner_rebuilds_heart_supply_when_team_cannot_refill(cogsguard_env_info) -> None:
    world_model = SharedWorldModel()
    agent = MettagridSemanticPolicy(cogsguard_env_info).agent_policy(4)
    agent._world_model = world_model
    state = MettagridState(
        game="cogsguard",
        step=4500,
        self_state=SelfState(
            entity_id="agent-4",
            entity_type="agent",
            position=GridPosition(x=0, y=0),
            attributes={"global_x": 0, "global_y": 0, "team": "cogs"},
            inventory={"aligner": 1, "hp": 100},
        ),
        visible_entities=[
            SemanticEntity(
                entity_id="hub@0,1",
                entity_type="hub",
                position=GridPosition(x=0, y=1),
                attributes={"global_x": 0, "global_y": 1, "team": "cogs", "owner": "cogs"},
            ),
            SemanticEntity(
                entity_id="carbon_extractor@5,0",
                entity_type="carbon_extractor",
                position=GridPosition(x=5, y=0),
                attributes={"global_x": 5, "global_y": 0, "remaining_uses": 8},
            ),
        ],
        team_summary=TeamSummary(
            team_id="cogs",
            shared_inventory={"heart": 0, "carbon": 6, "oxygen": 6, "germanium": 6, "silicon": 6},
        ),
    )
    world_model.update(state)

    action, summary = agent._aligner_action(state)

    assert summary == "rebuild_hearts_mine_carbon"
    assert action.name == "move_east"
    assert agent._current_target_position == (5, 0)


def test_scrambler_rebuilds_heart_supply_when_team_cannot_refill(cogsguard_env_info) -> None:
    world_model = SharedWorldModel()
    agent = MettagridSemanticPolicy(cogsguard_env_info).agent_policy(7)
    agent._world_model = world_model
    state = MettagridState(
        game="cogsguard",
        step=4500,
        self_state=SelfState(
            entity_id="agent-7",
            entity_type="agent",
            position=GridPosition(x=0, y=0),
            attributes={"global_x": 0, "global_y": 0, "team": "cogs"},
            inventory={"scrambler": 1, "hp": 100},
        ),
        visible_entities=[
            SemanticEntity(
                entity_id="hub@0,1",
                entity_type="hub",
                position=GridPosition(x=0, y=1),
                attributes={"global_x": 0, "global_y": 1, "team": "cogs", "owner": "cogs"},
            ),
            SemanticEntity(
                entity_id="oxygen_extractor@5,0",
                entity_type="oxygen_extractor",
                position=GridPosition(x=5, y=0),
                attributes={"global_x": 5, "global_y": 0, "remaining_uses": 8},
            ),
        ],
        team_summary=TeamSummary(
            team_id="cogs",
            shared_inventory={"heart": 0, "carbon": 10, "oxygen": 4, "germanium": 10, "silicon": 10},
        ),
    )
    world_model.update(state)

    action, summary = agent._scrambler_action(state)

    assert summary == "rebuild_hearts_mine_oxygen"
    assert action.name == "move_east"
    assert agent._current_target_position == (5, 0)


def test_unaffordable_gearless_miner_falls_back_to_mining(cogsguard_env_info) -> None:
    world_model = SharedWorldModel()
    agent = MettagridSemanticPolicy(cogsguard_env_info).agent_policy(0)
    agent._world_model = world_model
    state = MettagridState(
        game="cogsguard",
        step=4500,
        self_state=SelfState(
            entity_id="agent-0",
            entity_type="agent",
            position=GridPosition(x=0, y=0),
            attributes={"global_x": 0, "global_y": 0, "team": "cogs"},
            inventory={"hp": 100},
        ),
        visible_entities=[
            SemanticEntity(
                entity_id="miner_station@1,0",
                entity_type="miner_station",
                position=GridPosition(x=1, y=0),
                attributes={"global_x": 1, "global_y": 0, "team": "cogs"},
            ),
            SemanticEntity(
                entity_id="carbon_extractor@5,0",
                entity_type="carbon_extractor",
                position=GridPosition(x=5, y=0),
                attributes={"global_x": 5, "global_y": 0, "remaining_uses": 8},
            ),
        ],
        team_summary=TeamSummary(
            team_id="cogs",
            shared_inventory={"carbon": 0, "oxygen": 0, "germanium": 0, "silicon": 0},
        ),
    )
    world_model.update(state)

    action, summary = agent._choose_action(state, "miner")

    assert summary == "fund_miner_gear_mine_carbon"
    assert action.name in {"move_north", "move_south", "move_east", "move_west"}
    assert agent._current_target_position == (5, 0)


def test_phase_name_marks_unaffordable_role_recovery_as_fund_gear() -> None:
    state = MettagridState(
        game="cogsguard",
        step=250,
        self_state=SelfState(
            entity_id="agent-4",
            entity_type="agent",
            position=GridPosition(x=0, y=1),
            inventory={"heart": 0, "hp": 100},
        ),
        team_summary=TeamSummary(
            team_id="cogs",
            shared_inventory={"carbon": 0, "oxygen": 0, "germanium": 0, "silicon": 0},
        ),
    )

    assert _phase_name(state, "aligner") == "fund_gear"
