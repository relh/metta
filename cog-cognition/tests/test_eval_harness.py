from __future__ import annotations

from cog_cognition.evals import BehavioralScenario, InterviewProbeRequest, PlannerEvaluationHarness
from cog_cyborg.memory import MemoryStore
from mettagrid_sdk.sdk import (
    GridPosition,
    KnownWorldState,
    MettagridState,
    SelfState,
    SemanticEntity,
    SemanticEvent,
    TeamSummary,
)


def test_behavioral_scenarios_cover_role_workflows() -> None:
    store = MemoryStore()
    harness = PlannerEvaluationHarness()

    aligner = harness.run_scenario(
        BehavioralScenario(
            name="aligner-heart-capture",
            states=[
                _build_state(
                    step=10,
                    role="aligner",
                    heart=0,
                    visible_entities=[_friendly_hub(), _neutral_junction()],
                ),
                _build_state(
                    step=11,
                    role="aligner",
                    heart=1,
                    visible_entities=[_friendly_hub(), _neutral_junction()],
                    recent_events=[_event("heart_acquired", 11, "Agent acquired a heart.")],
                ),
            ],
        ),
        store,
        persist_store=store,
    )
    miner = PlannerEvaluationHarness().run_scenario(
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
                    extra_inventory={"oxygen": 4},
                    visible_entities=[_friendly_hub(), _extractor()],
                ),
            ],
        ),
        MemoryStore(),
    )
    scrambler = PlannerEvaluationHarness().run_scenario(
        BehavioralScenario(
            name="scrambler-neutralize",
            states=[
                _build_state(
                    step=30,
                    role="scrambler",
                    heart=0,
                    visible_entities=[_friendly_hub(), _enemy_junction()],
                ),
                _build_state(
                    step=31,
                    role="scrambler",
                    heart=1,
                    visible_entities=[_friendly_hub(), _enemy_junction()],
                    recent_events=[_event("heart_acquired", 31, "Scrambler picked up a heart.")],
                ),
            ],
        ),
        MemoryStore(),
    )
    scout_store = MemoryStore()
    scout_store.append_belief(
        record_id="belief-east",
        belief_type="east_lane_contested",
        summary="East lane is contested.",
        game="cogsguard",
        step=39,
        role_context="scout",
        tags=["east_lane", "scout"],
        importance=0.9,
        confidence=0.7,
    )
    scout = PlannerEvaluationHarness().run_scenario(
        BehavioralScenario(
            name="scout-frontier-discovery",
            states=[
                _build_state(
                    step=40,
                    role="scout",
                    heart=0,
                    frontier_regions=["east_lane", "west_lane"],
                )
            ],
        ),
        scout_store,
    )

    assert aligner.steps[0].decision.plan.active_subtask.kind == "acquire_heart"
    assert aligner.steps[1].decision.plan.active_subtask.kind == "capture_neutral_junction"
    assert miner.steps[0].decision.plan.active_subtask.kind == "collect_resources"
    assert miner.steps[1].decision.plan.active_subtask.kind == "deposit_resources"
    assert scrambler.steps[0].decision.plan.active_subtask.kind == "acquire_heart"
    assert scrambler.steps[1].decision.plan.active_subtask.kind == "neutralize_enemy_junction"
    assert scout.steps[0].decision.plan.active_subtask.kind == "explore_frontier"
    assert "west_lane" in scout.steps[0].decision.plan.active_subtask.target_tags


def test_behavioral_scenarios_cover_failure_modes() -> None:
    blocked = PlannerEvaluationHarness().run_scenario(
        BehavioralScenario(
            name="blocked-route",
            states=[
                _build_state(step=50, role="scout", heart=0, frontier_regions=["north_lane"]),
                _build_state(
                    step=51,
                    role="scout",
                    heart=0,
                    frontier_regions=["west_lane"],
                    recent_events=[_event("path_blocked", 51, "Path was blocked while advancing north.")],
                ),
            ],
        ),
        MemoryStore(),
    )
    empty_deposit = PlannerEvaluationHarness().run_scenario(
        BehavioralScenario(
            name="empty-deposit-target",
            states=[_build_state(step=60, role="miner", heart=0, visible_entities=[_friendly_hub(), _extractor()])],
        ),
        MemoryStore(),
    )

    assert blocked.steps[0].decision.plan.active_subtask.kind == "explore_frontier"
    assert blocked.steps[1].decision.mode == "replan"
    assert "west_lane" in blocked.steps[1].decision.plan.active_subtask.target_tags
    assert empty_deposit.steps[0].decision.plan.active_subtask.kind == "collect_resources"


def test_behavioral_scenarios_reset_planner_state_between_runs() -> None:
    harness = PlannerEvaluationHarness()
    first = harness.run_scenario(
        BehavioralScenario(
            name="first",
            states=[
                _build_state(
                    step=10,
                    role="aligner",
                    heart=0,
                    visible_entities=[_friendly_hub(), _neutral_junction()],
                )
            ],
        ),
        MemoryStore(),
    )
    second = harness.run_scenario(
        BehavioralScenario(
            name="second",
            states=[
                _build_state(
                    step=40,
                    role="aligner",
                    heart=0,
                    visible_entities=[_friendly_hub(), _neutral_junction()],
                )
            ],
        ),
        MemoryStore(),
    )

    assert first.steps[0].decision.mode == "replan"
    assert second.steps[0].decision.mode == "replan"
    assert second.steps[0].decision.plan.agenda_id != first.steps[0].decision.plan.agenda_id


def test_interview_probe_answers_next_action_and_abandon_triggers() -> None:
    store = MemoryStore()
    harness = PlannerEvaluationHarness()
    state = _build_state(
        step=70,
        role="aligner",
        heart=0,
        visible_entities=[_friendly_hub(), _neutral_junction()],
    )

    next_answer = harness.answer_probe(
        InterviewProbeRequest(question_type="what_next", state=state),
        store,
    )
    abandon_answer = harness.answer_probe(
        InterviewProbeRequest(question_type="abandon_triggers", state=state),
        store,
    )

    assert next_answer.subtask_kind == "acquire_heart"
    assert "Acquire a heart" in next_answer.answer
    assert "enemy_seen" in abandon_answer.answer


def test_interview_probe_picks_best_teammate_to_deposit() -> None:
    harness = PlannerEvaluationHarness()
    state = _build_state(
        step=80,
        role="aligner",
        heart=0,
        visible_entities=[
            _friendly_hub(),
            _friendly_agent(entity_id="agent-2", x=1, y=0, role="miner", resources={"oxygen": 5}),
            _friendly_agent(entity_id="agent-3", x=4, y=0, role="miner", resources={"oxygen": 2}),
        ],
    )

    answer = harness.answer_probe(
        InterviewProbeRequest(question_type="best_teammate_to_deposit_now", state=state),
        MemoryStore(),
    )

    assert answer.subject_entity_id == "agent-2"
    assert "carrying 5 resources" in answer.answer


def test_interview_probe_explains_why_junction_is_not_a_good_target() -> None:
    store = MemoryStore()
    store.append_belief(
        record_id="belief-east",
        belief_type="east_lane_contested",
        summary="East lane is contested and risky for aligners.",
        game="cogsguard",
        step=89,
        role_context="aligner",
        tags=["junction", "east_lane", "aligner"],
        importance=0.9,
        confidence=0.7,
    )
    harness = PlannerEvaluationHarness()
    state = _build_state(
        step=90,
        role="aligner",
        heart=0,
        visible_entities=[_friendly_hub(), _neutral_junction(labels=["junction", "neutral", "east_lane"])],
    )

    answer = harness.answer_probe(
        InterviewProbeRequest(question_type="why_not_target", state=state, target_entity_id="junction@1,0"),
        store,
    )

    assert "missing_heart" in answer.answer
    assert "East lane is contested and risky for aligners." in answer.answer
    assert "belief-east" in answer.evidence_ids


def _build_state(
    *,
    step: int,
    role: str,
    heart: int,
    visible_entities: list[SemanticEntity] | None = None,
    frontier_regions: list[str] | None = None,
    recent_events: list[SemanticEvent] | None = None,
    extra_inventory: dict[str, int] | None = None,
) -> MettagridState:
    inventory = {"energy": 90, role: 1, "heart": heart}
    if extra_inventory is not None:
        inventory.update(extra_inventory)
    return MettagridState(
        game="cogsguard",
        step=step,
        self_state=SelfState(
            entity_id="agent-0",
            entity_type="agent",
            position=GridPosition(x=0, y=0),
            role=role,
            inventory=inventory,
            labels=["friendly"],
            status=[] if heart == 0 else ["has_heart"],
            attributes={"team": "cogs"},
        ),
        visible_entities=[] if visible_entities is None else visible_entities,
        known_world=KnownWorldState(frontier_regions=[] if frontier_regions is None else frontier_regions),
        team_summary=TeamSummary(team_id="cogs"),
        recent_events=[] if recent_events is None else recent_events,
    )


def _friendly_hub() -> SemanticEntity:
    return SemanticEntity(
        entity_id="hub@0,1",
        entity_type="hub",
        position=GridPosition(x=0, y=1),
        labels=["hub", "friendly"],
        attributes={"owner": "cogs", "team": "cogs"},
    )


def _neutral_junction(labels: list[str] | None = None) -> SemanticEntity:
    return SemanticEntity(
        entity_id="junction@1,0",
        entity_type="junction",
        position=GridPosition(x=1, y=0),
        labels=["junction", "neutral"] if labels is None else labels,
        attributes={"owner": "neutral"},
    )


def _enemy_junction() -> SemanticEntity:
    return SemanticEntity(
        entity_id="junction@2,0",
        entity_type="junction",
        position=GridPosition(x=2, y=0),
        labels=["junction", "enemy"],
        attributes={"owner": "clips"},
    )


def _extractor() -> SemanticEntity:
    return SemanticEntity(
        entity_id="oxygen_extractor@2,1",
        entity_type="oxygen_extractor",
        position=GridPosition(x=2, y=1),
        labels=["extractor", "friendly"],
        attributes={"team": "cogs"},
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


def _event(event_type: str, step: int, summary: str) -> SemanticEvent:
    return SemanticEvent(
        event_id=f"{event_type}:{step}",
        event_type=event_type,
        step=step,
        location=GridPosition(x=0, y=0),
        importance=0.8,
        summary=summary,
    )
