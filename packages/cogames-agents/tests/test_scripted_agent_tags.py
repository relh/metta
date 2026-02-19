from __future__ import annotations

from cogames_agents.policy.scripted_agent.utils import create_object_state

from mettagrid.config.tag import typeTag


def test_primary_tag_prefers_type_over_collective() -> None:
    obj_state = create_object_state(
        {"tags": [1, 2]},
        tag_names={1: "collective:cogs", 2: typeTag("junction")},
    )

    assert obj_state.name == "junction"
    assert obj_state.tags == ["collective:cogs", typeTag("junction")]


def test_primary_tag_falls_back_to_non_collective() -> None:
    obj_state = create_object_state(
        {"tags": [1, 2]},
        tag_names={1: "collective:clips", 2: "hub"},
    )

    assert obj_state.name == "hub"
    assert obj_state.tags == ["collective:clips", "hub"]
