"""Workflow inference for session feature chunks and skill graph extraction."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from metta.chatprop.local.indexer import BranchSegment

_MAX_EVENT_TEXT_CHARS = 4000
_MAX_NODE_EXAMPLES = 3
_MAX_PAIR_EXAMPLES = 5
_MAX_ARGUMENT_SAMPLES = 8

_REVISION_CUE = re.compile(
    r"\b("
    r"fix|address|adjust|revise|revision|update|change|cleanup|polish|follow[- ]?up|"
    r"review comment|feedback|ci|failing|failure|bug|regression|edge case|nit"
    r")\b",
    re.IGNORECASE,
)
_NEGATED_DONE = re.compile(
    r"\b("
    r"not done|not complete|incomplete|remaining|todo|to do|still need|needs more|"
    r"can't finish|cannot finish|won't finish"
    r")\b",
    re.IGNORECASE,
)
_DONE_CUES = [
    re.compile(r"\b(done|completed?|finished)\b", re.IGNORECASE),
    re.compile(r"\ball set\b", re.IGNORECASE),
    re.compile(r"\bready (?:for review|to merge|for merge)\b", re.IGNORECASE),
    re.compile(r"\b(pr|pull request) (?:is )?(?:up|open|ready|created|submitted)\b", re.IGNORECASE),
    re.compile(r"\b(pushed|submitted|committed)\b", re.IGNORECASE),
    re.compile(r"\bimplemented\b", re.IGNORECASE),
]

_IMPLICIT_VERB_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("fix", re.compile(r"\b(fix|debug|triage|repair|resolve|address)\b", re.IGNORECASE)),
    ("cleanup", re.compile(r"\b(clean ?up|simplify|refactor|remove|prune)\b", re.IGNORECASE)),
    ("implement", re.compile(r"\b(add|implement|create|build|introduce)\b", re.IGNORECASE)),
    ("analyze", re.compile(r"\b(analy[sz]e|investigate|review|audit|inspect)\b", re.IGNORECASE)),
    ("test", re.compile(r"\b(test|verify|check|lint|pytest|ci)\b", re.IGNORECASE)),
    ("sync", re.compile(r"\b(sync|merge|rebase|restack|cherry-pick)\b", re.IGNORECASE)),
    ("submit", re.compile(r"\b(submit|push|commit|open pr|create pr)\b", re.IGNORECASE)),
    ("document", re.compile(r"\b(explain|summari[sz]e|document|write up|docs?)\b", re.IGNORECASE)),
]

_ARG_STOP_WORDS = {
    "a",
    "an",
    "the",
    "this",
    "that",
    "these",
    "those",
    "our",
    "my",
    "your",
    "to",
    "for",
    "on",
    "in",
    "with",
    "please",
    "just",
}


@dataclass(frozen=True)
class _Event:
    order: int
    timestamp: datetime | None
    timestamp_raw: str | None
    role: Literal["user", "assistant", "tool", "system"]
    text: str


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _extract_text_parts(value: Any) -> list[str]:
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, dict):
                for key in ("text", "content", "message", "thinking"):
                    if key in item:
                        parts.extend(_extract_text_parts(item[key]))
            elif isinstance(item, str):
                stripped = item.strip()
                if stripped:
                    parts.append(stripped)
        return parts
    if isinstance(value, dict):
        parts: list[str] = []
        for key in ("text", "content", "message", "output", "input"):
            if key in value:
                parts.extend(_extract_text_parts(value[key]))
        return parts
    return []


def _collapse_text(parts: list[str]) -> str:
    joined = " ".join(part for part in parts if part)
    compact = re.sub(r"\s+", " ", joined).strip()
    if len(compact) <= _MAX_EVENT_TEXT_CHARS:
        return compact
    return compact[:_MAX_EVENT_TEXT_CHARS] + "..."


def _extract_event_from_payload(obj: dict[str, Any], order: int) -> list[_Event]:
    timestamp_raw = obj.get("timestamp")
    timestamp_text = timestamp_raw if isinstance(timestamp_raw, str) else None
    timestamp = _parse_datetime(timestamp_text)
    msg_type = obj.get("type")
    events: list[_Event] = []

    if msg_type == "user":
        text = _collapse_text(_extract_text_parts(obj.get("message", obj)))
        if text:
            events.append(
                _Event(
                    order=order,
                    timestamp=timestamp,
                    timestamp_raw=timestamp_text,
                    role="user",
                    text=text,
                )
            )
        return events
    if msg_type == "assistant":
        text = _collapse_text(_extract_text_parts(obj.get("message", obj)))
        if text:
            events.append(
                _Event(order=order, timestamp=timestamp, timestamp_raw=timestamp_text, role="assistant", text=text)
            )
        return events
    if msg_type == "event_msg":
        payload = obj.get("payload")
        if not isinstance(payload, dict):
            return events
        event_kind = payload.get("type")
        if event_kind == "user_message":
            text = _collapse_text(_extract_text_parts(payload.get("message")))
            if text:
                events.append(
                    _Event(order=order, timestamp=timestamp, timestamp_raw=timestamp_text, role="user", text=text)
                )
        elif event_kind == "agent_message":
            text = _collapse_text(_extract_text_parts(payload.get("message")))
            if text:
                events.append(
                    _Event(order=order, timestamp=timestamp, timestamp_raw=timestamp_text, role="assistant", text=text)
                )
        return events
    if msg_type == "response_item":
        payload = obj.get("payload")
        if not isinstance(payload, dict):
            return events
        response_type = payload.get("type")
        if response_type == "message":
            role = payload.get("role")
            if role in {"user", "assistant"}:
                text = _collapse_text(_extract_text_parts(payload.get("content")))
                if text:
                    events.append(
                        _Event(
                            order=order,
                            timestamp=timestamp,
                            timestamp_raw=timestamp_text,
                            role=role,
                            text=text,
                        )
                    )
            return events
        if response_type in {"function_call", "custom_tool_call"}:
            name = payload.get("name")
            args = payload.get("arguments", payload.get("input"))
            text = _collapse_text(_extract_text_parts([name, args]))
            if text:
                events.append(
                    _Event(
                        order=order,
                        timestamp=timestamp,
                        timestamp_raw=timestamp_text,
                        role="tool",
                        text=text,
                    )
                )
            return events
        if response_type in {"function_call_output", "custom_tool_call_output"}:
            text = _collapse_text(_extract_text_parts(payload.get("output")))
            if text:
                events.append(
                    _Event(
                        order=order,
                        timestamp=timestamp,
                        timestamp_raw=timestamp_text,
                        role="tool",
                        text=text,
                    )
                )
            return events
        return events
    if msg_type == "progress":
        data = obj.get("data")
        if isinstance(data, dict):
            text = _collapse_text(
                _extract_text_parts(
                    [
                        data.get("type"),
                        data.get("command"),
                        data.get("input"),
                        data.get("output"),
                        data.get("stdout"),
                    ]
                )
            )
            if text:
                events.append(
                    _Event(
                        order=order,
                        timestamp=timestamp,
                        timestamp_raw=timestamp_text,
                        role="tool",
                        text=text,
                    )
                )
        return events
    return events


def extract_transcript_events(path: Path) -> list[_Event]:
    events: list[_Event] = []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for order, raw_line in enumerate(handle):
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            events.extend(_extract_event_from_payload(payload, order))
    return events


def build_feature_chunks_from_segments(segments: list[BranchSegment]) -> list[dict[str, Any]]:
    if not segments:
        return []

    non_main_present = any(segment.branch != "main" for segment in segments)
    if not non_main_present:
        return [
            {
                "branch": "main",
                "started_at": segments[0].started_at,
                "ended_at": segments[-1].ended_at,
            }
        ]

    chunks: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    prelude_start: str | None = None

    for segment in segments:
        branch = segment.branch
        if branch == "main":
            if current is not None:
                current["ended_at"] = segment.ended_at or current["ended_at"]
            elif prelude_start is None:
                prelude_start = segment.started_at
            continue

        if current is None:
            current = {
                "branch": branch,
                "started_at": prelude_start or segment.started_at,
                "ended_at": segment.ended_at,
            }
            prelude_start = None
            continue

        if current["branch"] == branch:
            current["ended_at"] = segment.ended_at or current["ended_at"]
            continue

        chunks.append(current)
        current = {
            "branch": branch,
            "started_at": segment.started_at,
            "ended_at": segment.ended_at,
        }

    if current is not None:
        chunks.append(current)

    return chunks


def _event_in_window(event: _Event, *, start: datetime | None, end: datetime | None) -> bool:
    if event.timestamp is None:
        return start is None and end is None
    if start is not None and event.timestamp < start:
        return False
    if end is not None and event.timestamp > end:
        return False
    return True


def _looks_done(text: str) -> bool:
    lowered = text.lower()
    if _NEGATED_DONE.search(lowered):
        return False
    return any(pattern.search(text) for pattern in _DONE_CUES)


def _looks_like_revision_request(text: str) -> bool:
    return bool(_REVISION_CUE.search(text))


def _classify_user_request(text: str) -> Literal["feature", "revision"]:
    if _looks_like_revision_request(text):
        return "revision"
    return "feature"


def _classify_target(text: str) -> str:
    lowered = text.lower()
    if re.search(r"\b(branch|pr|graphite|stack|merge|rebase)\b", lowered):
        return "branch"
    if re.search(r"\b(test|pytest|ci|lint|failing|failure)\b", lowered):
        return "quality"
    if re.search(r"\b(skill|claude\.md|agents\.md|instruction|prompt)\b", lowered):
        return "skills"
    if "/" in text or re.search(r"\b\w+\.(py|ts|tsx|js|md|toml|yml|yaml)\b", text):
        return "codepath"
    return "general"


def _clean_argument_phrase(raw: str, *, fallback: str) -> str:
    compact = re.sub(r"\s+", " ", raw).strip(" -:,.")
    if not compact:
        return fallback

    compact = re.sub(r"^(?:please|can you|could you|would you|help me)\s+", "", compact, flags=re.IGNORECASE)
    compact = re.split(r"\b(?:and|then|also|but)\b", compact, maxsplit=1, flags=re.IGNORECASE)[0]
    tokens = [token for token in compact.split(" ") if token]
    while tokens and tokens[0].lower() in _ARG_STOP_WORDS:
        tokens.pop(0)
    compact = " ".join(tokens).strip(" -:,.")
    if not compact:
        return fallback
    if len(compact) > 80:
        compact = compact[:80].rstrip() + "..."
    return compact


def _extract_argument_phrase(text: str, match: re.Match[str], *, fallback: str) -> str:
    tail = text[match.end() :]
    if not tail.strip():
        return fallback
    cutoff = re.search(r"[.!?\n]", tail)
    if cutoff:
        tail = tail[: cutoff.start()]
    return _clean_argument_phrase(tail, fallback=fallback)


def _infer_implicit_skill(text: str) -> tuple[str, str, str]:
    for verb, pattern in _IMPLICIT_VERB_PATTERNS:
        match = pattern.search(text)
        if match:
            target = _classify_target(text)
            fallback = target
            argument = _extract_argument_phrase(text, match, fallback=fallback)
            skill_id = f"implicit_fn:{verb}"
            return skill_id, f"{verb}(x)", argument
    target = _classify_target(text)
    return "implicit_fn:request", "request(x)", target


def load_explicit_skills(repo_root: Path) -> list[str]:
    skill_root = repo_root / "skills"
    if not skill_root.is_dir():
        return []
    names = sorted(
        {
            skill_dir.name
            for skill_dir in skill_root.iterdir()
            if skill_dir.is_dir() and (skill_dir / "SKILL.md").is_file()
        }
    )
    return names


def _skill_name_pattern(skill_name: str) -> re.Pattern[str]:
    lowered = skill_name.lower()
    normalized = re.escape(lowered).replace(r"\-", r"[-_ ]").replace(r"\.", r"[._ ]")
    return re.compile(rf"(?<!\w)(?:\${normalized}|{normalized})(?!\w)", re.IGNORECASE)


def _explicit_skill_refs(
    text: str,
    explicit_skills: list[str],
    compiled_patterns: dict[str, re.Pattern[str]],
) -> list[str]:
    refs: list[str] = []
    lowered = text.lower()
    for skill in explicit_skills:
        pattern = compiled_patterns[skill]
        if pattern.search(lowered):
            refs.append(f"explicit:{skill}")
    return refs


def analyze_session_feature_chunks(
    *,
    transcript_path: Path,
    branch_segments: list[BranchSegment],
    explicit_skills: list[str],
) -> list[dict[str, Any]]:
    chunks = build_feature_chunks_from_segments(branch_segments)
    if not chunks:
        return []

    events = extract_transcript_events(transcript_path)
    explicit_patterns = {skill: _skill_name_pattern(skill) for skill in explicit_skills}
    analyzed: list[dict[str, Any]] = []

    for chunk in chunks:
        start = _parse_datetime(chunk.get("started_at"))
        end = _parse_datetime(chunk.get("ended_at"))
        chunk_events = [event for event in events if _event_in_window(event, start=start, end=end)]

        chunk_users = [event for event in chunk_events if event.role == "user"]
        done_orders = [event.order for event in chunk_events if event.role == "assistant" and _looks_done(event.text)]
        first_revision_user = next(
            (
                event
                for event in chunk_users
                if _classify_user_request(event.text) == "revision"
                and any(done_order < event.order for done_order in done_orders)
            ),
            None,
        )
        if first_revision_user is None:
            assistant_orders = [event.order for event in chunk_events if event.role == "assistant"]
            first_revision_user = next(
                (
                    event
                    for event in chunk_users
                    if _classify_user_request(event.text) == "revision"
                    and any(assistant_order < event.order for assistant_order in assistant_orders)
                ),
                None,
            )
        feature_users = [
            event for event in chunk_users if first_revision_user is None or event.order < first_revision_user.order
        ]
        revision_users = [
            event
            for event in chunk_users
            if first_revision_user is not None
            and event.order >= first_revision_user.order
            and _classify_user_request(event.text) == "revision"
        ]

        last_feature_order = max((event.order for event in feature_users), default=-1)
        completion_candidates = []
        for event in chunk_events:
            if event.role != "assistant":
                continue
            if not _looks_done(event.text):
                continue
            if event.order <= last_feature_order:
                continue
            if first_revision_user is not None and event.order >= first_revision_user.order:
                continue
            completion_candidates.append(event)

        believed_done_event: _Event | None = None
        first_revision_event: _Event | None = None
        believed_done_inferred = False
        for candidate in completion_candidates:
            revision_candidate = next(
                (
                    user
                    for user in revision_users
                    if user.order > candidate.order and _looks_like_revision_request(user.text)
                ),
                None,
            )
            if revision_candidate is not None:
                believed_done_event = candidate
                first_revision_event = revision_candidate
                break
        if believed_done_event is None and completion_candidates:
            believed_done_event = completion_candidates[0]
        if first_revision_event is None:
            first_revision_event = first_revision_user

        if believed_done_event is None and first_revision_user is not None:
            believed_done_inferred = True
            inferred_order = first_revision_user.order - 1
            planning_events = [event for event in chunk_events if event.order <= inferred_order]
            revision_events = [event for event in chunk_events if event.order >= first_revision_user.order]
            believed_done_at = first_revision_user.timestamp_raw
        elif believed_done_event is None:
            planning_events = chunk_events
            revision_events = []
            believed_done_at = None
        else:
            planning_events = [event for event in chunk_events if event.order <= believed_done_event.order]
            revision_events = [event for event in chunk_events if event.order > believed_done_event.order]
            believed_done_at = believed_done_event.timestamp_raw

        revision_events = list(revision_events)

        planning_user_events = [event for event in planning_events if event.role == "user"]
        revision_user_events = [event for event in revision_events if event.role == "user"]

        planning_skills: list[str] = []
        revision_skills: list[str] = []
        planning_invocations: list[dict[str, str]] = []
        revision_invocations: list[dict[str, str]] = []
        explicit_refs: set[str] = set()
        implicit_labels: dict[str, str] = {}

        for event in planning_user_events:
            skill_id, label, argument = _infer_implicit_skill(event.text)
            planning_skills.append(skill_id)
            planning_invocations.append(
                {
                    "skill_id": skill_id,
                    "argument": argument,
                    "invocation": f"{label.replace('(x)', '')}({argument})",
                }
            )
            implicit_labels[skill_id] = label
            explicit_refs.update(_explicit_skill_refs(event.text, explicit_skills, explicit_patterns))

        for event in revision_user_events:
            skill_id, label, argument = _infer_implicit_skill(event.text)
            revision_skills.append(skill_id)
            revision_invocations.append(
                {
                    "skill_id": skill_id,
                    "argument": argument,
                    "invocation": f"{label.replace('(x)', '')}({argument})",
                }
            )
            implicit_labels[skill_id] = label
            explicit_refs.update(_explicit_skill_refs(event.text, explicit_skills, explicit_patterns))

        analyzed_chunk = {
            "branch": chunk["branch"],
            "started_at": chunk["started_at"],
            "ended_at": chunk["ended_at"],
            "believed_done_at": believed_done_at,
            "believed_done_inferred": believed_done_inferred,
            "feature_request_count": len(feature_users),
            "revision_request_count": len(revision_users),
            "phase_a": {
                "name": "planning_doing",
                "started_at": chunk["started_at"],
                "ended_at": believed_done_at if believed_done_at else chunk["ended_at"],
                "event_count": len(planning_events),
                "user_message_count": len(planning_user_events),
                "skills": planning_skills,
                "implicit_invocations": planning_invocations,
            },
            "phase_b": {
                "name": "revising",
                "started_at": believed_done_at,
                "ended_at": chunk["ended_at"],
                "event_count": len(revision_events),
                "user_message_count": len(revision_user_events),
                "skills": revision_skills,
                "implicit_invocations": revision_invocations,
                "first_revision_user_at": first_revision_event.timestamp_raw if first_revision_event else None,
            },
            "has_revision": bool(revision_events),
            "explicit_skill_refs": sorted(explicit_refs),
            "implicit_skill_labels": implicit_labels,
        }
        analyzed.append(analyzed_chunk)

    return analyzed


class SkillGraphAccumulator:
    def __init__(self, explicit_skills: list[str]) -> None:
        self._nodes: dict[str, dict[str, Any]] = {}
        self._edges: dict[tuple[str, str, str], int] = defaultdict(int)
        self._revision_pairs: dict[tuple[str, str], dict[str, Any]] = {}
        self._total_implicit_uses = 0
        for skill in explicit_skills:
            node_id = f"explicit:{skill}"
            self._nodes[node_id] = {
                "id": node_id,
                "label": skill,
                "kind": "explicit",
                "count": 0,
                "examples": [],
            }

    def _ensure_implicit_node(self, skill_id: str, label: str) -> dict[str, Any]:
        node = self._nodes.get(skill_id)
        if node is None:
            node = {
                "id": skill_id,
                "label": label,
                "kind": "implicit",
                "count": 0,
                "examples": [],
            }
            self._nodes[skill_id] = node
        return node

    def _record_node_use(self, skill_id: str, *, label: str, example: str | None, argument: str | None = None) -> None:
        if skill_id.startswith("implicit_"):
            node = self._ensure_implicit_node(skill_id, label)
            self._total_implicit_uses += 1
        else:
            node = self._nodes.setdefault(
                skill_id,
                {
                    "id": skill_id,
                    "label": skill_id.split(":", 1)[-1],
                    "kind": "explicit",
                    "count": 0,
                    "examples": [],
                },
            )
        node["count"] = int(node["count"]) + 1
        if example and len(node["examples"]) < _MAX_NODE_EXAMPLES and example not in node["examples"]:
            node["examples"].append(example)
        if argument:
            samples = node.setdefault("argument_samples", [])
            if isinstance(samples, list) and len(samples) < _MAX_ARGUMENT_SAMPLES and argument not in samples:
                samples.append(argument)

    def _record_edge(self, source: str, target: str, *, phase: str) -> None:
        if not source or not target:
            return
        self._edges[(source, target, phase)] += 1

    def add_feature_chunk(
        self,
        *,
        session_id: str,
        repo: str | None,
        chunk: dict[str, Any],
        include_revision_prevention: bool = True,
    ) -> None:
        labels = chunk.get("implicit_skill_labels", {})
        if not isinstance(labels, dict):
            labels = {}

        phase_a = chunk.get("phase_a", {})
        phase_b = chunk.get("phase_b", {})
        planning_skills = phase_a.get("skills", []) if isinstance(phase_a, dict) else []
        revision_skills = phase_b.get("skills", []) if isinstance(phase_b, dict) else []
        planning_invocations = phase_a.get("implicit_invocations", []) if isinstance(phase_a, dict) else []
        revision_invocations = phase_b.get("implicit_invocations", []) if isinstance(phase_b, dict) else []
        explicit_refs = chunk.get("explicit_skill_refs", [])
        if not isinstance(planning_skills, list):
            planning_skills = []
        if not isinstance(revision_skills, list):
            revision_skills = []
        if not isinstance(planning_invocations, list):
            planning_invocations = []
        if not isinstance(revision_invocations, list):
            revision_invocations = []
        if not isinstance(explicit_refs, list):
            explicit_refs = []

        for invocation in planning_invocations:
            if not isinstance(invocation, dict):
                continue
            skill_id = invocation.get("skill_id")
            if not isinstance(skill_id, str):
                continue
            label = labels.get(skill_id) if isinstance(labels.get(skill_id), str) else skill_id
            argument = invocation.get("argument")
            self._record_node_use(
                skill_id,
                label=label,
                example=f"{session_id}:{chunk.get('branch')}",
                argument=argument if isinstance(argument, str) else None,
            )
        for invocation in revision_invocations:
            if not isinstance(invocation, dict):
                continue
            skill_id = invocation.get("skill_id")
            if not isinstance(skill_id, str):
                continue
            label = labels.get(skill_id) if isinstance(labels.get(skill_id), str) else skill_id
            argument = invocation.get("argument")
            self._record_node_use(
                skill_id,
                label=label,
                example=f"{session_id}:{chunk.get('branch')}",
                argument=argument if isinstance(argument, str) else None,
            )
        for skill_id in planning_skills:
            if not isinstance(skill_id, str):
                continue
            if any(
                isinstance(invocation, dict) and invocation.get("skill_id") == skill_id
                for invocation in planning_invocations
            ):
                continue
            label = labels.get(skill_id) if isinstance(labels.get(skill_id), str) else skill_id
            self._record_node_use(skill_id, label=label, example=f"{session_id}:{chunk.get('branch')}")
        for skill_id in revision_skills:
            if not isinstance(skill_id, str):
                continue
            if any(
                isinstance(invocation, dict) and invocation.get("skill_id") == skill_id
                for invocation in revision_invocations
            ):
                continue
            label = labels.get(skill_id) if isinstance(labels.get(skill_id), str) else skill_id
            self._record_node_use(skill_id, label=label, example=f"{session_id}:{chunk.get('branch')}")
        for skill_id in explicit_refs:
            if not isinstance(skill_id, str):
                continue
            self._record_node_use(
                skill_id,
                label=skill_id.split(":", 1)[-1],
                example=f"{session_id}:{chunk.get('branch')}",
            )

        for source, target in zip(planning_skills, planning_skills[1:], strict=False):
            if isinstance(source, str) and isinstance(target, str):
                self._record_edge(source, target, phase="planning")
        for source, target in zip(revision_skills, revision_skills[1:], strict=False):
            if isinstance(source, str) and isinstance(target, str):
                self._record_edge(source, target, phase="revision")

        for implicit_skill in planning_skills + revision_skills:
            if not isinstance(implicit_skill, str):
                continue
            for explicit_skill in explicit_refs:
                if isinstance(explicit_skill, str):
                    self._record_edge(implicit_skill, explicit_skill, phase="explicit_ref")

        if planning_skills and revision_skills:
            first_revision = revision_skills[0]
            last_planning = planning_skills[-1]
            if isinstance(first_revision, str) and isinstance(last_planning, str):
                self._record_edge(last_planning, first_revision, phase="handoff")
                if not include_revision_prevention:
                    return
                key = (last_planning, first_revision)
                pair = self._revision_pairs.setdefault(
                    key,
                    {
                        "planning_skill": last_planning,
                        "revision_skill": first_revision,
                        "count": 0,
                        "branches": [],
                        "repos": [],
                    },
                )
                pair["count"] = int(pair["count"]) + 1
                branch_name = chunk.get("branch")
                if (
                    isinstance(branch_name, str)
                    and branch_name
                    and len(pair["branches"]) < _MAX_PAIR_EXAMPLES
                    and branch_name not in pair["branches"]
                ):
                    pair["branches"].append(branch_name)
                if (
                    isinstance(repo, str)
                    and repo
                    and len(pair["repos"]) < _MAX_PAIR_EXAMPLES
                    and repo not in pair["repos"]
                ):
                    pair["repos"].append(repo)

    def to_dict(self) -> dict[str, Any]:
        nodes: list[dict[str, Any]] = []
        for node in sorted(self._nodes.values(), key=lambda value: value["id"]):
            result = dict(node)
            if result["kind"] == "implicit":
                support = int(result.get("count", 0))
                total = max(1, self._total_implicit_uses)
                proportion = support / total
                z = 1.96
                denominator = 1.0 + (z * z) / total
                center = (proportion + (z * z) / (2 * total)) / denominator
                margin = (
                    z * ((proportion * (1.0 - proportion) / total) + (z * z) / (4 * total * total)) ** 0.5 / denominator
                )
                low = max(0.0, round(center - margin, 3))
                high = min(1.0, round(center + margin, 3))
                result["confidence_low"] = low
                result["confidence_high"] = high
            nodes.append(result)

        edges = [
            {
                "source": source,
                "target": target,
                "phase": phase,
                "count": count,
            }
            for (source, target, phase), count in sorted(
                self._edges.items(),
                key=lambda item: (-item[1], item[0][2], item[0][0], item[0][1]),
            )
        ]

        revision_prevention = []
        for pair in sorted(
            self._revision_pairs.values(),
            key=lambda item: (-int(item["count"]), item["planning_skill"]),
        ):
            revision_prevention.append(
                {
                    "planning_skill": pair["planning_skill"],
                    "revision_skill": pair["revision_skill"],
                    "count": pair["count"],
                    "example_branches": pair["branches"],
                    "example_repos": pair["repos"],
                    "suggested_adjustment": (
                        f"Insert {pair['revision_skill']} checks before declaring {pair['planning_skill']} complete."
                    ),
                }
            )

        return {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "nodes": nodes,
            "edges": edges,
            "revision_prevention": revision_prevention,
        }
