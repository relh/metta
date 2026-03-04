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

from metta.trainingboard.scoring import build_dashboard_snapshot_from_cache

FRONTEND_ROOT = Path(__file__).resolve().parents[1] / "frontend"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8877
DEFAULT_STATE_DIR = Path("~/.trainingboard").expanduser()
DEFAULT_CACHE_RELATIVE_PATH = Path("cache/asana_research_cache.json")


def cache_path_for_state_dir(state_dir: Path) -> Path:
    return state_dir.expanduser() / DEFAULT_CACHE_RELATIVE_PATH


def build_dashboard_for_state_dir(state_dir: Path) -> dict:
    snapshot = build_dashboard_snapshot_from_cache(cache_path_for_state_dir(state_dir))
    return snapshot.model_dump()


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


class TrainingBoardHTTPServer(ThreadingHTTPServer):
    state_dir: Path


class TrainingBoardHandler(BaseHTTPRequestHandler):
    server: TrainingBoardHTTPServer

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/":
            self._serve_file(FRONTEND_ROOT / "templates" / "index.html", "text/html; charset=utf-8")
            return

        if parsed.path == "/api/v1/dashboard":
            self._write_json(200, build_dashboard_for_state_dir(self.server.state_dir))
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
            self._write_json(200, build_dashboard_for_state_dir(self.server.state_dir))
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
    print(f"cache: {cache_path_for_state_dir(state_dir)}")
    httpd.serve_forever()


if __name__ == "__main__":
    run_server(parse_args(sys.argv[1:]))
