from __future__ import annotations

import json
import os
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from metta.trainingboard.models import LLMTaskScoreCacheEntry, LLMTaskScores, ResearchPaperRecord
from metta.trainingboard.scoring import AXIS_SPECS

DEFAULT_OPENAI_MODEL = "gpt-4.1-mini"
DEFAULT_OPENAI_TIMEOUT_SECONDS = 90
LLM_RUBRIC_VERSION = "v1"
OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"


class LLMScoringSummary(BaseModel):
    model: str
    cache_path: str
    reused_count: int = Field(ge=0)
    scored_count: int = Field(ge=0)
    processed_count: int = Field(ge=0)
    task_offset: int = Field(ge=0)
    task_limit: int = Field(ge=0)
    rubric_version: str


def default_llm_cache_path(state_dir: Path) -> Path:
    return state_dir.expanduser() / "cache" / "task_llm_scores.ndjson"


def resolve_openai_api_key(explicit_key: str = "", token_env: str = "OPENAI_API_KEY") -> str:
    return explicit_key or os.environ.get(token_env, "")


def load_llm_score_cache(cache_path: Path) -> dict[str, LLMTaskScoreCacheEntry]:
    if not cache_path.is_file():
        return {}

    entries: dict[str, LLMTaskScoreCacheEntry] = {}
    with cache_path.open(encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            entry = LLMTaskScoreCacheEntry.model_validate_json(line)
            entries[entry.gid] = entry
    return entries


def write_llm_score_cache(cache_path: Path, entries: dict[str, LLMTaskScoreCacheEntry]) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    sorted_entries = sorted(entries.values(), key=lambda entry: (entry.scored_at, entry.gid), reverse=True)
    with cache_path.open("w", encoding="utf-8") as handle:
        for entry in sorted_entries:
            handle.write(entry.model_dump_json())
            handle.write("\n")


def _truncate_text(text: str, max_chars: int) -> str:
    normalized = text.strip()
    if len(normalized) <= max_chars:
        return normalized
    return f"{normalized[: max_chars - 15]}\n...[truncated]"


def _task_prompt(record: ResearchPaperRecord) -> str:
    custom_fields_text = "\n".join(f"- {key}: {value}" for key, value in sorted(record.custom_fields.items()))
    links_text = "\n".join(f"- {link}" for link in record.paper_links)
    recommendations_text = "\n".join(f"- {recommendation}" for recommendation in record.recommendations)
    axis_definitions = "\n".join(f"- {spec.axis_id}: {spec.principle}" for spec in AXIS_SPECS)
    return (
        "Score this training task from 0.0 to 1.0 using the rubric below.\n"
        "Return only JSON that matches the schema.\n\n"
        "Task:\n"
        f"- gid: {record.gid}\n"
        f"- title: {_truncate_text(record.title, 220)}\n"
        f"- notes: {_truncate_text(record.notes, 3200)}\n"
        f"- custom_fields:\n{custom_fields_text or '- [none]'}\n"
        f"- paper_links:\n{links_text or '- [none]'}\n"
        f"- recommendations:\n{recommendations_text or '- [none]'}\n\n"
        "Impact axes (higher means more wall-clock training speed upside):\n"
        f"{axis_definitions}\n\n"
        "Execution metrics:\n"
        "- simplicity: high means straightforward implementation with limited moving parts\n"
        "- time_to_implement: high means faster to ship and validate\n"
        "- failure_likelihood: high means higher chance of failure or regression\n"
        "- dependency_load: high means many cross-team/system dependencies\n"
        "- measurement_speed: high means impact can be measured quickly\n"
        "- reversibility: high means easy rollback or safe trial\n\n"
        "evidence_confidence: high means this task description has concrete evidence and enough context."
    )


def _response_json_schema() -> dict:
    axis_properties = {spec.axis_id: {"type": "number", "minimum": 0.0, "maximum": 1.0} for spec in AXIS_SPECS}
    execution_properties = {
        "simplicity": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "time_to_implement": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "failure_likelihood": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "dependency_load": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "measurement_speed": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "reversibility": {"type": "number", "minimum": 0.0, "maximum": 1.0},
    }
    return {
        "name": "trainingboard_task_llm_scores",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "axis_scores": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": axis_properties,
                    "required": list(axis_properties.keys()),
                },
                "execution_scores": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": execution_properties,
                    "required": list(execution_properties.keys()),
                },
                "evidence_confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "rationale": {"type": "string"},
            },
            "required": ["axis_scores", "execution_scores", "evidence_confidence", "rationale"],
        },
    }


def _score_task_with_openai(
    record: ResearchPaperRecord,
    model: str,
    api_key: str,
    timeout_seconds: int = DEFAULT_OPENAI_TIMEOUT_SECONDS,
) -> LLMTaskScores:
    payload = {
        "model": model,
        "temperature": 0,
        "response_format": {"type": "json_schema", "json_schema": _response_json_schema()},
        "messages": [
            {
                "role": "system",
                "content": "You are a strict evaluator for RL training prioritization. Output valid JSON only.",
            },
            {"role": "user", "content": _task_prompt(record)},
        ],
    }
    request = urllib.request.Request(
        OPENAI_CHAT_COMPLETIONS_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        response_payload = json.loads(response.read().decode("utf-8"))

    content = response_payload["choices"][0]["message"]["content"]
    return LLMTaskScores.model_validate_json(content)


def score_tasks_with_openai(
    papers: list[ResearchPaperRecord],
    *,
    model: str = DEFAULT_OPENAI_MODEL,
    api_key: str,
    cache_path: Path,
    task_limit: Optional[int] = None,
    task_offset: int = 0,
    force_refresh: bool = False,
) -> tuple[dict[str, LLMTaskScores], LLMScoringSummary]:
    offset = max(0, task_offset)
    if task_limit is None:
        selected_papers = papers[offset:]
        effective_task_limit = len(selected_papers)
    else:
        effective_task_limit = max(0, task_limit)
        selected_papers = papers[offset : offset + effective_task_limit]
    cache_entries = load_llm_score_cache(cache_path)
    selected_scores: dict[str, LLMTaskScores] = {}
    scored_count = 0
    reused_count = 0

    for paper in selected_papers:
        cache_entry = cache_entries.get(paper.gid)
        is_cache_hit = (
            cache_entry is not None
            and cache_entry.modified_at == paper.modified_at
            and cache_entry.model == model
            and cache_entry.rubric_version == LLM_RUBRIC_VERSION
            and not force_refresh
        )
        if is_cache_hit:
            selected_scores[paper.gid] = cache_entry.scores
            reused_count += 1
            continue

        llm_scores = _score_task_with_openai(record=paper, model=model, api_key=api_key)
        cache_entries[paper.gid] = LLMTaskScoreCacheEntry(
            gid=paper.gid,
            modified_at=paper.modified_at,
            model=model,
            rubric_version=LLM_RUBRIC_VERSION,
            scored_at=datetime.now(tz=UTC).isoformat(),
            scores=llm_scores,
        )
        selected_scores[paper.gid] = llm_scores
        scored_count += 1

    write_llm_score_cache(cache_path=cache_path, entries=cache_entries)
    return selected_scores, LLMScoringSummary(
        model=model,
        cache_path=str(cache_path),
        reused_count=reused_count,
        scored_count=scored_count,
        processed_count=len(selected_papers),
        task_offset=offset,
        task_limit=effective_task_limit,
        rubric_version=LLM_RUBRIC_VERSION,
    )
