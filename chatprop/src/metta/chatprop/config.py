from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

DEFAULT_CLAUDE_CODE_PATH = Path.home() / ".claude" / "projects"
DEFAULT_CODEX_PATH = Path.home() / ".codex" / "sessions"


class SourcesConfig(BaseModel):
    claude_code_path: Path = DEFAULT_CLAUDE_CODE_PATH
    codex_path: Path = DEFAULT_CODEX_PATH


class ChatpropConfig(BaseModel):
    sources: SourcesConfig = SourcesConfig()


def load_config() -> ChatpropConfig:
    return ChatpropConfig()
