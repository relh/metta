"""Transcript indexing helpers for branch -> transcript lookup."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from metta.chatprop.local.models import BranchIndex, utc_now_iso

MAIN_LIKE_BRANCHES = {"main", "master", "head"}


@dataclass(frozen=True)
class BranchSegment:
    branch: str
    started_at: str | None
    ended_at: str | None


def _iter_branch_fields(obj: Any):
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in {"gitBranch", "git_branch"} and isinstance(value, str):
                yield value
            if key == "git" and isinstance(value, dict):
                branch = value.get("branch")
                if isinstance(branch, str):
                    yield branch
            yield from _iter_branch_fields(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from _iter_branch_fields(item)


def _normalize_branch_name(branch: str) -> str:
    cleaned = branch.strip()
    if not cleaned:
        return ""
    lowered = cleaned.lower()
    if lowered in MAIN_LIKE_BRANCHES:
        return "main"
    return cleaned


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def extract_branch_segments_from_transcript(path: Path) -> list[BranchSegment]:
    if not path.is_file():
        return []

    segments: list[BranchSegment] = []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue

            timestamp_raw = payload.get("timestamp")
            timestamp = timestamp_raw if isinstance(timestamp_raw, str) and timestamp_raw.strip() else None

            branches = [_normalize_branch_name(branch) for branch in _iter_branch_fields(payload)]
            for branch in branches:
                if not branch:
                    continue
                if not segments or segments[-1].branch != branch:
                    segments.append(BranchSegment(branch=branch, started_at=timestamp, ended_at=timestamp))
                    continue
                last = segments[-1]
                segments[-1] = BranchSegment(
                    branch=last.branch,
                    started_at=last.started_at,
                    ended_at=timestamp or last.ended_at,
                )
    return segments


def extract_work_branches_from_segments(segments: list[BranchSegment]) -> list[str]:
    sequence = [segment.branch for segment in segments if segment.branch]
    if not sequence:
        return []

    non_main = [branch for branch in sequence if branch != "main"]
    if non_main:
        return _dedupe_preserve_order(non_main)
    return ["main"]


def extract_work_branches_from_transcript(path: Path) -> list[str]:
    return extract_work_branches_from_segments(extract_branch_segments_from_transcript(path))


def extract_branches_from_transcript(path: Path) -> set[str]:
    return set(extract_work_branches_from_transcript(path))


def add_transcript_to_index(index: BranchIndex, transcript_key: str, branches: set[str]) -> BranchIndex:
    updated = {branch: list(keys) for branch, keys in index.branches.items()}
    for branch in sorted(branches):
        keys = updated.setdefault(branch, [])
        if transcript_key not in keys:
            keys.append(transcript_key)
    return BranchIndex(updated_at=utc_now_iso(), branches=updated)
