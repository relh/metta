"""Shared models for chatprop collection and indexing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

TranscriptSource = Literal["claude-code", "codex"]


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class TranscriptMetadata:
    session_id: str
    source: TranscriptSource
    started_at: str
    ended_at: str
    transcript_path: str
    size_bytes: int

    def to_dict(self) -> dict[str, str | int]:
        return {
            "session_id": self.session_id,
            "source": self.source,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "transcript_path": self.transcript_path,
            "size_bytes": self.size_bytes,
        }


@dataclass(frozen=True)
class ManifestEntry:
    source: TranscriptSource
    transcript_path: str
    mtime_ns: int
    size_bytes: int
    uploaded_at: str
    transcript_path_key: str

    def to_dict(self) -> dict[str, str | int]:
        return {
            "source": self.source,
            "transcript_path": self.transcript_path,
            "mtime_ns": self.mtime_ns,
            "size_bytes": self.size_bytes,
            "uploaded_at": self.uploaded_at,
            "transcript_path_key": self.transcript_path_key,
        }


@dataclass(frozen=True)
class BranchIndex:
    updated_at: str
    branches: dict[str, list[str]]

    def to_dict(self) -> dict[str, object]:
        return {"updated_at": self.updated_at, "branches": self.branches}
