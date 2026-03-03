from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SourceConfig:
    path: Path


@dataclass(frozen=True)
class DaemonConfig:
    poll_interval_seconds: int
    inactivity_threshold_seconds: int


@dataclass(frozen=True)
class ChatpropConfig:
    claude_code: SourceConfig
    codex: SourceConfig
    daemon: DaemonConfig
    state_dir: Path


ChatPropConfig = ChatpropConfig


def default_state_dir() -> Path:
    return Path.home() / ".chatprop"


def default_config_path() -> Path:
    return default_state_dir() / "config.toml"


def _read_toml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        with path.open("rb") as handle:
            parsed = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    if isinstance(parsed, dict):
        return parsed
    return {}


def _read_dict(parent: dict[str, Any], key: str) -> dict[str, Any]:
    value = parent.get(key)
    if isinstance(value, dict):
        return value
    return {}


def _read_str(parent: dict[str, Any], key: str, default: str) -> str:
    value = parent.get(key)
    if isinstance(value, str) and value.strip():
        return value
    return default


def _read_int(parent: dict[str, Any], key: str, default: int, minimum: int) -> int:
    value = parent.get(key)
    if isinstance(value, int):
        return max(minimum, value)
    return default


def load_config(path: Path | None = None) -> ChatpropConfig:
    resolved_path = (path or default_config_path()).expanduser()
    raw = _read_toml(resolved_path)

    sources_raw = _read_dict(raw, "sources")
    claude_raw = _read_dict(sources_raw, "claude-code")
    codex_raw = _read_dict(sources_raw, "codex")
    daemon_raw = _read_dict(raw, "daemon")
    state_raw = _read_dict(raw, "state")

    return ChatpropConfig(
        claude_code=SourceConfig(path=Path(_read_str(claude_raw, "path", "~/.claude/projects")).expanduser()),
        codex=SourceConfig(path=Path(_read_str(codex_raw, "path", "~/.codex/sessions")).expanduser()),
        daemon=DaemonConfig(
            poll_interval_seconds=_read_int(daemon_raw, "poll_interval_seconds", default=30, minimum=1),
            inactivity_threshold_seconds=_read_int(daemon_raw, "inactivity_threshold_seconds", default=60, minimum=0),
        ),
        state_dir=Path(_read_str(state_raw, "dir", str(default_state_dir()))).expanduser(),
    )
