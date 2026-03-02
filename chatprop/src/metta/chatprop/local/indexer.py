"""Transcript indexing helpers for branch -> transcript lookup."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from metta.chatprop.local.models import BranchIndex, utc_now_iso

MAIN_LIKE_BRANCHES = {"main", "master", "head"}
_BRANCH_TOKEN = r"[A-Za-z0-9._/\-]+"
_CHECKOUT_PATTERN = re.compile(rf"\bgit\s+(?:checkout|switch)(?:\s+-[cbCB]\s+|\s+)(?P<branch>{_BRANCH_TOKEN})")
_GT_CREATE_PATTERN = re.compile(rf"\bgt\s+(?:create|checkout)\s+(?P<branch>{_BRANCH_TOKEN})")
_GIT_STATUS_PATTERN = re.compile(r"##\s+(?P<branch>[A-Za-z0-9._/\-]+?)(?:\.\.\.|$)")
_SWITCHED_PATTERN = re.compile(rf"Switched to branch ['\"](?P<branch>{_BRANCH_TOKEN})['\"]")
_ON_BRANCH_PATTERN = re.compile(rf"\bOn branch (?P<branch>{_BRANCH_TOKEN})\b")


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


def _iter_command_like_text(obj: Any, parent_key: str = ""):
    if isinstance(obj, dict):
        for key, value in obj.items():
            key_lower = key.lower()
            if isinstance(value, str) and key_lower in {
                "arguments",
                "command",
                "output",
                "stdout",
                "stderr",
                "message",
                "content",
                "input",
            }:
                yield value
            elif isinstance(value, list) and key_lower in {"command"}:
                command_text = " ".join(str(item) for item in value if isinstance(item, str))
                if command_text:
                    yield command_text
            yield from _iter_command_like_text(value, key_lower)
    elif isinstance(obj, list):
        for item in obj:
            yield from _iter_command_like_text(item, parent_key)
    elif isinstance(obj, str) and parent_key in {"arguments", "input"}:
        yield obj


def _extract_branches_from_text(text: str) -> list[str]:
    lowered = text.lower()
    if not any(token in lowered for token in ("git", "branch", "## ", "gt create", "gt checkout")):
        return []

    candidates: list[str] = []
    for pattern in (_CHECKOUT_PATTERN, _GT_CREATE_PATTERN, _GIT_STATUS_PATTERN, _SWITCHED_PATTERN, _ON_BRANCH_PATTERN):
        for match in pattern.finditer(text):
            branch = match.group("branch")
            if branch:
                candidates.append(branch)
    return candidates


def _extract_branches_from_payload(payload: Any) -> list[str]:
    extracted: list[str] = []
    for text in _iter_command_like_text(payload):
        extracted.extend(_extract_branches_from_text(text))
        if text.startswith("{") and text.endswith("}"):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                continue
            extracted.extend(_extract_branches_from_payload(parsed))
    return extracted


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
            branches.extend(_normalize_branch_name(branch) for branch in _extract_branches_from_payload(payload))
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
