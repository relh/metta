from __future__ import annotations

from cog_cyborg.memory import MemoryStore
from mettagrid_sdk.sdk import MemoryQuery


def test_memory_retrieval_ranks_relevant_records_highest() -> None:
    store = MemoryStore()
    store.append_event(
        record_id="evt-east",
        event_type="enemy_seen",
        summary="Enemy scrambler spotted on the east lane near a junction.",
        game="cogsguard",
        step=48,
        role_context="aligner",
        tags=["junction", "east_lane", "scrambler", "aligner"],
        importance=0.8,
    )
    store.append_belief(
        record_id="belief-east",
        belief_type="east_lane_contested",
        summary="East lane is contested and risky for aligners.",
        game="cogsguard",
        step=50,
        role_context="aligner",
        tags=["junction", "east_lane", "aligner"],
        importance=0.95,
        confidence=0.8,
    )
    store.append_event(
        record_id="evt-hub",
        event_type="deposit_complete",
        summary="Miner deposited silicon safely at the west hub.",
        game="cogsguard",
        step=49,
        role_context="miner",
        tags=["hub", "west_lane", "miner"],
        importance=0.5,
    )

    retrieved = store.retrieve(
        MemoryQuery(
            game="cogsguard",
            step=52,
            role_context="aligner",
            target_tags=["junction", "east_lane", "aligner"],
            active_plan="capture_east_junction",
            text="What do I know about the east junction lane?",
        ),
        limit=2,
    )

    assert [item.record.record_id for item in retrieved] == ["belief-east", "evt-east"]
    assert retrieved[0].score >= retrieved[1].score


def test_memory_retrieval_renders_prompt_slice() -> None:
    store = MemoryStore()
    store.append_plan(
        record_id="plan-1",
        plan_type="capture_east_junction",
        summary="Get a heart and pressure the east neutral junction.",
        game="cogsguard",
        step=21,
        role_context="aligner",
        tags=["junction", "east_lane", "heart", "aligner"],
        importance=0.7,
    )

    rendered = store.render_prompt_context(
        MemoryQuery(
            game="cogsguard",
            step=24,
            role_context="aligner",
            target_tags=["junction", "aligner"],
        ),
        limit=3,
    )

    assert "RETRIEVED SEMANTIC MEMORY" in rendered
    assert "capture_east_junction" in rendered
    assert "Get a heart and pressure the east neutral junction." in rendered


def test_memory_retrieval_does_not_treat_future_steps_as_maximally_recent() -> None:
    store = MemoryStore()
    store.append_belief(
        record_id="belief-current",
        belief_type="east_lane_contested",
        summary="Current run east lane pressure is contested.",
        game="cogsguard",
        step=18,
        role_context="aligner",
        tags=["junction", "east_lane", "aligner"],
        importance=0.8,
        confidence=0.7,
    )
    store.append_belief(
        record_id="belief-future",
        belief_type="east_lane_contested",
        summary="Old run east lane pressure was contested.",
        game="cogsguard",
        step=180,
        role_context="aligner",
        tags=["junction", "east_lane", "aligner"],
        importance=0.8,
        confidence=0.7,
    )

    retrieved = store.retrieve(
        MemoryQuery(
            game="cogsguard",
            step=20,
            role_context="aligner",
            target_tags=["junction", "east_lane", "aligner"],
        ),
        limit=2,
    )

    assert [item.record.record_id for item in retrieved] == ["belief-current", "belief-future"]
    assert retrieved[0].recency_score > retrieved[1].recency_score
