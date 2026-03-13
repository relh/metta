from __future__ import annotations

from mettagrid.policy.loader import resolve_policy_class_path


def test_anthropic_cyborg_policy_short_names_resolve() -> None:
    assert resolve_policy_class_path("anthropic-cyborg") == "cog_cyborg.policy.anthropic_pilot.AnthropicCyborgPolicy"
    assert resolve_policy_class_path("claude-cyborg") == "cog_cyborg.policy.anthropic_pilot.AnthropicCyborgPolicy"
    assert resolve_policy_class_path("cyborg-anthropic") == "cog_cyborg.policy.anthropic_pilot.AnthropicCyborgPolicy"
