from __future__ import annotations

from cog_cognition.planning import HierarchicalPlanner
from cog_cognition.reflection import ReflectionEngine
from cog_cyborg.memory import MemoryStore
from mettagrid_sdk.sdk import (
    GridPosition,
    KnownWorldState,
    MettagridState,
    SelfState,
    SemanticEntity,
    TeamSummary,
)


def test_reflection_synthesizes_lane_contested_belief_from_repeated_enemy_pressure() -> None:
    store = MemoryStore()
    _append_event(
        store,
        record_id="evt-1",
        event_type="enemy_seen",
        summary="Enemy scrambler seen on the east lane.",
        step=10,
        tags=["aligner", "east_lane", "junction"],
        importance=0.8,
    )
    _append_event(
        store,
        record_id="evt-2",
        event_type="junction_owner_changed",
        summary="East lane junction flipped to clips.",
        step=11,
        tags=["aligner", "east_lane", "junction"],
        importance=0.85,
    )

    created = ReflectionEngine().reflect(_build_state(step=12, role="aligner"), store)

    assert len(created) == 1
    belief = created[0]
    assert belief.belief_type == "lane_contested"
    assert belief.region_id == "east_lane"
    assert belief.evidence_ids == ["evt-1", "evt-2"]


def test_reflection_synthesizes_aligner_requires_heart_belief() -> None:
    store = MemoryStore()
    _append_event(
        store,
        record_id="evt-10",
        event_type="capture_failed_no_heart",
        summary="Aligner failed to capture without a heart.",
        step=20,
        tags=["aligner", "heart", "junction"],
        importance=0.8,
        role_context="aligner",
    )
    _append_event(
        store,
        record_id="evt-11",
        event_type="capture_failed_no_heart",
        summary="Another aligner capture failed because no heart was carried.",
        step=21,
        tags=["aligner", "heart", "junction"],
        importance=0.9,
        role_context="aligner",
    )

    created = ReflectionEngine().reflect(_build_state(step=22, role="aligner"), store)

    assert len(created) == 1
    belief = created[0]
    assert belief.belief_type == "aligner_requires_heart_before_commit"
    assert belief.role_context == "aligner"
    assert belief.evidence_ids == ["evt-10", "evt-11"]


def test_reflection_is_sparse_and_does_not_duplicate_recent_belief() -> None:
    store = MemoryStore()
    _append_event(
        store,
        record_id="evt-20",
        event_type="path_blocked",
        summary="North lane path blocked.",
        step=30,
        tags=["scout", "north_lane"],
        importance=0.8,
        role_context="scout",
    )
    _append_event(
        store,
        record_id="evt-21",
        event_type="region_unsafe",
        summary="North lane remains unsafe.",
        step=31,
        tags=["scout", "north_lane"],
        importance=0.9,
        role_context="scout",
    )
    first = ReflectionEngine().reflect(_build_state(step=32, role="scout"), store)
    second = ReflectionEngine().reflect(_build_state(step=33, role="scout"), store)

    assert len(first) == 1
    assert first[0].belief_type == "region_path_risky"
    assert second == []


def test_reflection_beliefs_feed_existing_planner() -> None:
    store = MemoryStore()
    _append_event(
        store,
        record_id="evt-30",
        event_type="enemy_seen",
        summary="Enemy pressure on east lane.",
        step=40,
        tags=["scout", "east_lane"],
        importance=0.8,
        role_context="scout",
    )
    _append_event(
        store,
        record_id="evt-31",
        event_type="region_unsafe",
        summary="East lane unsafe.",
        step=41,
        tags=["scout", "east_lane"],
        importance=0.85,
        role_context="scout",
    )
    ReflectionEngine().reflect(
        _build_state(step=42, role="scout", frontier_regions=["east_lane", "west_lane"]),
        store,
    )

    decision = HierarchicalPlanner().decide(
        _build_state(step=43, role="scout", frontier_regions=["east_lane", "west_lane"]),
        store,
    )

    assert decision.plan.active_subtask.kind == "explore_frontier"
    assert "west_lane" in decision.plan.active_subtask.target_tags


def _build_state(
    *,
    step: int,
    role: str,
    frontier_regions: list[str] | None = None,
) -> MettagridState:
    return MettagridState(
        game="cogsguard",
        step=step,
        self_state=SelfState(
            entity_id="agent-0",
            entity_type="agent",
            position=GridPosition(x=0, y=0),
            role=role,
            inventory={"energy": 90, role: 1, "heart": 0},
            labels=["friendly"],
            status=[],
            attributes={"team": "cogs"},
        ),
        visible_entities=[_friendly_hub()],
        known_world=KnownWorldState(frontier_regions=[] if frontier_regions is None else frontier_regions),
        team_summary=TeamSummary(team_id="cogs"),
    )


def _friendly_hub() -> SemanticEntity:
    return SemanticEntity(
        entity_id="hub@0,1",
        entity_type="hub",
        position=GridPosition(x=0, y=1),
        labels=["hub", "friendly"],
        attributes={"owner": "cogs", "team": "cogs"},
    )


def _append_event(
    store: MemoryStore,
    *,
    record_id: str,
    event_type: str,
    summary: str,
    step: int,
    tags: list[str],
    importance: float,
    role_context: str = "aligner",
) -> None:
    store.append_event(
        record_id=record_id,
        event_type=event_type,
        summary=summary,
        game="cogsguard",
        step=step,
        role_context=role_context,
        tags=tags,
        importance=importance,
        location=GridPosition(x=1, y=0),
    )
