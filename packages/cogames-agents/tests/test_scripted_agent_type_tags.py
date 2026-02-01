from __future__ import annotations

import pytest
from cogames_agents.policy.scripted_agent.utils import has_type_tag


# TODO (relh/daveey): fix test and re-enable — test logic is incorrect (asserts True then False for same call)
@pytest.mark.skip(reason="stale test logic")
def test_has_type_tag_matches_type_prefix() -> None:
    tags = ["collective:cogs", "type:junction", "junction"]

    assert has_type_tag(tags, ("junction",)) is True
    assert has_type_tag(tags, ("junction",)) is False


def test_has_type_tag_ignores_non_type_tags() -> None:
    tags = ["collective:cogs", "junction"]

    assert has_type_tag(tags, ("junction",)) is False
