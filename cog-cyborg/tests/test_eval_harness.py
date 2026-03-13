from __future__ import annotations

from cog_cyborg.evals import BehavioralScenario, InterviewProbeRequest, SemanticPolicyEvaluationHarness
from cog_cyborg.policy import MettagridSemanticPolicy
from mettagrid_sdk.sdk import (
    GridPosition,
    KnownWorldState,
    MacroDirective,
    MettagridState,
    SelfState,
    SemanticEntity,
    TeamSummary,
)


def test_behavioral_scenarios_cover_role_workflows(cogsguard_env_info) -> None:
    harness = _harness(cogsguard_env_info)

    aligner = harness.run_scenario(
        BehavioralScenario(
            name="aligner-heart-capture",
            states=[
                _build_state(
                    step=10,
                    role="aligner",
                    heart=0,
                    shared_inventory={"heart": 1},
                    visible_entities=[_friendly_hub(), _neutral_junction()],
                ),
                _build_state(
                    step=11,
                    role="aligner",
                    heart=1,
                    position=(2, 0),
                    shared_inventory={"heart": 0},
                    visible_entities=[_friendly_hub(), _neutral_junction()],
                ),
            ],
        )
    )
    miner = harness.run_scenario(
        BehavioralScenario(
            name="miner-gather-deposit",
            states=[
                _build_state(
                    step=20,
                    role="miner",
                    heart=0,
                    visible_entities=[_friendly_hub(), _extractor()],
                ),
                _build_state(
                    step=21,
                    role="miner",
                    heart=0,
                    extra_inventory={"oxygen": 40},
                    visible_entities=[_friendly_hub(), _extractor()],
                ),
            ],
        )
    )
    scrambler = harness.run_scenario(
        BehavioralScenario(
            name="scrambler-neutralize",
            states=[
                _build_state(
                    step=30,
                    role="scrambler",
                    heart=0,
                    shared_inventory={"heart": 1},
                    visible_entities=[_friendly_hub(), _enemy_junction()],
                ),
                _build_state(
                    step=31,
                    role="scrambler",
                    heart=1,
                    position=(3, 0),
                    visible_entities=[_friendly_hub(), _enemy_junction()],
                ),
            ],
        )
    )

    assert aligner.steps[0].decision.summary == "acquire_heart"
    assert aligner.steps[1].decision.summary == "align_junction"
    assert miner.steps[0].decision.summary == "mine_oxygen"
    assert miner.steps[1].decision.summary == "deposit_resources"
    assert scrambler.steps[0].decision.summary == "acquire_heart"
    assert scrambler.steps[1].decision.summary == "scramble_junction"


def test_interview_probe_answers_next_action(cogsguard_env_info) -> None:
    harness = _harness(cogsguard_env_info)
    answer = harness.answer_probe(
        InterviewProbeRequest(
            question_type="what_next",
            state=_build_state(
                step=70,
                role="aligner",
                heart=0,
                shared_inventory={"heart": 1},
                visible_entities=[_friendly_hub(), _neutral_junction()],
            ),
        )
    )

    assert answer.summary == "acquire_heart"
    assert "Execute acquire_heart next as aligner." == answer.answer


def test_interview_probe_picks_best_teammate_to_deposit(cogsguard_env_info) -> None:
    harness = _harness(cogsguard_env_info)
    answer = harness.answer_probe(
        InterviewProbeRequest(
            question_type="best_teammate_to_deposit_now",
            state=_build_state(
                step=80,
                role="aligner",
                heart=0,
                visible_entities=[
                    _friendly_hub(),
                    _friendly_agent(entity_id="agent-2", x=1, y=0, role="miner", resources={"oxygen": 5}),
                    _friendly_agent(entity_id="agent-3", x=4, y=0, role="miner", resources={"oxygen": 2}),
                ],
            ),
        )
    )

    assert answer.subject_entity_id == "agent-2"
    assert "carrying 5 resources" in answer.answer


def test_interview_probe_explains_why_junction_is_not_a_good_target(cogsguard_env_info) -> None:
    harness = _harness(cogsguard_env_info)
    answer = harness.answer_probe(
        InterviewProbeRequest(
            question_type="why_not_target",
            state=_build_state(
                step=90,
                role="aligner",
                heart=0,
                shared_inventory={"heart": 1},
                visible_entities=[_friendly_hub(), _neutral_junction()],
            ),
            target_entity_id="junction@1,0",
        )
    )

    assert "missing_heart" in answer.answer
    assert "policy_requires_heart_first" in answer.answer


def _harness(cogsguard_env_info) -> SemanticPolicyEvaluationHarness:
    policy = MettagridSemanticPolicy(cogsguard_env_info).agent_policy(0)
    policy._macro_directive = lambda state: MacroDirective(role=state.self_state.role)  # type: ignore[method-assign]
    return SemanticPolicyEvaluationHarness(policy)


def _build_state(
    *,
    step: int,
    role: str,
    heart: int,
    position: tuple[int, int] = (0, 0),
    visible_entities: list[SemanticEntity] | None = None,
    extra_inventory: dict[str, int] | None = None,
    shared_inventory: dict[str, int] | None = None,
) -> MettagridState:
    inventory = {"energy": 90, role: 1, "heart": heart, "hp": 100}
    if extra_inventory is not None:
        inventory.update(extra_inventory)
    resolved_shared_inventory = {
        "carbon": 10,
        "oxygen": 10,
        "germanium": 10,
        "silicon": 10,
    }
    if shared_inventory is not None:
        resolved_shared_inventory.update(shared_inventory)
    return MettagridState(
        game="cogsguard",
        step=step,
        self_state=SelfState(
            entity_id="agent-0",
            entity_type="agent",
            position=GridPosition(x=position[0], y=position[1]),
            role=role,
            inventory=inventory,
            labels=["friendly"],
            status=[] if heart == 0 else ["has_heart"],
            attributes={"team": "cogs", "global_x": position[0], "global_y": position[1]},
        ),
        visible_entities=[] if visible_entities is None else visible_entities,
        known_world=KnownWorldState(frontier_regions=[]),
        team_summary=TeamSummary(team_id="cogs", shared_inventory=resolved_shared_inventory),
    )


def _friendly_hub() -> SemanticEntity:
    return SemanticEntity(
        entity_id="hub@0,1",
        entity_type="hub",
        position=GridPosition(x=0, y=1),
        labels=["hub", "friendly"],
        attributes={"owner": "cogs", "team": "cogs", "global_x": 0, "global_y": 1},
    )


def _neutral_junction() -> SemanticEntity:
    return SemanticEntity(
        entity_id="junction@1,0",
        entity_type="junction",
        position=GridPosition(x=1, y=0),
        labels=["junction", "neutral"],
        attributes={"owner": "neutral", "global_x": 1, "global_y": 0},
    )


def _enemy_junction() -> SemanticEntity:
    return SemanticEntity(
        entity_id="junction@2,0",
        entity_type="junction",
        position=GridPosition(x=2, y=0),
        labels=["junction", "enemy"],
        attributes={"owner": "clips", "global_x": 2, "global_y": 0},
    )


def _extractor() -> SemanticEntity:
    return SemanticEntity(
        entity_id="oxygen_extractor@2,1",
        entity_type="oxygen_extractor",
        position=GridPosition(x=2, y=1),
        labels=["extractor", "friendly"],
        attributes={"team": "cogs", "global_x": 2, "global_y": 1},
    )


def _friendly_agent(
    *,
    entity_id: str,
    x: int,
    y: int,
    role: str,
    resources: dict[str, int],
) -> SemanticEntity:
    attributes = {"team": "cogs", "role": role, "agent_id": int(entity_id.removeprefix("agent-"))}
    attributes.update(resources)
    return SemanticEntity(
        entity_id=entity_id,
        entity_type="agent",
        position=GridPosition(x=x, y=y),
        labels=["agent", "friendly"],
        attributes=attributes,
    )
