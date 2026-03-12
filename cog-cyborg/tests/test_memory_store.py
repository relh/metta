from __future__ import annotations

from pathlib import Path

from cog_cyborg.memory import MemoryStore
from mettagrid_sdk.sdk import GridPosition, SemanticEvent


def test_memory_store_persists_typed_records(tmp_path: Path) -> None:
    memory_file = tmp_path / "semantic_memory.jsonl"
    store = MemoryStore(backing_file=memory_file)

    store.append_event(
        record_id="evt-1",
        event_type="enemy_seen",
        summary="Enemy scrambler spotted near east junction.",
        game="cogsguard",
        step=18,
        role_context="aligner",
        tags=["junction", "east_lane", "scrambler"],
        importance=0.8,
        location=GridPosition(x=3, y=-1),
    )
    store.append_plan(
        record_id="plan-1",
        plan_type="capture_east_junction",
        summary="Pressure east neutral junction after grabbing a heart.",
        game="cogsguard",
        step=19,
        role_context="aligner",
        tags=["junction", "east_lane", "heart"],
        importance=0.7,
    )
    store.append_belief(
        record_id="belief-1",
        belief_type="east_lane_contested",
        summary="East lane is contested and usually has enemy scramblers.",
        game="cogsguard",
        step=20,
        role_context="aligner",
        tags=["junction", "east_lane", "scrambler"],
        importance=0.9,
        confidence=0.75,
    )

    reloaded_store = MemoryStore.from_file(memory_file)
    records = reloaded_store.recent_records(limit=3)

    assert [record.kind for record in records] == ["event", "plan", "belief"]
    assert records[-1].summary == "East lane is contested and usually has enemy scramblers."


def test_memory_store_can_append_semantic_events() -> None:
    store = MemoryStore()

    created = store.append_semantic_events(
        [
            SemanticEvent(
                event_id="evt-junction",
                event_type="junction_owner_changed",
                step=32,
                location=GridPosition(x=1, y=-1),
                importance=0.8,
                summary="Junction changed ownership from neutral to cogs.",
                evidence=["previous_owner=neutral", "current_owner=cogs"],
            )
        ],
        game="cogsguard",
        role_context="aligner",
        tags=["junction"],
    )

    assert len(created) == 1
    assert created[0].kind == "event"
    assert created[0].event_type == "junction_owner_changed"
    assert store.recent_records(limit=1)[0].evidence_ids == ["previous_owner=neutral", "current_owner=cogs"]


def test_memory_store_persists_scratchpad(tmp_path: Path) -> None:
    scratchpad_file = tmp_path / "memory.md"
    store = MemoryStore(scratchpad_file=scratchpad_file)

    store.replace_scratchpad("Open with miners.")
    store.append_scratchpad("\nRotate into aligners when hearts appear.")

    reloaded = MemoryStore(scratchpad_file=scratchpad_file)

    assert "Open with miners." in reloaded.read_scratchpad()
    assert "Rotate into aligners" in reloaded.read_scratchpad()


def test_memory_store_supports_keyed_scratchpad_updates(tmp_path: Path) -> None:
    store = MemoryStore(scratchpad_file=tmp_path / "memory.md")

    store["phase"] = "resource_coverage"
    store["hearts_online"] = False
    store.setdefault("goal", "open coverage")
    store["phase"] = "aligner_pressure"

    assert store["phase"] == "aligner_pressure"
    assert store.get("hearts_online") is False
    assert "goal" in store
    assert "phase: aligner_pressure" in store.read_scratchpad()
