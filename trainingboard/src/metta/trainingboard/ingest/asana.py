from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import asana as asana_sdk
from pydantic import BaseModel, Field

from metta.trainingboard.keyword_match import count_keyword_hits
from metta.trainingboard.models import ResearchPaperRecord
from metta.trainingboard.scoring import AXIS_SPECS

ASANA_TASK_FIELDS = (
    "gid,name,notes,permalink_url,created_at,modified_at,completed,completed_at,"
    "custom_fields.name,custom_fields.display_value,custom_fields.text_value,"
    "memberships.project.gid,memberships.section.gid"
)
ASANA_STORY_FIELDS = "gid,type,resource_subtype,text,created_at,created_by.name"

PAPER_HOST_MARKERS = (
    "arxiv.org",
    "openreview.net",
    "paperswithcode.com",
    "aclanthology.org",
    "ieeexplore.ieee.org",
    "dl.acm.org",
    "nature.com",
    "science.org",
    "research.google",
)
RECOMMENDATION_MARKERS = (
    "recommend",
    "should",
    "need to",
    "needs to",
    "try ",
    "consider",
    "improve",
    "focus on",
    "next step",
    "action item",
    "follow up",
)
URL_PATTERN = re.compile(r"https?://[^\s\]\[\)\(\}\{\"'<>]+", re.IGNORECASE)
WHITESPACE_PATTERN = re.compile(r"\s+")
ASANA_LIST_URL_PATTERN = re.compile(r"/project/(?P<project_gid>\d+)/list/(?P<section_gid>\d+)")


class RawAsanaCustomField(BaseModel):
    name: str
    display_value: Optional[str] = None
    text_value: Optional[str] = None


class RawAsanaMembershipEntity(BaseModel):
    gid: Optional[str] = None


class RawAsanaMembership(BaseModel):
    project: Optional[RawAsanaMembershipEntity] = None
    section: Optional[RawAsanaMembershipEntity] = None


class RawAsanaTask(BaseModel):
    gid: str
    name: str
    notes: Optional[str] = None
    permalink_url: Optional[str] = None
    created_at: Optional[str] = None
    modified_at: Optional[str] = None
    completed: bool = False
    completed_at: Optional[str] = None
    custom_fields: list[RawAsanaCustomField] = Field(default_factory=list)
    memberships: list[RawAsanaMembership] = Field(default_factory=list)


class RawAsanaStory(BaseModel):
    gid: str
    type: Optional[str] = None
    resource_subtype: Optional[str] = None
    text: Optional[str] = None
    created_at: Optional[str] = None


class AsanaTaskCacheEntry(BaseModel):
    task: RawAsanaTask
    stories: list[RawAsanaStory] = Field(default_factory=list)


class AsanaProjectRawCache(BaseModel):
    source_key: str
    project_gid: str
    section_gid: Optional[str] = None
    synced_at: str
    tasks: dict[str, AsanaTaskCacheEntry] = Field(default_factory=dict)


class ResearchSyncSummary(BaseModel):
    source_key: str
    used_project_fallback: bool = False
    tasks_total: int
    story_refetch_count: int
    story_reuse_count: int
    records_written: int
    output_records_total: int
    paper_link_count: int
    recommendation_count: int


def asana_client(token: str) -> asana_sdk.ApiClient:
    config = asana_sdk.Configuration()
    config.access_token = token
    config.connection_pool_kw = {"timeout": 30}
    return asana_sdk.ApiClient(config)


def source_key(project_gid: str, section_gid: Optional[str]) -> str:
    return f"{project_gid}:{section_gid or 'all'}"


def parse_project_and_section_from_url(source_url: str) -> tuple[str, str]:
    parsed = urlparse(source_url)
    match = ASANA_LIST_URL_PATTERN.search(parsed.path)
    if match is None:
        raise ValueError(f"Unsupported Asana list URL: {source_url}")
    return match.group("project_gid"), match.group("section_gid")


def default_raw_cache_path(state_dir: Path, project_gid: str, section_gid: Optional[str]) -> Path:
    section_component = section_gid if section_gid else "all"
    file_name = f"asana_research_raw_cache_{project_gid}_{section_component}.json"
    return state_dir.expanduser() / "cache" / file_name


def fetch_project_tasks(project_gid: str, token: str, include_completed: bool = True) -> list[RawAsanaTask]:
    client = asana_client(token)
    tasks_api = asana_sdk.TasksApi(client)
    params = {"opt_fields": ASANA_TASK_FIELDS}
    params["completed_since"] = "1970-01-01T00:00:00Z" if include_completed else "now"
    raw_tasks = list(tasks_api.get_tasks_for_project(project_gid, params))
    return [RawAsanaTask.model_validate(raw_task) for raw_task in raw_tasks]


def _task_matches_section(task: RawAsanaTask, section_gid: str) -> bool:
    return any(
        membership.section is not None and membership.section.gid == section_gid for membership in task.memberships
    )


def fetch_section_tasks(
    project_gid: str, section_gid: str, token: str, include_completed: bool = True
) -> list[RawAsanaTask]:
    project_tasks = fetch_project_tasks(project_gid=project_gid, token=token, include_completed=include_completed)
    return [task for task in project_tasks if _task_matches_section(task, section_gid)]


def fetch_task_stories(task_gid: str, token: str) -> list[RawAsanaStory]:
    client = asana_client(token)
    stories_api = asana_sdk.StoriesApi(client)
    params = {"opt_fields": ASANA_STORY_FIELDS}
    raw_stories = list(stories_api.get_stories_for_task(task_gid, params))
    return [RawAsanaStory.model_validate(raw_story) for raw_story in raw_stories]


def _custom_field_map(task: RawAsanaTask) -> dict[str, str]:
    values: dict[str, str] = {}
    for custom_field in task.custom_fields:
        value = custom_field.display_value or custom_field.text_value or ""
        if value:
            values[custom_field.name] = value
    return values


def _normalize_text(raw_text: str) -> str:
    return WHITESPACE_PATTERN.sub(" ", raw_text).strip()


def _extract_urls(text_chunks: list[str]) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for text in text_chunks:
        for url in URL_PATTERN.findall(text):
            normalized_url = url.rstrip(".,;:!?)]}")
            if normalized_url in seen:
                continue
            seen.add(normalized_url)
            urls.append(normalized_url)
    return urls


def _is_research_link(url: str) -> bool:
    hostname = (urlparse(url).hostname or "").lower()
    return any(marker in hostname for marker in PAPER_HOST_MARKERS)


def extract_paper_links(text_chunks: list[str]) -> list[str]:
    return [url for url in _extract_urls(text_chunks) if _is_research_link(url)]


def _recommendation_candidates(text_chunks: list[str]) -> list[str]:
    candidates: list[str] = []
    for text in text_chunks:
        for raw_line in text.splitlines():
            normalized_line = _normalize_text(raw_line.lstrip("-•* "))
            if not normalized_line:
                continue
            if len(normalized_line) < 24 or len(normalized_line) > 280:
                continue
            lower_line = normalized_line.lower()
            if any(marker in lower_line for marker in RECOMMENDATION_MARKERS):
                candidates.append(normalized_line)
    return candidates


def extract_recommendations(text_chunks: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for recommendation in _recommendation_candidates(text_chunks):
        normalized_key = recommendation.lower()
        if normalized_key in seen:
            continue
        seen.add(normalized_key)
        unique.append(recommendation)
    return unique[:12]


def infer_axis_scores(text: str, recommendations: list[str], paper_links: list[str]) -> dict[str, float]:
    normalized_text = text.lower()
    recommendation_text = "\n".join(recommendations).lower()
    has_links = bool(paper_links)

    axis_scores: dict[str, float] = {}
    for axis_spec in AXIS_SPECS:
        text_hits = count_keyword_hits(normalized_text, axis_spec.keywords)
        recommendation_hits = count_keyword_hits(recommendation_text, axis_spec.keywords)
        if text_hits == 0 and recommendation_hits == 0:
            continue

        score = 0.1
        score += min(0.55, text_hits * 0.08)
        score += min(0.25, recommendation_hits * 0.09)
        if has_links:
            score += 0.06
        axis_scores[axis_spec.axis_id] = round(min(1.0, score), 3)
    return axis_scores


def _story_analysis_texts(stories: list[RawAsanaStory]) -> list[str]:
    comment_texts: list[str] = []
    for story in stories:
        story_text = story.text or ""
        if not story_text.strip():
            continue
        story_type = (story.type or "").lower()
        story_subtype = (story.resource_subtype or "").lower()
        if "comment" in story_type or "comment" in story_subtype:
            comment_texts.append(story_text)
            continue
        comment_texts.append(story_text)
    return comment_texts


def _record_from_cache_entry(entry: AsanaTaskCacheEntry) -> ResearchPaperRecord:
    task = entry.task
    custom_fields = _custom_field_map(task)
    story_texts = _story_analysis_texts(entry.stories)
    text_chunks = [task.name, task.notes or "", *custom_fields.values(), *story_texts]

    paper_links = extract_paper_links(text_chunks)
    recommendations = extract_recommendations([task.notes or "", *story_texts])
    axis_scores = infer_axis_scores("\n".join(text_chunks), recommendations, paper_links)

    return ResearchPaperRecord(
        gid=task.gid,
        title=task.name,
        notes=task.notes or "",
        permalink_url=task.permalink_url or "",
        created_at=task.created_at or "",
        modified_at=task.modified_at or "",
        custom_fields=custom_fields,
        paper_links=paper_links,
        recommendations=recommendations,
        inferred_axis_scores=axis_scores,
    )


def _load_raw_cache(project_gid: str, section_gid: Optional[str], raw_cache_path: Path) -> AsanaProjectRawCache:
    key = source_key(project_gid, section_gid)
    if not raw_cache_path.is_file():
        return AsanaProjectRawCache(
            source_key=key,
            project_gid=project_gid,
            section_gid=section_gid,
            synced_at="",
            tasks={},
        )

    raw_payload = json.loads(raw_cache_path.read_text(encoding="utf-8"))
    cache = AsanaProjectRawCache.model_validate(raw_payload)
    if cache.source_key != key:
        return AsanaProjectRawCache(
            source_key=key,
            project_gid=project_gid,
            section_gid=section_gid,
            synced_at="",
            tasks={},
        )
    return cache


def _write_json_file(path: Path, payload: dict | list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _load_existing_records(path: Path) -> list[ResearchPaperRecord]:
    if not path.is_file():
        return []
    raw_records = json.loads(path.read_text(encoding="utf-8"))
    return [ResearchPaperRecord.model_validate(raw_record) for raw_record in raw_records]


def _record_sort_key(record: ResearchPaperRecord) -> tuple[str, str]:
    return (record.modified_at, record.gid)


def _merge_records(
    existing_records: list[ResearchPaperRecord], new_records: list[ResearchPaperRecord]
) -> list[ResearchPaperRecord]:
    merged_by_gid: dict[str, ResearchPaperRecord] = {record.gid: record for record in existing_records}
    for record in new_records:
        if record.gid not in merged_by_gid:
            merged_by_gid[record.gid] = record
            continue
        if _record_sort_key(record) >= _record_sort_key(merged_by_gid[record.gid]):
            merged_by_gid[record.gid] = record
    return sorted(merged_by_gid.values(), key=_record_sort_key, reverse=True)


def _fetch_story_batch(task_gids: list[str], token: str, story_worker_count: int) -> dict[str, list[RawAsanaStory]]:
    if not task_gids:
        return {}

    with ThreadPoolExecutor(max_workers=story_worker_count) as executor:
        story_lists = list(executor.map(lambda task_gid: fetch_task_stories(task_gid=task_gid, token=token), task_gids))
    return dict(zip(task_gids, story_lists, strict=True))


def sync_project_research(
    project_gid: str,
    token: str,
    raw_cache_path: Path,
    output_path: Path,
    section_gid: Optional[str] = None,
    include_completed: bool = True,
    story_worker_count: int = 12,
    merge_output: bool = True,
) -> tuple[list[ResearchPaperRecord], ResearchSyncSummary]:
    key = source_key(project_gid, section_gid)
    previous_cache = _load_raw_cache(project_gid=project_gid, section_gid=section_gid, raw_cache_path=raw_cache_path)
    used_project_fallback = False
    if section_gid:
        tasks = fetch_section_tasks(
            project_gid=project_gid,
            section_gid=section_gid,
            token=token,
            include_completed=include_completed,
        )
        if not tasks:
            used_project_fallback = True
            tasks = fetch_project_tasks(project_gid=project_gid, token=token, include_completed=include_completed)
    else:
        tasks = fetch_project_tasks(project_gid=project_gid, token=token, include_completed=include_completed)

    refreshed_entries: dict[str, AsanaTaskCacheEntry] = {}
    story_refetch_count = 0
    story_reuse_count = 0
    task_gids_to_refetch: list[str] = []

    for task in tasks:
        previous_entry = previous_cache.tasks.get(task.gid)
        if previous_entry is not None and previous_entry.task.modified_at == task.modified_at:
            refreshed_entries[task.gid] = AsanaTaskCacheEntry(task=task, stories=previous_entry.stories)
            story_reuse_count += 1
            continue
        task_gids_to_refetch.append(task.gid)

    story_batch = _fetch_story_batch(
        task_gids=task_gids_to_refetch,
        token=token,
        story_worker_count=max(1, story_worker_count),
    )
    story_refetch_count = len(task_gids_to_refetch)

    for task in tasks:
        if task.gid in refreshed_entries:
            continue
        refreshed_entries[task.gid] = AsanaTaskCacheEntry(task=task, stories=story_batch[task.gid])

    synced_at = datetime.now(tz=UTC).isoformat()
    raw_cache = AsanaProjectRawCache(
        source_key=key,
        project_gid=project_gid,
        section_gid=section_gid,
        synced_at=synced_at,
        tasks=refreshed_entries,
    )

    source_records = [_record_from_cache_entry(entry) for entry in refreshed_entries.values()]
    source_records = sorted(source_records, key=_record_sort_key, reverse=True)
    records = _merge_records(_load_existing_records(output_path), source_records) if merge_output else source_records

    _write_json_file(raw_cache_path, raw_cache.model_dump())
    _write_json_file(output_path, [record.model_dump() for record in records])

    summary = ResearchSyncSummary(
        source_key=key,
        used_project_fallback=used_project_fallback,
        tasks_total=len(tasks),
        story_refetch_count=story_refetch_count,
        story_reuse_count=story_reuse_count,
        records_written=len(source_records),
        output_records_total=len(records),
        paper_link_count=sum(len(record.paper_links) for record in source_records),
        recommendation_count=sum(len(record.recommendations) for record in source_records),
    )
    return records, summary
