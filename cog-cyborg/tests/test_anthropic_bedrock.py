from __future__ import annotations

import cog_cyborg.providers.anthropic as anthropic_provider
from cog_cyborg.provider_utils import (
    DEFAULT_BEDROCK_MODEL,
    get_default_anthropic_model,
    should_use_anthropic_bedrock,
)


def test_should_use_bedrock_when_flag_enabled(monkeypatch) -> None:
    monkeypatch.setenv("CLAUDE_CODE_USE_BEDROCK", "1")

    assert should_use_anthropic_bedrock(api_key="direct-key") is True


def test_should_use_bedrock_without_api_key(monkeypatch) -> None:
    monkeypatch.delenv("CLAUDE_CODE_USE_BEDROCK", raising=False)

    assert should_use_anthropic_bedrock(api_key=None) is True


def test_should_use_bedrock_with_blank_api_key(monkeypatch) -> None:
    monkeypatch.delenv("CLAUDE_CODE_USE_BEDROCK", raising=False)

    assert should_use_anthropic_bedrock(api_key="") is True


def test_get_default_anthropic_model_prefers_env_override(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_MODEL", "us.anthropic.claude-haiku-4-5-20251001-v1:0")

    assert get_default_anthropic_model(use_bedrock=True) == "us.anthropic.claude-haiku-4-5-20251001-v1:0"


def test_get_default_anthropic_model_has_bedrock_default(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)

    assert get_default_anthropic_model(use_bedrock=True) == DEFAULT_BEDROCK_MODEL


def test_build_anthropic_client_uses_bedrock_when_requested(monkeypatch) -> None:
    called: dict[str, object] = {}

    class FakeBedrock:
        def __init__(self, **kwargs):
            called["kwargs"] = kwargs

    monkeypatch.setattr(anthropic_provider, "AnthropicBedrock", FakeBedrock)
    monkeypatch.setenv("CLAUDE_CODE_USE_BEDROCK", "1")
    monkeypatch.setenv("AWS_PROFILE", "softmax")
    monkeypatch.setenv("AWS_REGION", "us-east-1")

    client = anthropic_provider.build_anthropic_client(api_key="direct-key")

    assert isinstance(client, FakeBedrock)
    assert called["kwargs"] == {"aws_profile": "softmax", "aws_region": "us-east-1"}
