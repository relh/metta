from __future__ import annotations

from cog_cognition.planning import HierarchicalPlanner
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


def test_planner_holds_plan_until_trigger_fires() -> None:
    store = MemoryStore()
    store.append_belief(
        record_id="belief-east",
        belief_type="east_lane_contested",
        summary="East lane is contested and risky for aligners.",
        game="cogsguard",
        step=18,
        role_context="aligner",
        tags=["aligner", "east_lane", "junction"],
        importance=0.9,
        confidence=0.8,
    )
    planner = HierarchicalPlanner()

    first = planner.decide(_build_aligner_state(step=20, heart=0), store, persist_store=store)
    second = planner.decide(_build_aligner_state(step=21, heart=0), store, persist_store=store)

    assert first.mode == "replan"
    assert first.plan.active_subtask.kind == "acquire_heart"
    assert "East lane is contested and risky for aligners." in first.plan.notes
    assert second.mode == "continue"
    assert second.plan.agenda_id == first.plan.agenda_id
    assert [record.kind for record in store.recent_records(limit=2)] == ["belief", "plan"]


def test_planner_reacts_to_heart_acquired_and_advances_to_capture() -> None:
    store = MemoryStore()
    planner = HierarchicalPlanner()
    planner.decide(_build_aligner_state(step=20, heart=0), store, persist_store=store)

    decision = planner.decide(
        _build_aligner_state(
            step=21,
            heart=1,
            recent_events=[
                SemanticEvent(
                    event_id="evt-heart",
                    event_type="heart_acquired",
                    step=21,
                    location=GridPosition(x=0, y=0),
                    importance=0.9,
                    summary="Agent acquired a heart.",
                )
            ],
        ),
        store,
        persist_store=store,
    )

    assert decision.mode == "replan"
    assert decision.plan.active_subtask.kind == "capture_neutral_junction"
    assert decision.plan.active_subtask.target_entity_id == "junction@1,0"
    assert any(trigger.trigger_type == "heart_acquired" for trigger in decision.triggers)


def test_planner_uses_beliefs_to_choose_safer_frontier() -> None:
    store = MemoryStore()
    store.append_belief(
        record_id="belief-east",
        belief_type="east_lane_contested",
        summary="East lane is currently contested.",
        game="cogsguard",
        step=30,
        role_context="scout",
        tags=["east_lane", "scout"],
        importance=0.85,
        confidence=0.7,
    )
    planner = HierarchicalPlanner()

    decision = planner.decide(
        _build_state(
            step=31,
            role="scout",
            heart=0,
            frontier_regions=["east_lane", "west_lane"],
        ),
        store,
        persist_store=store,
    )

    assert decision.plan.active_subtask.kind == "explore_frontier"
    assert "west_lane" in decision.plan.active_subtask.target_tags
    assert "East lane is currently contested." in decision.plan.notes


def test_planner_reacts_to_enemy_sighting_for_scout() -> None:
    store = MemoryStore()
    planner = HierarchicalPlanner()
    planner.decide(
        _build_state(
            step=40,
            role="scout",
            heart=0,
            frontier_regions=["north_lane"],
        ),
        store,
        persist_store=store,
    )

    decision = planner.decide(
        _build_state(
            step=41,
            role="scout",
            heart=0,
            frontier_regions=["north_lane"],
            visible_entities=[_enemy_agent()],
            recent_events=[
                SemanticEvent(
                    event_id="evt-enemy",
                    event_type="enemy_seen",
                    step=41,
                    location=GridPosition(x=2, y=0),
                    importance=0.8,
                    summary="Enemy agent became visible.",
                )
            ],
        ),
        store,
        persist_store=store,
    )

    assert decision.mode == "replan"
    assert decision.plan.active_subtask.kind == "shadow_enemy"
    assert any(trigger.trigger_type == "enemy_seen" for trigger in decision.triggers)


def test_planner_replans_after_neutralizing_enemy_junction() -> None:
    store = MemoryStore()
    planner = HierarchicalPlanner()

    first = planner.decide(
        _build_state(
            step=50,
            role="scrambler",
            heart=1,
            visible_entities=[_friendly_hub(), _enemy_junction()],
        ),
        store,
        persist_store=store,
    )
    second = planner.decide(
        _build_state(
            step=51,
            role="scrambler",
            heart=1,
            visible_entities=[_friendly_hub(), _neutralized_junction()],
        ),
        store,
        persist_store=store,
    )

    assert first.plan.active_subtask.kind == "neutralize_enemy_junction"
    assert second.mode == "replan"
    assert second.plan.active_subtask.kind == "regroup_at_hub"
    assert any(trigger.trigger_type == "subtask_completed" for trigger in second.triggers)


def test_planner_pressure_completion_handles_missing_team_summary() -> None:
    store = MemoryStore()
    planner = HierarchicalPlanner()

    first = planner.decide(
        _build_state(
            step=60,
            role="scrambler",
            heart=0,
            visible_entities=[_enemy_agent()],
        ),
        store,
        persist_store=store,
    )
    second = planner.decide(
        _build_state(
            step=61,
            role="scrambler",
            heart=0,
            visible_entities=[],
            team_id=None,
        ),
        store,
        persist_store=store,
    )

    assert first.plan.active_subtask.kind == "pressure_enemy_lane"
    assert second.mode == "replan"
    assert second.plan.active_subtask.kind == "survey_visible_region"
    assert any(trigger.trigger_type == "subtask_completed" for trigger in second.triggers)


def _build_aligner_state(
    *,
    step: int,
    heart: int,
    recent_events: list[SemanticEvent] | None = None,
) -> MettagridState:
    return _build_state(
        step=step,
        role="aligner",
        heart=heart,
        visible_entities=[_friendly_hub(), _neutral_junction()],
        frontier_regions=["east_lane", "west_lane"],
        recent_events=recent_events,
    )


def _build_state(
    *,
    step: int,
    role: str,
    heart: int,
    visible_entities: list[SemanticEntity] | None = None,
    frontier_regions: list[str] | None = None,
    recent_events: list[SemanticEvent] | None = None,
    team_id: str | None = "cogs",
) -> MettagridState:
    inventory = {"energy": 90, role: 1, "heart": heart}
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
        team_summary=None if team_id is None else TeamSummary(team_id=team_id),
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


def _neutral_junction() -> SemanticEntity:
    return SemanticEntity(
        entity_id="junction@1,0",
        entity_type="junction",
        position=GridPosition(x=1, y=0),
        labels=["junction", "neutral"],
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


def _neutralized_junction() -> SemanticEntity:
    return SemanticEntity(
        entity_id="junction@2,0",
        entity_type="junction",
        position=GridPosition(x=2, y=0),
        labels=["junction", "neutral"],
        attributes={"owner": "neutral"},
    )


def _enemy_agent() -> SemanticEntity:
    return SemanticEntity(
        entity_id="agent-9",
        entity_type="agent",
        position=GridPosition(x=2, y=0),
        labels=["agent", "enemy"],
        attributes={"team": "clips", "role": "scrambler"},
    )
