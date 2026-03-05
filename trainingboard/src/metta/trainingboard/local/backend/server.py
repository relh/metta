"""Small localhost server for the trainingboard six-axis dashboard."""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional

from metta.trainingboard.llm_scoring import default_llm_cache_path, load_llm_score_cache
from metta.trainingboard.models import LLMTaskScores
from metta.trainingboard.scoring import (
    build_dashboard_snapshot,
    build_task_leaderboards,
    build_task_ranking_snapshot,
    load_cached_papers,
)

FRONTEND_ROOT = Path(__file__).resolve().parents[1] / "frontend"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8877
DEFAULT_STATE_DIR = Path("~/.trainingboard").expanduser()
DEFAULT_CACHE_RELATIVE_PATH = Path("cache/asana_research_cache.ndjson")
DEFAULT_REPO_CACHE_FILE_NAME = "asana_research_cache.ndjson"
DEFAULT_REPO_LLM_CACHE_FILE_NAME = "task_llm_scores.ndjson"
REPO_CACHE_DIRECTORY = Path("trainingboard/data")


def cache_path_for_state_dir(state_dir: Path) -> Path:
    return state_dir.expanduser() / DEFAULT_CACHE_RELATIVE_PATH


def llm_cache_path_for_state_dir(state_dir: Path) -> Path:
    return default_llm_cache_path(state_dir)


def _discover_repo_cache_dir() -> Optional[Path]:
    module_path = Path(__file__).resolve()
    for parent in module_path.parents:
        candidate = parent / REPO_CACHE_DIRECTORY
        if candidate.is_dir():
            return candidate

    cwd = Path.cwd().resolve()
    for parent in (cwd, *cwd.parents):
        candidate = parent / REPO_CACHE_DIRECTORY
        if candidate.is_dir():
            return candidate
    return None


def default_repo_cache_path(state_dir: Optional[Path] = None) -> Path:
    repo_cache_dir = _discover_repo_cache_dir()
    if repo_cache_dir is not None:
        return repo_cache_dir / DEFAULT_REPO_CACHE_FILE_NAME
    if state_dir is None:
        state_dir = DEFAULT_STATE_DIR
    return cache_path_for_state_dir(state_dir)


def default_repo_llm_cache_path(state_dir: Optional[Path] = None) -> Path:
    repo_cache_dir = _discover_repo_cache_dir()
    if repo_cache_dir is not None:
        return repo_cache_dir / DEFAULT_REPO_LLM_CACHE_FILE_NAME
    if state_dir is None:
        state_dir = DEFAULT_STATE_DIR
    return llm_cache_path_for_state_dir(state_dir)


def _prefer_newer_cache(state_path: Path, repo_path: Path) -> Path:
    if repo_path.is_file() and state_path.is_file():
        if repo_path.stat().st_mtime >= state_path.stat().st_mtime:
            return repo_path
        return state_path
    if repo_path.is_file():
        return repo_path
    if state_path.is_file():
        return state_path
    return repo_path


def dashboard_cache_path_for_state_dir(state_dir: Path) -> Path:
    state_cache_path = cache_path_for_state_dir(state_dir)
    repo_cache_path = default_repo_cache_path(state_dir)
    return _prefer_newer_cache(state_cache_path, repo_cache_path)


def task_ranking_llm_cache_path_for_state_dir(state_dir: Path) -> Path:
    state_llm_cache_path = llm_cache_path_for_state_dir(state_dir)
    repo_llm_cache_path = default_repo_llm_cache_path(state_dir)
    return _prefer_newer_cache(state_llm_cache_path, repo_llm_cache_path)


def _load_llm_scores_for_state_dir(state_dir: Path) -> tuple[Optional[dict[str, LLMTaskScores]], Path]:
    llm_cache_path = task_ranking_llm_cache_path_for_state_dir(state_dir)
    if not llm_cache_path.is_file():
        return None, llm_cache_path
    return (
        {gid: cache_entry.scores for gid, cache_entry in load_llm_score_cache(llm_cache_path).items()},
        llm_cache_path,
    )


def build_dashboard_for_state_dir(state_dir: Path) -> dict:
    papers = load_cached_papers(dashboard_cache_path_for_state_dir(state_dir))
    llm_scores_by_gid, llm_cache_path = _load_llm_scores_for_state_dir(state_dir)
    effective_llm_scores = llm_scores_by_gid or {}
    snapshot = build_dashboard_snapshot(papers, llm_scores_by_gid=effective_llm_scores)
    llm_scored_tasks = sum(1 for paper in papers if paper.gid in effective_llm_scores)
    total_tasks = len(papers)
    payload = snapshot.model_dump()
    payload["scoring_source"] = "llm_only"
    payload["llm_scored_tasks"] = llm_scored_tasks
    payload["tasks_total"] = total_tasks
    payload["llm_coverage"] = round(llm_scored_tasks / total_tasks, 3) if total_tasks > 0 else 0.0
    payload["llm_cache_path"] = str(llm_cache_path)
    return payload


def build_task_ranking_for_state_dir(state_dir: Path, limit: int = 60, leaderboard_top_n: int = 10) -> dict:
    papers = load_cached_papers(dashboard_cache_path_for_state_dir(state_dir))
    llm_scores_by_gid, llm_cache_path = _load_llm_scores_for_state_dir(state_dir)
    full_snapshot = build_task_ranking_snapshot(
        papers,
        limit=None,
        llm_scores_by_gid=llm_scores_by_gid or {},
        require_llm_scores=True,
    )
    leaderboards = build_task_leaderboards(full_snapshot.ranked_tasks, top_n=leaderboard_top_n)
    payload = full_snapshot.model_dump()
    payload["ranked_tasks"] = payload["ranked_tasks"][: max(0, limit)]
    payload["leaderboards"] = {
        "top_overall": [task.model_dump() for task in leaderboards["top_overall"]],
        "top_by_axis": {
            axis_id: [task.model_dump() for task in tasks] for axis_id, tasks in leaderboards["top_by_axis"].items()
        },
    }
    payload["llm_cache_path"] = str(llm_cache_path)
    return payload


def build_board_payload_for_state_dir(state_dir: Path) -> dict:
    return {
        "dashboard": build_dashboard_for_state_dir(state_dir),
        "task_ranking": build_task_ranking_for_state_dir(state_dir),
    }


def _resolve_frontend_target(base: Path, file_name: str) -> Optional[Path]:
    raw_target = Path(file_name)
    if raw_target.is_absolute() or ".." in raw_target.parts:
        return None
    target = (base / raw_target).resolve()
    try:
        target.relative_to(base.resolve())
    except ValueError:
        return None
    return target


def _query_int(
    query_params: dict[str, list[str]],
    *,
    key: str,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    if key not in query_params or not query_params[key]:
        return default
    raw = query_params[key][0]
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(minimum, min(maximum, value))


class TrainingBoardHTTPServer(ThreadingHTTPServer):
    state_dir: Path


class TrainingBoardHandler(BaseHTTPRequestHandler):
    server: TrainingBoardHTTPServer

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        query_params = urllib.parse.parse_qs(parsed.query)
        if parsed.path == "/":
            self._serve_file(FRONTEND_ROOT / "templates" / "index.html", "text/html; charset=utf-8")
            return

        if parsed.path == "/api/v1/dashboard":
            self._write_json(200, build_dashboard_for_state_dir(self.server.state_dir))
            return

        if parsed.path == "/api/v1/task-ranking":
            limit = _query_int(query_params, key="limit", default=60, minimum=0, maximum=1000)
            top_n = _query_int(query_params, key="top_n", default=10, minimum=0, maximum=100)
            self._write_json(
                200,
                build_task_ranking_for_state_dir(self.server.state_dir, limit=limit, leaderboard_top_n=top_n),
            )
            return

        if parsed.path == "/api/v1/board":
            self._write_json(200, build_board_payload_for_state_dir(self.server.state_dir))
            return

        if parsed.path.startswith("/static/"):
            file_name = parsed.path.removeprefix("/static/")
            target = _resolve_frontend_target(FRONTEND_ROOT / "static", file_name)
            if target is None or not target.is_file():
                self._write_json(404, {"error": "static asset not found"})
                return
            mime_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
            self._serve_file(target, mime_type)
            return

        self._write_json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/v1/recompute":
            self._write_json(200, build_board_payload_for_state_dir(self.server.state_dir))
            return
        self._write_json(404, {"error": "not found"})

    def _serve_file(self, path: Path, content_type: str) -> None:
        payload = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _write_json(self, status_code: int, payload: dict) -> None:
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run trainingboard local dashboard server")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--state-dir", default=str(DEFAULT_STATE_DIR))
    return parser.parse_args(argv)


def run_server(args: argparse.Namespace) -> None:
    host = args.host
    port = args.port
    state_dir = Path(args.state_dir).expanduser()

    httpd = TrainingBoardHTTPServer((host, port), TrainingBoardHandler)
    httpd.state_dir = state_dir

    print(f"trainingboard server listening on http://{host}:{port}")
    print(f"state dir: {state_dir}")
    print(f"cache: {dashboard_cache_path_for_state_dir(state_dir)}")
    httpd.serve_forever()


if __name__ == "__main__":
    run_server(parse_args(sys.argv[1:]))
