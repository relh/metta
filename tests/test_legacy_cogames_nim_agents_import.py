from __future__ import annotations

import importlib.util


def test_legacy_cogames_nim_agents_import_path_exists() -> None:
    # Old policy bundles reference this path (pre `cogames-agents` split).
    assert importlib.util.find_spec("cogames.policy.nim_agents") is not None
    assert importlib.util.find_spec("cogames.policy.nim_agents.agents") is not None
    import cogames.policy.nim_agents  # noqa: F401
    import cogames.policy.nim_agents.agents as legacy_agents

    assert hasattr(legacy_agents, "ThinkyAgentsMultiPolicy")
