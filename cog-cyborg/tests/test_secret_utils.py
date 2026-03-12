from __future__ import annotations

from pathlib import Path

from cog_cyborg.secret_utils import resolve_api_key


def test_resolve_api_key_prefers_direct_value(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "env-key")
    key_file = tmp_path / "openai.key"
    key_file.write_text("file-key")

    value = resolve_api_key(
        direct_value="direct-key",
        file_path=key_file,
        env_var="OPENAI_API_KEY",
    )
    assert value == "direct-key"


def test_resolve_api_key_uses_file_before_env(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "env-key")
    key_file = tmp_path / "anthropic.key"
    key_file.write_text("file-key\n")

    value = resolve_api_key(
        direct_value=None,
        file_path=key_file,
        env_var="ANTHROPIC_API_KEY",
    )
    assert value == "file-key"


def test_resolve_api_key_ignores_blank_direct_value(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "env-key")
    key_file = tmp_path / "anthropic.key"
    key_file.write_text("file-key\n")

    value = resolve_api_key(
        direct_value="   ",
        file_path=key_file,
        env_var="ANTHROPIC_API_KEY",
    )
    assert value == "file-key"


def test_resolve_api_key_falls_back_to_env_when_file_missing(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "env-key")

    value = resolve_api_key(
        direct_value=None,
        file_path=tmp_path / "missing.key",
        env_var="ANTHROPIC_API_KEY",
    )
    assert value == "env-key"


def test_resolve_api_key_returns_none_when_missing(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    value = resolve_api_key(
        direct_value=None,
        file_path=None,
        env_var="OPENAI_API_KEY",
    )

    assert value is None
