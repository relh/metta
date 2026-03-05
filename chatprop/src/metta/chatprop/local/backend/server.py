"""Small localhost server for chatprop GUI wrappers and session/branch catalog."""

from __future__ import annotations

import argparse
import contextlib
import json
import mimetypes
import re
import subprocess
import threading
import urllib.parse
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from metta.chatprop.analyze import build_analysis_context, run_analysis
from metta.chatprop.config import ChatpropConfig, load_config
from metta.chatprop.local.flowchart_core import render_mermaid_flowchart, write_flowchart_outputs
from metta.chatprop.local.indexer import (
    BranchSegment,
    extract_branch_segments_from_transcript,
    extract_branches_from_transcript,
    extract_work_branches_from_segments,
)
from metta.chatprop.local.workflow import (
    SkillGraphAccumulator,
    analyze_session_feature_chunks,
    build_feature_chunks_from_segments,
    load_explicit_skills,
)
from metta.chatprop.scanner import find_transcripts_for_branches, scan_archived

FRONTEND_ROOT = Path(__file__).resolve().parents[1] / "frontend"
CATALOG_CACHE_TTL = timedelta(hours=24)
CATALOG_JOB_TTL = timedelta(hours=2)
DEFAULT_GH_AUTHOR = "relh"
MERGED_PR_CACHE_SCOPE = "author_all_repos_v2"
DEFAULT_GRAPHITE_CLOSED_REPO = "Metta-AI/metta"
DEFAULT_FLOWCHART_MIN_NODE_COUNT = 1
DEFAULT_FLOWCHART_MIN_EDGE_COUNT = 1
DEFAULT_FLOWCHART_MAX_NODES = 120
DEFAULT_FLOWCHART_MAX_EDGES = 350
DEFAULT_FLOWCHART_EXPORT_RELATIVE_MERMAID = Path("exports/chatprop_flowchart.mmd")
DEFAULT_FLOWCHART_EXPORT_RELATIVE_JSON = Path("exports/chatprop_flowchart.json")
PR_NUMBER_IN_SUBJECT = re.compile(r"\(#(\d+)\)")
_GH_PR_SEARCH_QUERY = """
query($search: String!, $first: Int!, $after: String) {
  search(query: $search, type: ISSUE, first: $first, after: $after) {
    pageInfo {
      hasNextPage
      endCursor
    }
    nodes {
      ... on PullRequest {
        number
        title
        url
        mergedAt
        closedAt
        headRefName
        baseRefName
        updatedAt
        repository {
          name
          nameWithOwner
        }
      }
    }
  }
}
""".strip()

_catalog_jobs_lock = threading.Lock()
_catalog_jobs: dict[str, dict[str, Any]] = {}


def _repo_root_for_explicit_skills() -> Path:
    module_path = Path(__file__).resolve()
    for candidate in module_path.parents:
        if (candidate / "skills").is_dir():
            return candidate
    return module_path.parent


def _normalize_catalog_branch_name(branch: str) -> str:
    cleaned = branch.strip()
    if not cleaned:
        return ""
    lowered = cleaned.lower()
    if lowered in {"main", "master", "head"}:
        return "main"
    return cleaned


def _extract_branches(payload: dict[str, Any]) -> list[str]:
    raw = payload.get("branches")
    if not isinstance(raw, list):
        return []

    cleaned: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, str):
            continue
        branch = item.strip()
        if not branch or branch in seen:
            continue
        seen.add(branch)
        cleaned.append(branch)
    return cleaned


def _parse_bounded_int(raw: Any, *, minimum: int, maximum: int) -> int | None:
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        value = raw
    elif isinstance(raw, str):
        text = raw.strip().removeprefix("+")
        if not text.isdigit():
            return None
        value = int(text)
    else:
        return None
    if value < minimum or value > maximum:
        return None
    return value


def _flowchart_options_from_payload(payload: dict[str, Any]) -> dict[str, int] | None:
    min_node_count_raw = payload.get("min_node_count", DEFAULT_FLOWCHART_MIN_NODE_COUNT)
    min_edge_count_raw = payload.get("min_edge_count", DEFAULT_FLOWCHART_MIN_EDGE_COUNT)
    max_nodes_raw = payload.get("max_nodes", DEFAULT_FLOWCHART_MAX_NODES)
    max_edges_raw = payload.get("max_edges", DEFAULT_FLOWCHART_MAX_EDGES)

    min_node_count = _parse_bounded_int(min_node_count_raw, minimum=1, maximum=100_000)
    min_edge_count = _parse_bounded_int(min_edge_count_raw, minimum=1, maximum=100_000)
    max_nodes = _parse_bounded_int(max_nodes_raw, minimum=1, maximum=10_000)
    max_edges = _parse_bounded_int(max_edges_raw, minimum=1, maximum=20_000)
    if min_node_count is None or min_edge_count is None or max_nodes is None or max_edges is None:
        return None

    return {
        "min_node_count": min_node_count,
        "min_edge_count": min_edge_count,
        "max_nodes": max_nodes,
        "max_edges": max_edges,
    }


def _flowchart_export_defaults(config: ChatpropConfig) -> tuple[Path, Path]:
    export_root = config.state_dir.expanduser() / "cache"
    return (
        export_root / DEFAULT_FLOWCHART_EXPORT_RELATIVE_MERMAID,
        export_root / DEFAULT_FLOWCHART_EXPORT_RELATIVE_JSON,
    )


def _flowchart_payload(
    workflow_graph: dict[str, Any],
    *,
    options: dict[str, int],
    catalog_generated_at: str | None = None,
    session_count: int | None = None,
    branch_count: int | None = None,
) -> dict[str, Any]:
    rendered = render_mermaid_flowchart(
        workflow_graph,
        min_node_count=options["min_node_count"],
        min_edge_count=options["min_edge_count"],
        max_nodes=options["max_nodes"],
        max_edges=options["max_edges"],
    )
    payload: dict[str, Any] = {
        "generated_at": _iso_utc(datetime.now(tz=UTC)),
        "workflow_graph": workflow_graph,
        "selected_graph": rendered["selected_graph"],
        "mermaid": rendered["mermaid"],
        "options": options,
    }
    if catalog_generated_at:
        payload["catalog_generated_at"] = catalog_generated_at
    if session_count is not None:
        payload["session_count"] = session_count
    if branch_count is not None:
        payload["branch_count"] = branch_count
    return payload


def _flowchart_payload_with_catalog(
    workflow_graph: dict[str, Any],
    *,
    options: dict[str, int],
    catalog: dict[str, Any] | None,
) -> dict[str, Any]:
    return _flowchart_payload(
        workflow_graph,
        options=options,
        catalog_generated_at=catalog.get("generated_at") if catalog is not None else None,
        session_count=catalog.get("session_count") if catalog is not None else None,
        branch_count=catalog.get("branch_count") if catalog is not None else None,
    )


def _parse_output_path(raw_value: Any) -> Path | None:
    if raw_value is None:
        return None
    if not isinstance(raw_value, str):
        return None
    text = raw_value.strip()
    if not text:
        return None
    return Path(text).expanduser().resolve()


def _resolve_frontend_target(base: Path, file_name: str) -> Path | None:
    target = (base / file_name).resolve()
    try:
        target.relative_to(base.resolve())
    except ValueError:
        return None
    return target


def _read_json_dict(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if isinstance(parsed, dict):
        return parsed
    return {}


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


def _iso_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _extract_session_window(path: Path) -> tuple[str, str]:
    first_timestamp: datetime | None = None
    last_timestamp: datetime | None = None

    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            timestamp = payload.get("timestamp")
            if not isinstance(timestamp, str):
                continue
            parsed = _parse_datetime(timestamp)
            if parsed is None:
                continue
            if first_timestamp is None:
                first_timestamp = parsed
            last_timestamp = parsed

    if first_timestamp and last_timestamp:
        return _iso_utc(first_timestamp), _iso_utc(last_timestamp)

    stat = path.stat()
    fallback = datetime.fromtimestamp(stat.st_mtime, tz=UTC)
    fallback_iso = _iso_utc(fallback)
    return fallback_iso, fallback_iso


def _mtime_window(path: Path) -> tuple[str, str]:
    fallback = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    fallback_iso = _iso_utc(fallback)
    return fallback_iso, fallback_iso


def _extract_session_cwd(path: Path, *, max_lines: int = 500) -> str | None:
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for index, raw_line in enumerate(handle, start=1):
            if index > max_lines:
                break
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            cwd = payload.get("cwd")
            if isinstance(cwd, str) and cwd.strip():
                return cwd.strip()
    return None


def _repo_from_cwd(cwd: str, *, cache: dict[str, str | None]) -> str | None:
    cached = cache.get(cwd)
    if cwd in cache:
        return cached

    path = Path(cwd).expanduser()
    generic_names = {"", "gt", "co_gas", "users", "relh"}
    parts = list(path.parts)

    # Prefer explicit co_gas repo segment when available.
    for index, part in enumerate(parts):
        if part.lower() != "co_gas":
            continue
        if index + 1 < len(parts):
            candidate = parts[index + 1].strip()
            if candidate and candidate.lower() not in generic_names:
                cache[cwd] = candidate
                return candidate

    for candidate in [path, *path.parents]:
        if (candidate / ".git").exists():
            repo = candidate.name.strip()
            if repo.lower() in generic_names:
                continue
            cache[cwd] = repo if repo else None
            return cache[cwd]
        if candidate == candidate.parent:
            break

    fallback = ""
    for part in reversed(parts):
        candidate = part.strip()
        if candidate and candidate.lower() not in generic_names:
            fallback = candidate
            break

    cache[cwd] = fallback or None
    return cache[cwd]


def _parse_archived_session_id(path: Path) -> str:
    stem = path.stem
    prefix, sep, suffix = stem.rpartition("-")
    if sep and suffix.isdigit() and prefix:
        return prefix
    return stem


def _read_archive_metadata_windows(config: ChatpropConfig) -> dict[str, tuple[str, str]]:
    metadata_root = config.state_dir.expanduser() / "archive" / "metadata"
    if not metadata_root.is_dir():
        return {}

    windows: dict[str, tuple[str, str]] = {}
    for metadata_path in metadata_root.glob("*.json"):
        payload = _read_json_dict(metadata_path)
        session_id = payload.get("session_id")
        started_at = payload.get("started_at")
        ended_at = payload.get("ended_at")
        if not isinstance(session_id, str) or not session_id.strip():
            continue
        if not isinstance(started_at, str) or not started_at.strip():
            continue
        if not isinstance(ended_at, str) or not ended_at.strip():
            continue
        windows[session_id] = (started_at, ended_at)
    return windows


def _read_archive_index(config: ChatpropConfig) -> dict[Path, set[str]]:
    index_path = config.state_dir.expanduser() / "archive" / "index.json"
    archive_root = config.state_dir.expanduser() / "archive"
    payload = _read_json_dict(index_path)
    branches = payload.get("branches")
    if not isinstance(branches, dict):
        return {}

    reverse: dict[Path, set[str]] = {}
    for branch, keys in branches.items():
        if not isinstance(branch, str) or not isinstance(keys, list):
            continue
        for key in keys:
            if not isinstance(key, str):
                continue
            candidate = (archive_root / key).resolve()
            reverse.setdefault(candidate, set()).add(branch)
    return reverse


def _run_capture(cmd: list[str], *, timeout_seconds: float = 4.0) -> tuple[int, str]:
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except FileNotFoundError:
        return 127, ""
    except subprocess.TimeoutExpired:
        return 124, ""
    return result.returncode, result.stdout.strip()


def _git_ref_exists(ref: str) -> bool:
    return _run_capture(["git", "rev-parse", "--verify", ref])[0] == 0


def _git_commit_window(branch: str) -> tuple[str | None, str | None]:
    for ref in (branch, f"origin/{branch}"):
        if not _git_ref_exists(ref):
            continue
        rc_first, first = _run_capture(["git", "log", "--reverse", "--format=%cI", "-1", ref])
        rc_last, last = _run_capture(["git", "log", "--format=%cI", "-1", ref])
        if rc_first == 0 and rc_last == 0 and first and last:
            return first, last
    return None, None


def _select_pr_record(branch: str, records: list[dict[str, Any]]) -> dict[str, Any] | None:
    exact = [record for record in records if record.get("headRefName") == branch]
    candidates = exact if exact else records
    if not candidates:
        return None

    def _sort_key(record: dict[str, Any]) -> tuple[int, str]:
        merged = 1 if record.get("mergedAt") else 0
        updated = record.get("updatedAt")
        return merged, updated if isinstance(updated, str) else ""

    return max(candidates, key=_sort_key)


def _query_pr_record(branch: str) -> dict[str, Any] | None:
    rc, output = _run_capture(
        [
            "gh",
            "pr",
            "list",
            "--state",
            "all",
            "--search",
            f"head:{branch}",
            "--limit",
            "20",
            "--json",
            "number,title,state,mergedAt,closedAt,createdAt,updatedAt,url,headRefName,baseRefName",
        ],
        timeout_seconds=3.0,
    )
    if rc != 0 or not output:
        return None

    try:
        parsed = json.loads(output)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, list):
        return None
    records = [record for record in parsed if isinstance(record, dict)]
    return _select_pr_record(branch, records)


def _merged_pr_cache_path(config: ChatpropConfig) -> Path:
    return config.state_dir.expanduser() / "cache" / "merged_prs.json"


def _load_merged_pr_cache(config: ChatpropConfig) -> tuple[str | None, list[dict[str, Any]], str | None]:
    payload = _read_json_dict(_merged_pr_cache_path(config))
    updated_at_raw = payload.get("updated_at")
    updated_at = updated_at_raw if isinstance(updated_at_raw, str) and updated_at_raw.strip() else None
    scope_raw = payload.get("scope")
    scope = scope_raw if isinstance(scope_raw, str) and scope_raw.strip() else None

    merged_prs_raw = payload.get("merged_prs")
    if not isinstance(merged_prs_raw, list):
        return updated_at, [], scope

    merged_prs: list[dict[str, Any]] = []
    for record in merged_prs_raw:
        if isinstance(record, dict):
            merged_prs.append(record)
    return updated_at, merged_prs, scope


def _write_merged_pr_cache(
    config: ChatpropConfig,
    *,
    merged_prs: list[dict[str, Any]],
    author: str,
) -> None:
    path = _merged_pr_cache_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": _iso_utc(datetime.now(tz=UTC)),
        "scope": MERGED_PR_CACHE_SCOPE,
        "author": author,
        "merged_prs": merged_prs,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _merged_since_date(updated_at: str | None) -> str | None:
    parsed = _parse_datetime(updated_at)
    if parsed is None:
        return None
    return parsed.date().isoformat()


def _normalize_merged_pr_record(record: dict[str, Any]) -> dict[str, Any] | None:
    head_ref_name = record.get("headRefName")
    if not isinstance(head_ref_name, str) or not head_ref_name.strip():
        return None
    merged_at = record.get("mergedAt")
    if not isinstance(merged_at, str) or not merged_at.strip():
        return None
    number = record.get("number")
    if not isinstance(number, int):
        return None

    repository = record.get("repository")
    repository_name_with_owner = None
    repository_name = None
    if isinstance(repository, dict):
        raw_full = repository.get("nameWithOwner")
        raw_name = repository.get("name")
        if isinstance(raw_full, str) and raw_full.strip():
            repository_name_with_owner = raw_full.strip()
        if isinstance(raw_name, str) and raw_name.strip():
            repository_name = raw_name.strip()

    return {
        "number": number,
        "title": record.get("title") if isinstance(record.get("title"), str) else None,
        "url": record.get("url") if isinstance(record.get("url"), str) else None,
        "mergedAt": merged_at,
        "closedAt": record.get("closedAt") if isinstance(record.get("closedAt"), str) else None,
        "headRefName": head_ref_name.strip(),
        "baseRefName": record.get("baseRefName") if isinstance(record.get("baseRefName"), str) else None,
        "updatedAt": record.get("updatedAt") if isinstance(record.get("updatedAt"), str) else None,
        "repositoryNameWithOwner": repository_name_with_owner,
        "repositoryName": repository_name,
    }


def _normalize_closed_pr_record(record: dict[str, Any]) -> dict[str, Any] | None:
    head_ref_name = record.get("headRefName")
    if not isinstance(head_ref_name, str) or not head_ref_name.strip():
        return None
    closed_at = record.get("closedAt")
    if not isinstance(closed_at, str) or not closed_at.strip():
        return None
    number = record.get("number")
    if not isinstance(number, int):
        return None

    repository = record.get("repository")
    repository_name_with_owner = None
    repository_name = None
    if isinstance(repository, dict):
        raw_full = repository.get("nameWithOwner")
        raw_name = repository.get("name")
        if isinstance(raw_full, str) and raw_full.strip():
            repository_name_with_owner = raw_full.strip()
        if isinstance(raw_name, str) and raw_name.strip():
            repository_name = raw_name.strip()

    return {
        "number": number,
        "title": record.get("title") if isinstance(record.get("title"), str) else None,
        "url": record.get("url") if isinstance(record.get("url"), str) else None,
        "mergedAt": closed_at,
        "closedAt": closed_at,
        "headRefName": head_ref_name.strip(),
        "baseRefName": record.get("baseRefName") if isinstance(record.get("baseRefName"), str) else None,
        "updatedAt": record.get("updatedAt") if isinstance(record.get("updatedAt"), str) else None,
        "repositoryNameWithOwner": repository_name_with_owner,
        "repositoryName": repository_name,
        "landedVia": "closed_pr_number_on_main",
    }


def _search_pr_records_via_github_api(
    *,
    search_query: str,
    normalizer: Callable[[dict[str, Any]], dict[str, Any] | None],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    cursor: str | None = None
    for _ in range(20):
        cmd = [
            "gh",
            "api",
            "graphql",
            "-f",
            f"query={_GH_PR_SEARCH_QUERY}",
            "-F",
            f"search={search_query}",
            "-F",
            "first=100",
        ]
        if cursor:
            cmd.extend(["-F", f"after={cursor}"])

        rc, output = _run_capture(cmd, timeout_seconds=8.0)
        if rc != 0 or not output:
            break
        try:
            payload = json.loads(output)
        except json.JSONDecodeError:
            break

        data = payload.get("data") if isinstance(payload, dict) else None
        search = data.get("search") if isinstance(data, dict) else None
        nodes = search.get("nodes") if isinstance(search, dict) else None
        if isinstance(nodes, list):
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                normalized = normalizer(node)
                if normalized is not None:
                    records.append(normalized)

        page_info = search.get("pageInfo") if isinstance(search, dict) else None
        if not isinstance(page_info, dict):
            break
        has_next = page_info.get("hasNextPage") is True
        cursor_raw = page_info.get("endCursor")
        cursor = cursor_raw if isinstance(cursor_raw, str) and cursor_raw else None
        if not has_next or cursor is None:
            break
    return records


def _search_merged_prs_via_github_api(
    *,
    author: str,
    merged_since: str | None,
) -> list[dict[str, Any]]:
    search_query = f"is:pr is:merged author:{author} sort:updated-desc"
    if merged_since:
        search_query = f"{search_query} merged:>={merged_since}"
    return _search_pr_records_via_github_api(search_query=search_query, normalizer=_normalize_merged_pr_record)


def _search_closed_unmerged_prs_via_github_api(
    *,
    author: str,
    repo: str,
    closed_since: str | None,
) -> list[dict[str, Any]]:
    search_query = f"repo:{repo} is:pr is:closed -is:merged author:{author} sort:updated-desc"
    if closed_since:
        search_query = f"{search_query} closed:>={closed_since}"
    return _search_pr_records_via_github_api(search_query=search_query, normalizer=_normalize_closed_pr_record)


def _landed_pr_numbers_on_main(base_ref: str = "origin/main") -> set[int]:
    if not _git_ref_exists(base_ref):
        return set()
    rc, output = _run_capture(["git", "log", base_ref, "--format=%s", "--max-count=20000"], timeout_seconds=8.0)
    if rc != 0 or not output:
        return set()
    numbers: set[int] = set()
    for line in output.splitlines():
        for match in PR_NUMBER_IN_SUBJECT.findall(line):
            try:
                numbers.add(int(match))
            except ValueError:
                continue
    return numbers


def _resolve_closed_prs_landed_on_main(
    *,
    author: str,
    repo: str,
    closed_since: str | None,
) -> list[dict[str, Any]]:
    landed_numbers = _landed_pr_numbers_on_main()
    if not landed_numbers:
        return []
    candidates = _search_closed_unmerged_prs_via_github_api(author=author, repo=repo, closed_since=closed_since)
    landed: list[dict[str, Any]] = []
    for record in candidates:
        number = record.get("number")
        if isinstance(number, int) and number in landed_numbers:
            landed.append(record)
    return landed


def _normalize_repo_key(repo: str | None) -> str | None:
    if not isinstance(repo, str):
        return None
    value = repo.strip().lower()
    if not value:
        return None
    return value.replace("_", "-")


def _select_newer_merged_pr(candidate: dict[str, Any], existing: dict[str, Any] | None) -> dict[str, Any]:
    if existing is None:
        return candidate
    candidate_merged_at = candidate.get("mergedAt")
    existing_merged_at = existing.get("mergedAt")
    if (
        isinstance(candidate_merged_at, str)
        and isinstance(existing_merged_at, str)
        and candidate_merged_at > existing_merged_at
    ):
        return candidate
    return existing


def _repo_names_from_record(record: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for key in ("repositoryName", "repositoryNameWithOwner"):
        raw = record.get(key)
        if not isinstance(raw, str):
            continue
        normalized = _normalize_repo_key(raw)
        if normalized:
            names.add(normalized)
            if "/" in normalized:
                names.add(normalized.rsplit("/", 1)[-1])
    return names


def _merged_pr_index(records: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    by_branch: dict[str, dict[str, Any]] = {}
    by_repo_branch: dict[str, dict[str, Any]] = {}
    for record in records:
        branch_raw = record.get("headRefName")
        if not isinstance(branch_raw, str):
            continue
        branch = _normalize_catalog_branch_name(branch_raw)
        if not branch:
            continue
        by_branch[branch] = _select_newer_merged_pr(record, by_branch.get(branch))
        for repo_name in _repo_names_from_record(record):
            key = f"{repo_name}\0{branch}"
            by_repo_branch[key] = _select_newer_merged_pr(record, by_repo_branch.get(key))
    return {"by_branch": by_branch, "by_repo_branch": by_repo_branch}


def _find_merged_pr_match(
    *,
    branch: str,
    repo: str | None,
    repos: list[str] | None,
    merged_pr_lookup: dict[str, dict[str, dict[str, Any]]] | None,
) -> dict[str, Any] | None:
    if not merged_pr_lookup:
        return None
    by_repo_branch = merged_pr_lookup.get("by_repo_branch", {})
    by_branch = merged_pr_lookup.get("by_branch", {})
    normalized_branch = _normalize_catalog_branch_name(branch)
    if not normalized_branch:
        return None

    repo_candidates: list[str] = []
    for raw in [repo, *(repos or [])]:
        normalized_repo = _normalize_repo_key(raw)
        if not normalized_repo or normalized_repo in repo_candidates:
            continue
        repo_candidates.append(normalized_repo)
        if "/" in normalized_repo:
            short_name = normalized_repo.rsplit("/", 1)[-1]
            if short_name not in repo_candidates:
                repo_candidates.append(short_name)

    for repo_name in repo_candidates:
        matched = by_repo_branch.get(f"{repo_name}\0{normalized_branch}")
        if matched is not None:
            return matched
    return by_branch.get(normalized_branch)


def _refresh_merged_pr_cache(
    config: ChatpropConfig,
    *,
    author: str = DEFAULT_GH_AUTHOR,
    fallback_since: str | None = None,
) -> dict[str, dict[str, dict[str, Any]]]:
    updated_at, cached_records, scope = _load_merged_pr_cache(config)
    if scope != MERGED_PR_CACHE_SCOPE:
        updated_at = None
        cached_records = []
    merged_since = _merged_since_date(updated_at)
    if merged_since is None:
        merged_since = fallback_since
    fresh_records = _search_merged_prs_via_github_api(author=author, merged_since=merged_since)
    closed_since = fallback_since if fallback_since else None
    landed_closed_records = _resolve_closed_prs_landed_on_main(
        author=author,
        repo=DEFAULT_GRAPHITE_CLOSED_REPO,
        closed_since=closed_since,
    )

    merged_by_number: dict[int, dict[str, Any]] = {}
    for record in cached_records:
        number = record.get("number")
        if isinstance(number, int):
            merged_by_number[number] = record
    for record in fresh_records:
        number = record.get("number")
        if isinstance(number, int):
            merged_by_number[number] = record
    for record in landed_closed_records:
        number = record.get("number")
        if isinstance(number, int) and number not in merged_by_number:
            merged_by_number[number] = record

    merged_records = list(merged_by_number.values())
    merged_records.sort(
        key=lambda record: record.get("mergedAt") if isinstance(record.get("mergedAt"), str) else "",
        reverse=True,
    )
    _write_merged_pr_cache(config, merged_prs=merged_records, author=author)
    return _merged_pr_index(merged_records)


def _load_merged_pr_index(config: ChatpropConfig) -> dict[str, dict[str, dict[str, Any]]]:
    _, records, scope = _load_merged_pr_cache(config)
    if scope != MERGED_PR_CACHE_SCOPE:
        return {"by_branch": {}, "by_repo_branch": {}}
    return _merged_pr_index(records)


def _branch_outcome_from_sources(
    branch: str,
    *,
    repo: str | None,
    repos: list[str] | None,
    include_pr_lookup: bool,
    include_commit_lookup: bool,
    merged_pr_lookup: dict[str, dict[str, dict[str, Any]]] | None,
) -> dict[str, Any]:
    commit_first_at: str | None = None
    commit_last_at: str | None = None
    if include_commit_lookup:
        commit_first_at, commit_last_at = _git_commit_window(branch)
    merged_pr = _find_merged_pr_match(
        branch=branch,
        repo=repo,
        repos=repos,
        merged_pr_lookup=merged_pr_lookup,
    )
    pr = _query_pr_record(branch) if include_pr_lookup and merged_pr_lookup is None else None

    outcome: dict[str, Any] = {
        "branch": branch,
        "commit_first_at": commit_first_at,
        "commit_last_at": commit_last_at,
        "pr_number": None,
        "pr_title": None,
        "pr_url": None,
        "pr_base_ref": None,
        "pr_state": "pending_lookup" if not include_pr_lookup else "no_pr",
        "pr_merged_at": None,
        "pr_closed_at": None,
    }

    if merged_pr is not None:
        outcome["pr_number"] = merged_pr.get("number")
        outcome["pr_title"] = merged_pr.get("title")
        outcome["pr_url"] = merged_pr.get("url")
        outcome["pr_base_ref"] = merged_pr.get("baseRefName")
        outcome["pr_merged_at"] = merged_pr.get("mergedAt")
        outcome["pr_closed_at"] = merged_pr.get("closedAt")
        outcome["pr_state"] = "merged"
        return outcome

    if pr is None:
        if include_pr_lookup:
            outcome["pr_state"] = "no_pr"
        return outcome

    outcome["pr_number"] = pr.get("number")
    outcome["pr_title"] = pr.get("title")
    outcome["pr_url"] = pr.get("url")
    outcome["pr_base_ref"] = pr.get("baseRefName")
    outcome["pr_merged_at"] = pr.get("mergedAt")
    outcome["pr_closed_at"] = pr.get("closedAt")

    if pr.get("mergedAt"):
        outcome["pr_state"] = "merged"
    elif pr.get("state") == "OPEN":
        outcome["pr_state"] = "open"
    elif pr.get("closedAt"):
        outcome["pr_state"] = "closed"
    else:
        outcome["pr_state"] = "no_pr"

    return outcome


def _branch_cache_path(config: ChatpropConfig) -> Path:
    return config.state_dir.expanduser() / "cache" / "branch_outcomes.json"


def _load_branch_cache(config: ChatpropConfig) -> dict[str, dict[str, Any]]:
    payload = _read_json_dict(_branch_cache_path(config))
    entries = payload.get("branches")
    if not isinstance(entries, dict):
        return {}
    parsed: dict[str, dict[str, Any]] = {}
    for branch, value in entries.items():
        if isinstance(branch, str) and isinstance(value, dict):
            parsed[branch] = value
    return parsed


def _write_branch_cache(config: ChatpropConfig, entries: dict[str, dict[str, Any]]) -> None:
    path = _branch_cache_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": _iso_utc(datetime.now(tz=UTC)),
        "branches": entries,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _cached_outcome_is_fresh(entry: dict[str, Any]) -> bool:
    fetched_at = _parse_datetime(entry.get("fetched_at") if isinstance(entry.get("fetched_at"), str) else None)
    if fetched_at is None:
        return False
    return datetime.now(tz=UTC) - fetched_at <= CATALOG_CACHE_TTL


def _get_branch_outcome(
    branch: str,
    *,
    cache: dict[str, dict[str, Any]],
    refresh: bool,
    merged_pr_lookup: dict[str, dict[str, dict[str, Any]]] | None,
    repo: str | None,
    repos: list[str] | None,
) -> dict[str, Any]:
    cached = cache.get(branch)
    if not refresh and cached:
        if (
            cached.get("pr_state") != "merged"
            and merged_pr_lookup
            and _find_merged_pr_match(branch=branch, repo=repo, repos=repos, merged_pr_lookup=merged_pr_lookup)
        ):
            outcome = _branch_outcome_from_sources(
                branch,
                repo=repo,
                repos=repos,
                include_pr_lookup=False,
                include_commit_lookup=False,
                merged_pr_lookup=merged_pr_lookup,
            )
            outcome["fetched_at"] = cached.get("fetched_at")
            if outcome.get("commit_first_at") is None:
                outcome["commit_first_at"] = cached.get("commit_first_at")
            if outcome.get("commit_last_at") is None:
                outcome["commit_last_at"] = cached.get("commit_last_at")
            cache[branch] = outcome
            return outcome
        return cached

    outcome = _branch_outcome_from_sources(
        branch,
        repo=repo,
        repos=repos,
        include_pr_lookup=refresh,
        include_commit_lookup=refresh,
        merged_pr_lookup=merged_pr_lookup,
    )
    outcome["fetched_at"] = _iso_utc(datetime.now(tz=UTC))
    cache[branch] = outcome
    return outcome


def _clean_catalog_jobs(now: datetime) -> None:
    stale_job_ids: list[str] = []
    for job_id, job in _catalog_jobs.items():
        updated_at = _parse_datetime(job["updated_at"])
        if updated_at is None:
            stale_job_ids.append(job_id)
            continue
        if now - updated_at > CATALOG_JOB_TTL:
            stale_job_ids.append(job_id)
    for job_id in stale_job_ids:
        _catalog_jobs.pop(job_id, None)


def _set_catalog_job_state(job_id: str, updates: dict[str, Any]) -> None:
    with _catalog_jobs_lock:
        job = _catalog_jobs.get(job_id)
        if job is None:
            return
        job.update(updates)
        job["updated_at"] = _iso_utc(datetime.now(tz=UTC))


def _create_catalog_job(refresh: bool) -> dict[str, Any]:
    job_id = uuid.uuid4().hex
    now = _iso_utc(datetime.now(tz=UTC))
    job = {
        "job_id": job_id,
        "status": "running",
        "refresh": refresh,
        "created_at": now,
        "updated_at": now,
        "phase": "queued",
        "phase_processed": 0,
        "phase_total": 0,
        "phase_percent": 0.0,
        "overall_percent": 0.0,
        "message": "Queued",
        "result": None,
        "error": None,
    }
    with _catalog_jobs_lock:
        _clean_catalog_jobs(datetime.now(tz=UTC))
        _catalog_jobs[job_id] = job

    thread = threading.Thread(
        target=_run_catalog_job,
        args=(job_id, refresh),
        daemon=True,
    )
    thread.start()
    return job


def _get_catalog_job(job_id: str) -> dict[str, Any] | None:
    with _catalog_jobs_lock:
        job = _catalog_jobs.get(job_id)
        if job is None:
            return None
        return dict(job)


def _run_catalog_job(job_id: str, refresh: bool) -> None:
    config = load_config()

    def _progress(
        *,
        phase: str,
        phase_processed: int,
        phase_total: int,
        phase_percent: float,
        overall_percent: float,
        message: str,
    ) -> None:
        _set_catalog_job_state(
            job_id,
            {
                "phase": phase,
                "phase_processed": phase_processed,
                "phase_total": phase_total,
                "phase_percent": phase_percent,
                "overall_percent": overall_percent,
                "message": message,
            },
        )

    try:
        payload = _build_catalog(config, refresh=refresh, on_progress=_progress)
    except Exception as exc:  # noqa: BLE001
        _set_catalog_job_state(
            job_id,
            {
                "status": "failed",
                "error": str(exc),
                "message": f"Catalog failed: {exc}",
                "overall_percent": 100.0,
                "phase_percent": 100.0,
            },
        )
        return

    _set_catalog_job_state(
        job_id,
        {
            "status": "completed",
            "phase": "done",
            "phase_processed": 1,
            "phase_total": 1,
            "phase_percent": 100.0,
            "overall_percent": 100.0,
            "message": "Catalog ready",
            "result": payload,
            "error": None,
        },
    )


def _build_catalog(
    config: ChatpropConfig,
    refresh: bool = False,
    on_progress: Callable[..., None] | None = None,
) -> dict[str, Any]:
    index_reverse = _read_archive_index(config)
    metadata_windows = _read_archive_metadata_windows(config)
    archive_transcript_root = (config.state_dir.expanduser() / "archive" / "transcripts").resolve()
    transcripts = scan_archived(config)

    sessions: list[dict[str, Any]] = []
    branch_rows: dict[str, dict[str, Any]] = {}
    transcript_total = len(transcripts)
    repo_lookup_cache: dict[str, str | None] = {}

    def _emit_progress(
        *,
        phase: str,
        phase_processed: int,
        phase_total: int,
        phase_message: str,
    ) -> None:
        if on_progress is None:
            return
        safe_total = phase_total if phase_total > 0 else 1
        phase_percent = min(100.0, max(0.0, (phase_processed / safe_total) * 100.0))
        if refresh:
            if phase == "scan_transcripts":
                overall_percent = phase_percent * 0.8
            elif phase == "refresh_merged_prs":
                overall_percent = 80.0 + (phase_percent * 0.1)
            elif phase == "enrich_branches":
                overall_percent = 90.0 + (phase_percent * 0.1)
            else:
                overall_percent = phase_percent
        else:
            overall_percent = phase_percent
        on_progress(
            phase=phase,
            phase_processed=phase_processed,
            phase_total=phase_total,
            phase_percent=phase_percent,
            overall_percent=overall_percent,
            message=phase_message,
        )

    _emit_progress(
        phase="scan_transcripts",
        phase_processed=0,
        phase_total=transcript_total,
        phase_message=f"Scanning logs 0/{transcript_total}",
    )

    for index, transcript in enumerate(transcripts, start=1):
        resolved = transcript.path.resolve()
        indexed_branches = sorted(
            {
                normalized
                for normalized in (
                    _normalize_catalog_branch_name(branch) for branch in index_reverse.get(resolved, set())
                )
                if normalized
            }
        )
        should_infer_segments = not indexed_branches or len(indexed_branches) > 1
        segments = extract_branch_segments_from_transcript(transcript.path) if should_infer_segments else []

        inferred_branches = extract_work_branches_from_segments(segments) if segments else []
        if inferred_branches:
            branches = inferred_branches
        elif indexed_branches:
            branches = indexed_branches
        else:
            branches = sorted(
                {
                    normalized
                    for normalized in (
                        _normalize_catalog_branch_name(branch)
                        for branch in extract_branches_from_transcript(transcript.path)
                    )
                    if normalized
                }
            )
        branch_set = set(branches)
        branch_sequence = [segment.branch for segment in segments]
        if not branch_sequence:
            branch_sequence = list(branches)
        feature_chunks = build_feature_chunks_from_segments(segments)

        started_at: str
        ended_at: str
        try:
            resolved.relative_to(archive_transcript_root)
            in_archive = True
        except ValueError:
            in_archive = False

        if in_archive:
            session_key = _parse_archived_session_id(resolved)
            window = metadata_windows.get(session_key)
            if window is not None:
                started_at, ended_at = window
            else:
                started_at, ended_at = _mtime_window(transcript.path)
        else:
            started_at, ended_at = _extract_session_window(transcript.path)
        cwd = _extract_session_cwd(transcript.path)
        repo = _repo_from_cwd(cwd, cache=repo_lookup_cache) if cwd else None
        session_segments = segments
        if not session_segments and len(branches) == 1:
            session_segments = [
                BranchSegment(
                    branch=branches[0],
                    started_at=started_at,
                    ended_at=ended_at,
                )
            ]
            feature_chunks = build_feature_chunks_from_segments(session_segments)

        sessions.append(
            {
                "session_id": transcript.session_id,
                "source": transcript.source,
                "path": str(transcript.path),
                "size_bytes": transcript.size_bytes,
                "started_at": started_at,
                "ended_at": ended_at,
                "cwd": cwd,
                "repo": repo,
                "branches": list(branches),
                "branch_sequence": branch_sequence,
                "branch_chunks": [
                    {
                        "branch": segment.branch,
                        "started_at": segment.started_at,
                        "ended_at": segment.ended_at,
                    }
                    for segment in session_segments
                ],
                "feature_chunks": feature_chunks,
                "_branch_segments_internal": [
                    {
                        "branch": segment.branch,
                        "started_at": segment.started_at,
                        "ended_at": segment.ended_at,
                    }
                    for segment in session_segments
                ],
            }
        )

        for branch in branch_set:
            row = branch_rows.setdefault(
                branch,
                {
                    "name": branch,
                    "transcript_count": 0,
                    "session_ids": set(),
                    "first_seen_at": started_at,
                    "last_seen_at": ended_at,
                    "repo_counts": {},
                },
            )
            row["transcript_count"] += 1
            row["session_ids"].add(transcript.session_id)
            if repo:
                repo_counts = row["repo_counts"]
                if isinstance(repo_counts, dict):
                    repo_counts[repo] = int(repo_counts.get(repo, 0)) + 1

            first_seen = _parse_datetime(row["first_seen_at"])
            current_start = _parse_datetime(started_at)
            if first_seen and current_start and current_start < first_seen:
                row["first_seen_at"] = started_at

            last_seen = _parse_datetime(row["last_seen_at"])
            current_end = _parse_datetime(ended_at)
            if last_seen and current_end and current_end > last_seen:
                row["last_seen_at"] = ended_at

        if index == transcript_total or index % 25 == 0:
            _emit_progress(
                phase="scan_transcripts",
                phase_processed=index,
                phase_total=transcript_total,
                phase_message=f"Scanning logs {index}/{transcript_total}",
            )

    cache = _load_branch_cache(config)
    merged_pr_lookup = _load_merged_pr_index(config)
    earliest_session_start: datetime | None = None
    for session in sessions:
        started_at = session.get("started_at")
        if not isinstance(started_at, str):
            continue
        parsed_start = _parse_datetime(started_at)
        if parsed_start is None:
            continue
        if earliest_session_start is None or parsed_start < earliest_session_start:
            earliest_session_start = parsed_start
    fallback_since = earliest_session_start.date().isoformat() if earliest_session_start else None
    if refresh:
        _emit_progress(
            phase="refresh_merged_prs",
            phase_processed=0,
            phase_total=1,
            phase_message=f"Refreshing merged PR index for @{DEFAULT_GH_AUTHOR}",
        )
        merged_pr_lookup = _refresh_merged_pr_cache(
            config,
            author=DEFAULT_GH_AUTHOR,
            fallback_since=fallback_since,
        )
        _emit_progress(
            phase="refresh_merged_prs",
            phase_processed=1,
            phase_total=1,
            phase_message=f"Refreshed merged PR index for @{DEFAULT_GH_AUTHOR}",
        )

    branch_names = list(branch_rows)
    branch_total = len(branch_names)
    if refresh:
        _emit_progress(
            phase="enrich_branches",
            phase_processed=0,
            phase_total=branch_total,
            phase_message=f"Enriching branches 0/{branch_total}",
        )

    for index, branch in enumerate(branch_names, start=1):
        row = branch_rows[branch]
        repo_counts_raw = row.get("repo_counts", {})
        repo_pairs: list[tuple[str, int]] = []
        if isinstance(repo_counts_raw, dict):
            for repo_name, count in repo_counts_raw.items():
                if isinstance(repo_name, str) and repo_name.strip() and isinstance(count, int):
                    repo_pairs.append((repo_name.strip(), count))
        repo_pairs.sort(key=lambda item: (-item[1], item[0]))
        primary_repo = repo_pairs[0][0] if repo_pairs else None
        repo_names = [name for name, _ in repo_pairs]

        outcome = _get_branch_outcome(
            branch,
            cache=cache,
            refresh=refresh,
            merged_pr_lookup=merged_pr_lookup,
            repo=primary_repo,
            repos=repo_names,
        )
        row.pop("repo_counts", None)

        row["session_count"] = len(row["session_ids"])
        row["session_ids"] = sorted(row["session_ids"])
        row["repo"] = primary_repo
        row["repos"] = repo_names
        row["feature_count"] = 0
        row["revision_feature_count"] = 0
        row["sessions_with_revision_count"] = 0
        row.update(
            {
                "commit_first_at": outcome.get("commit_first_at"),
                "commit_last_at": outcome.get("commit_last_at"),
                "pr_number": outcome.get("pr_number"),
                "pr_title": outcome.get("pr_title"),
                "pr_url": outcome.get("pr_url"),
                "pr_base_ref": outcome.get("pr_base_ref"),
                "pr_state": outcome.get("pr_state"),
                "pr_merged_at": outcome.get("pr_merged_at"),
                "pr_closed_at": outcome.get("pr_closed_at"),
                "fetched_at": outcome.get("fetched_at"),
            }
        )
        if refresh and (index == branch_total or index % 10 == 0):
            _emit_progress(
                phase="enrich_branches",
                phase_processed=index,
                phase_total=branch_total,
                phase_message=f"Enriching branches {index}/{branch_total}",
            )

    merged_branches = {name for name, row in branch_rows.items() if row.get("pr_state") == "merged"}
    explicit_skills = load_explicit_skills(_repo_root_for_explicit_skills())
    skill_graph = SkillGraphAccumulator(explicit_skills)
    feature_rollups: dict[str, dict[str, Any]] = {}

    for session in sessions:
        raw_segments = session.pop("_branch_segments_internal", [])
        segments: list[BranchSegment] = []
        if isinstance(raw_segments, list):
            for raw in raw_segments:
                if not isinstance(raw, dict):
                    continue
                branch = raw.get("branch")
                started_at = raw.get("started_at")
                ended_at = raw.get("ended_at")
                if isinstance(branch, str):
                    segments.append(
                        BranchSegment(
                            branch=branch,
                            started_at=started_at if isinstance(started_at, str) else None,
                            ended_at=ended_at if isinstance(ended_at, str) else None,
                        )
                    )

        if segments:
            try:
                analyzed_chunks = analyze_session_feature_chunks(
                    transcript_path=Path(str(session["path"])),
                    branch_segments=segments,
                    explicit_skills=explicit_skills,
                )
            except OSError:
                analyzed_chunks = build_feature_chunks_from_segments(segments)
            session["feature_chunks"] = analyzed_chunks
        elif not session.get("feature_chunks"):
            session["feature_chunks"] = build_feature_chunks_from_segments(segments)

        feature_chunks = session.get("feature_chunks", [])
        revision_feature_count = 0
        feature_count = 0
        if isinstance(feature_chunks, list):
            for chunk in feature_chunks:
                if not isinstance(chunk, dict):
                    continue
                branch = chunk.get("branch")
                if not isinstance(branch, str):
                    continue
                is_merged_branch = branch in merged_branches
                chunk["is_merged_branch"] = is_merged_branch
                feature_count += 1
                has_revision = chunk.get("has_revision") is True
                if has_revision:
                    revision_feature_count += 1
                skill_graph.add_feature_chunk(
                    session_id=str(session.get("session_id", "")),
                    repo=session.get("repo") if isinstance(session.get("repo"), str) else None,
                    chunk=chunk,
                    include_revision_prevention=is_merged_branch,
                )
                rollup = feature_rollups.setdefault(
                    branch,
                    {
                        "feature_count": 0,
                        "revision_feature_count": 0,
                        "sessions_with_revision": set(),
                    },
                )
                rollup["feature_count"] = int(rollup["feature_count"]) + 1
                if has_revision:
                    rollup["revision_feature_count"] = int(rollup["revision_feature_count"]) + 1
                    sessions_with_revision = rollup.get("sessions_with_revision")
                    if isinstance(sessions_with_revision, set):
                        sessions_with_revision.add(str(session.get("session_id", "")))

        session["feature_count"] = feature_count
        session["revision_feature_count"] = revision_feature_count

    for branch, rollup in feature_rollups.items():
        row = branch_rows.get(branch)
        if row is None:
            continue
        row["feature_count"] = int(rollup.get("feature_count", 0))
        row["revision_feature_count"] = int(rollup.get("revision_feature_count", 0))
        sessions_with_revision = rollup.get("sessions_with_revision")
        row["sessions_with_revision_count"] = (
            len(sessions_with_revision) if isinstance(sessions_with_revision, set) else 0
        )

    _write_branch_cache(config, cache)

    sessions.sort(key=lambda row: row.get("ended_at") or "", reverse=True)
    branches_sorted = sorted(
        branch_rows.values(),
        key=lambda row: row.get("last_seen_at") or "",
        reverse=True,
    )

    workflow_graph = {
        **skill_graph.to_dict(),
        "graph_scope": "all_feature_chunks",
        "revision_prevention_scope": "merged_feature_chunks_only",
    }
    flowchart_options = {
        "min_node_count": DEFAULT_FLOWCHART_MIN_NODE_COUNT,
        "min_edge_count": DEFAULT_FLOWCHART_MIN_EDGE_COUNT,
        "max_nodes": DEFAULT_FLOWCHART_MAX_NODES,
        "max_edges": DEFAULT_FLOWCHART_MAX_EDGES,
    }
    flowchart_payload = _flowchart_payload(
        workflow_graph,
        options=flowchart_options,
        session_count=len(sessions),
        branch_count=len(branches_sorted),
    )

    return {
        "generated_at": _iso_utc(datetime.now(tz=UTC)),
        "session_count": len(sessions),
        "branch_count": len(branches_sorted),
        "sessions": sessions,
        "branches": branches_sorted,
        "workflow_graph": workflow_graph,
        "workflow_flowchart": flowchart_payload,
    }


def build_catalog_snapshot(
    config: ChatpropConfig | None = None,
    *,
    refresh: bool = False,
) -> dict[str, Any]:
    """Public helper for one-off local catalog analysis/export."""
    resolved = config or load_config()
    return _build_catalog(resolved, refresh=refresh)


@dataclass
class ServerConfig:
    host: str
    port: int


class ChatPropHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path in {"", "/"}:
            self._serve_file("index.html", is_static=False)
            return

        if self.path.startswith("/static/"):
            file_name = self.path[len("/static/") :]
            self._serve_file(file_name, is_static=True)
            return

        if self.path == "/api/health":
            self._serve_json({"ok": True})
            return

        if self.path.startswith("/api/catalog/jobs/"):
            self._serve_catalog_job_status()
            return

        if self.path.startswith("/api/catalog"):
            self._serve_catalog()
            return

        self.send_error(404, "Not found")

    def do_POST(self) -> None:
        if self.path == "/api/catalog/jobs":
            self._serve_catalog_job_create()
            return
        if self.path == "/api/analysis/find":
            self._serve_analysis_find()
            return
        if self.path == "/api/analysis/context":
            self._serve_analysis_context()
            return
        if self.path == "/api/analysis/run":
            self._serve_analysis_run()
            return
        if self.path == "/api/flowchart/render":
            self._serve_flowchart_render()
            return
        if self.path == "/api/flowchart/save":
            self._serve_flowchart_save()
            return

        self.send_error(404, "Not found")

    def _query_params(self) -> dict[str, list[str]]:
        return urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)

    def _read_json_body(self) -> dict[str, Any] | None:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length > 0 else b""
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            self.send_error(400, "Invalid request body")
            return None
        if not isinstance(payload, dict):
            self.send_error(400, "Request body must be a JSON object")
            return None
        return payload

    def _read_analysis_branches(self) -> list[str] | None:
        if self.command != "POST":
            self.send_error(405, "Method not allowed")
            return None

        payload = self._read_json_body()
        if payload is None:
            return None

        branches = _extract_branches(payload)
        if not branches:
            self.send_error(400, "branches must be a non-empty list of strings")
            return None
        return branches

    def _serve_analysis_find(self) -> None:
        branches = self._read_analysis_branches()
        if branches is None:
            return

        config = load_config()
        matches = find_transcripts_for_branches(config, branches)
        self._serve_json(
            {
                "branches": branches,
                "count": len(matches),
                "matches": [
                    {
                        "path": str(match.path),
                        "source": match.source,
                        "session_id": match.session_id,
                        "size_bytes": match.size_bytes,
                        "matched_branches": match.matched_branches,
                    }
                    for match in matches
                ],
            }
        )

    def _serve_analysis_context(self) -> None:
        branches = self._read_analysis_branches()
        if branches is None:
            return

        config = load_config()
        context = build_analysis_context(branches, config)
        self._serve_json(
            {
                "branches": branches,
                "length": len(context),
                "context": context,
            }
        )

    def _serve_analysis_run(self) -> None:
        branches = self._read_analysis_branches()
        if branches is None:
            return

        config = load_config()
        output = run_analysis(branches, config)
        if not output.strip():
            self.send_error(502, "analysis produced no output")
            return

        self._serve_json(
            {
                "branches": branches,
                "output": output,
            }
        )

    def _resolve_flowchart_graph(
        self,
        graph_raw: Any,
        *,
        config: ChatpropConfig | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any] | None] | None:
        if graph_raw is not None and not isinstance(graph_raw, dict):
            self.send_error(400, "workflow_graph must be an object")
            return None

        workflow_graph = graph_raw
        catalog: dict[str, Any] | None = None
        if workflow_graph is None:
            resolved_config = config or load_config()
            catalog = _build_catalog(resolved_config, refresh=False)
            workflow_graph = catalog.get("workflow_graph")
            if not isinstance(workflow_graph, dict):
                self.send_error(500, "Catalog missing workflow graph")
                return None

        return workflow_graph, catalog

    def _serve_flowchart_render(self) -> None:
        payload = self._read_json_body()
        if payload is None:
            return

        options = _flowchart_options_from_payload(payload)
        if options is None:
            self.send_error(400, "Invalid flowchart options")
            return

        resolved = self._resolve_flowchart_graph(payload.get("workflow_graph"))
        if resolved is None:
            return
        workflow_graph, catalog = resolved
        rendered = _flowchart_payload_with_catalog(workflow_graph, options=options, catalog=catalog)
        self._serve_json(rendered)

    def _serve_flowchart_save(self) -> None:
        payload = self._read_json_body()
        if payload is None:
            return

        options = _flowchart_options_from_payload(payload)
        if options is None:
            self.send_error(400, "Invalid flowchart options")
            return

        config = load_config()
        resolved = self._resolve_flowchart_graph(payload.get("workflow_graph"), config=config)
        if resolved is None:
            return
        workflow_graph, catalog = resolved
        rendered = _flowchart_payload_with_catalog(workflow_graph, options=options, catalog=catalog)

        default_mermaid_path, default_json_path = _flowchart_export_defaults(config)
        mermaid_path_raw = payload.get("mermaid_path")
        json_path_raw = payload.get("json_path")

        mermaid_path = _parse_output_path(mermaid_path_raw)
        if mermaid_path is None:
            if mermaid_path_raw is not None and not (
                isinstance(mermaid_path_raw, str) and not mermaid_path_raw.strip()
            ):
                self.send_error(400, "mermaid_path must be a path string")
                return
            mermaid_path = default_mermaid_path

        json_path = _parse_output_path(json_path_raw)
        if json_path is None:
            if json_path_raw is None:
                json_path = default_json_path
            elif not (isinstance(json_path_raw, str) and not json_path_raw.strip()):
                self.send_error(400, "json_path must be a path string")
                return

        write_flowchart_outputs(payload=rendered, mermaid_path=mermaid_path, json_path=json_path)
        self._serve_json(
            {
                "saved": True,
                "mermaid_path": str(mermaid_path),
                "json_path": str(json_path) if json_path is not None else None,
                "node_count": rendered["selected_graph"]["node_count"],
                "edge_count": rendered["selected_graph"]["edge_count"],
                "generated_at": rendered["generated_at"],
            }
        )

    def _serve_catalog(self) -> None:
        params = self._query_params()
        refresh = params.get("refresh", ["0"])[0] in {"1", "true", "yes"}

        config = load_config()
        payload = _build_catalog(config, refresh=refresh)
        self._serve_json(payload)

    def _serve_catalog_job_create(self) -> None:
        payload = self._read_json_body()
        if payload is None:
            return
        refresh = payload.get("refresh") in {True, "1", "true", "yes"}
        job = _create_catalog_job(bool(refresh))
        self._serve_json(job)

    def _serve_catalog_job_status(self) -> None:
        path = urllib.parse.urlparse(self.path).path
        prefix = "/api/catalog/jobs/"
        if not path.startswith(prefix):
            self.send_error(404, "Not found")
            return
        job_id = path[len(prefix) :].strip()
        if not job_id:
            self.send_error(404, "Not found")
            return
        job = _get_catalog_job(job_id)
        if job is None:
            self.send_error(404, "Unknown catalog job")
            return
        self._serve_json(job)

    def _serve_json(self, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False)
        encoded = data.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _serve_file(self, file_name: str, *, is_static: bool) -> None:
        base = FRONTEND_ROOT / ("static" if is_static else "templates")
        target = _resolve_frontend_target(base, file_name)

        if target is None or not target.exists() or not target.is_file():
            self.send_error(404, "Missing file")
            return

        mime_type, _ = mimetypes.guess_type(str(target))
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime_type or "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return


def run_server(args: argparse.Namespace) -> None:
    config = ServerConfig(host=args.host, port=args.port)
    server = ThreadingHTTPServer((config.host, config.port), ChatPropHandler)
    print(f"chatprop: serving on http://{config.host}:{config.port}", flush=True)
    with contextlib.suppress(KeyboardInterrupt):
        server.serve_forever()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run chatprop webserver")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    run_server(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
