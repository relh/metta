from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from metta.chatprop.config import ChatpropConfig

logger = logging.getLogger(__name__)


@dataclass
class TranscriptFile:
    path: Path
    session_id: str
    source: Literal["claude-code", "codex"]
    size_bytes: int
    matched_branches: list[str] = field(default_factory=list)


def _archive_root(config: ChatpropConfig) -> Path:
    return config.state_dir.expanduser() / "archive"


def _parse_archived_session_id(path: Path) -> str:
    stem = path.stem
    prefix, sep, suffix = stem.rpartition("-")
    if sep and suffix.isdigit() and prefix:
        return prefix
    return stem


def _scan_root(
    base_path: Path,
    source: Literal["claude-code", "codex"],
    archived: bool = False,
) -> list[TranscriptFile]:
    if not base_path.exists():
        return []

    files: list[TranscriptFile] = []
    for jsonl_file in base_path.rglob("*.jsonl"):
        try:
            stat = jsonl_file.stat()
        except OSError:
            continue
        session_id = _parse_archived_session_id(jsonl_file) if archived else jsonl_file.stem
        files.append(
            TranscriptFile(
                path=jsonl_file,
                session_id=session_id,
                source=source,
                size_bytes=stat.st_size,
            )
        )
    return files


def scan_archived(config: ChatpropConfig) -> list[TranscriptFile]:
    root = _archive_root(config) / "transcripts"
    results: list[TranscriptFile] = []
    results.extend(_scan_root(root / "claude-code", "claude-code", archived=True))
    results.extend(_scan_root(root / "codex", "codex", archived=True))
    return results


def scan_sources(config: ChatpropConfig) -> list[TranscriptFile]:
    results = []
    results.extend(_scan_root(config.sources.claude_code_path, "claude-code"))
    results.extend(_scan_root(config.sources.codex_path, "codex"))
    return results


def scan_all(config: ChatpropConfig) -> list[TranscriptFile]:
    deduped: dict[Path, TranscriptFile] = {}
    for tf in scan_archived(config) + scan_sources(config):
        deduped[tf.path.resolve()] = tf
    return list(deduped.values())


def _read_index(config: ChatpropConfig) -> dict[str, list[str]]:
    index_path = _archive_root(config) / "index.json"
    if not index_path.is_file():
        return {}
    try:
        payload = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    branches = payload.get("branches")
    if not isinstance(branches, dict):
        return {}

    parsed: dict[str, list[str]] = {}
    for branch, values in branches.items():
        if isinstance(branch, str) and isinstance(values, list):
            parsed[branch] = [value for value in values if isinstance(value, str)]
    return parsed


def _source_for_key(key: str) -> Literal["claude-code", "codex"]:
    if "/claude-code/" in key:
        return "claude-code"
    return "codex"


def _match_via_index(config: ChatpropConfig, branch_names: list[str]) -> dict[Path, TranscriptFile]:
    index = _read_index(config)
    archive_root = _archive_root(config)
    matches: dict[Path, TranscriptFile] = {}
    for branch in branch_names:
        for key in index.get(branch, []):
            candidate = (archive_root / key).resolve()
            if not candidate.is_file():
                continue
            tf = matches.get(candidate)
            if tf is None:
                try:
                    stat = candidate.stat()
                except OSError:
                    continue
                tf = TranscriptFile(
                    path=candidate,
                    session_id=_parse_archived_session_id(candidate),
                    source=_source_for_key(key),
                    size_bytes=stat.st_size,
                    matched_branches=[],
                )
                matches[candidate] = tf
            if branch not in tf.matched_branches:
                tf.matched_branches.append(branch)
    return matches


def find_transcripts_for_branches(
    config: ChatpropConfig,
    branch_names: list[str],
) -> list[TranscriptFile]:
    cleaned_branches = [name.strip() for name in branch_names if name and name.strip()]
    if not cleaned_branches:
        return []

    matches = _match_via_index(config, cleaned_branches)
    all_files = scan_all(config)
    for tf in all_files:
        path = tf.path.resolve()
        existing = matches.get(path)
        if existing is None:
            existing = TranscriptFile(
                path=tf.path,
                session_id=tf.session_id,
                source=tf.source,
                size_bytes=tf.size_bytes,
                matched_branches=[],
            )
            matches[path] = existing
        grep_matches = _grep_file_for_branches(tf.path, cleaned_branches)
        for branch in grep_matches:
            if branch not in existing.matched_branches:
                existing.matched_branches.append(branch)

    return [tf for tf in matches.values() if tf.matched_branches]


def _grep_file_for_branches(path: Path, branch_names: list[str]) -> list[str]:
    matched = []
    try:
        text = path.read_text(errors="replace")
        for branch in branch_names:
            if branch in text:
                matched.append(branch)
    except OSError:
        logger.warning("Could not read %s", path)
    return matched


def read_transcript(path: Path) -> str:
    lines = []
    with open(path, errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            msg_type = obj.get("type")
            if msg_type == "user":
                content = _extract_content(obj)
                if content:
                    lines.append(f"[USER]: {content}")
            elif msg_type == "assistant":
                content = _extract_content(obj)
                if content:
                    lines.append(f"[ASSISTANT]: {content}")
            elif msg_type == "event_msg":
                content = _extract_event_message(obj)
                if content:
                    lines.append(content)
            elif msg_type == "response_item":
                lines.extend(_extract_response_item_lines(obj))
            elif msg_type == "progress":
                data = obj.get("data", {})
                tool_name = data.get("toolName", "")
                tool_input = data.get("input", "")
                tool_output = data.get("output", "")
                if tool_name:
                    lines.append(f"[TOOL:{tool_name}]: input={_truncate(str(tool_input), 500)}")
                    if tool_output:
                        lines.append(f"[TOOL_RESULT]: {_truncate(str(tool_output), 500)}")
    return "\n".join(lines)


def _extract_content(obj: dict) -> str:
    msg = obj.get("message", obj)
    content = msg.get("content", "")
    if isinstance(content, list):
        return _extract_content_blocks(content)
    return str(content)


def _truncate(s: str, max_len: int) -> str:
    return s[:max_len] + "..." if len(s) > max_len else s


def _extract_content_blocks(content: list[dict]) -> str:
    parts = []
    for block in content:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        if block_type in {"text", "input_text", "output_text", "summary_text"}:
            text = block.get("text", "")
            if text:
                parts.append(text)
    return " ".join(parts)


def _extract_event_message(obj: dict) -> str:
    payload = obj.get("payload", {})
    event_type = payload.get("type")
    if event_type == "user_message":
        message = payload.get("message", "")
        return f"[USER]: {message}" if message else ""
    if event_type == "agent_message":
        message = payload.get("message", "")
        return f"[ASSISTANT]: {message}" if message else ""
    return ""


def _extract_response_item_lines(obj: dict) -> list[str]:
    payload = obj.get("payload", {})
    response_type = payload.get("type")
    if response_type == "message":
        role = payload.get("role")
        content = payload.get("content", [])
        text = _extract_content_blocks(content) if isinstance(content, list) else ""
        if not text:
            return []
        if role == "user":
            return [f"[USER]: {text}"]
        if role == "assistant":
            return [f"[ASSISTANT]: {text}"]
        return []
    if response_type in {"function_call", "custom_tool_call"}:
        tool_name = payload.get("name", "")
        tool_input = payload.get("arguments", payload.get("input", ""))
        if tool_name:
            return [f"[TOOL:{tool_name}]: input={_truncate(str(tool_input), 500)}"]
        return []
    if response_type in {"function_call_output", "custom_tool_call_output"}:
        tool_output = payload.get("output", "")
        if tool_output:
            return [f"[TOOL_RESULT]: {_truncate(str(tool_output), 500)}"]
    return []
