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


def scan_claude_code(base_path: Path) -> list[TranscriptFile]:
    if not base_path.exists():
        return []
    results = []
    for jsonl_file in base_path.rglob("*.jsonl"):
        stat = jsonl_file.stat()
        results.append(
            TranscriptFile(
                path=jsonl_file,
                session_id=jsonl_file.stem,
                source="claude-code",
                size_bytes=stat.st_size,
            )
        )
    return results


def scan_codex(base_path: Path) -> list[TranscriptFile]:
    if not base_path.exists():
        return []
    results = []
    for jsonl_file in base_path.rglob("*.jsonl"):
        stat = jsonl_file.stat()
        results.append(
            TranscriptFile(
                path=jsonl_file,
                session_id=jsonl_file.stem,
                source="codex",
                size_bytes=stat.st_size,
            )
        )
    return results


def scan_all(config: ChatpropConfig) -> list[TranscriptFile]:
    results = []
    results.extend(scan_claude_code(config.sources.claude_code_path))
    results.extend(scan_codex(config.sources.codex_path))
    return results


def find_transcripts_for_branches(
    config: ChatpropConfig,
    branch_names: list[str],
) -> list[TranscriptFile]:
    all_files = scan_all(config)
    matches = []
    for tf in all_files:
        matched = _grep_file_for_branches(tf.path, branch_names)
        if matched:
            tf.matched_branches = matched
            matches.append(tf)
    return matches


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
