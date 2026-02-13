from __future__ import annotations

import argparse
import json
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

DefectStatus = Literal["open", "triaged", "fixed", "dismissed"]

AUTH_MARKERS = (
    "not authenticated",
    "authentication failed",
    "token",
    "unauthorized",
    "forbidden",
    "run: cogames login",
)


class CrashDefect(BaseModel):
    defect_id: str
    submitted_at: datetime
    reporter: str
    command: str
    observed_error: str
    stacktrace: str | None = None
    context: str | None = None
    season: str | None = None
    policy_name: str | None = None
    likely_owner: str
    proposed_fix: str
    status: DefectStatus = "open"


class DefectBacklogItem(BaseModel):
    signature: str
    count: int
    likely_owner: str
    recommended_fix: str


class DefectBacklog(BaseModel):
    generated_at: datetime
    defects_path: str
    total_defects: int
    open_defects: int
    status_counts: dict[str, int]
    top_signatures: list[DefectBacklogItem]


class DefectIntakeConfig(BaseModel):
    store_dir: Path = Path("./artifacts/ai_researcher/defects")


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _looks_like_auth_failure(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in AUTH_MARKERS)


def _likely_owner(observed_error: str) -> str:
    return "auth" if _looks_like_auth_failure(observed_error) else "cogames-cli"


def _default_fix(likely_owner: str) -> str:
    if likely_owner == "auth":
        return "Refresh login token and rerun command with explicit login-server/server args."
    return "Reproduce with exact command and stderr, then patch root-cause in CLI/runtime path."


def _defects_path(store_dir: Path) -> Path:
    return store_dir / "crash_defects.jsonl"


def _backlog_path(store_dir: Path) -> Path:
    return store_dir / "defect_backlog.json"


def load_crash_defects(store_dir: Path) -> list[CrashDefect]:
    defects_path = _defects_path(store_dir)
    if not defects_path.exists():
        return []

    defects: list[CrashDefect] = []
    for line in defects_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        defects.append(CrashDefect.model_validate(json.loads(line)))
    return defects


def _write_crash_defects(store_dir: Path, defects: list[CrashDefect]) -> None:
    store_dir.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(defect.model_dump(mode="json")) for defect in defects]
    _defects_path(store_dir).write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def build_defect_backlog(store_dir: Path) -> DefectBacklog:
    defects = load_crash_defects(store_dir)

    status_counts = Counter(defect.status for defect in defects)
    by_signature = Counter((defect.observed_error, defect.likely_owner, defect.proposed_fix) for defect in defects)

    top_signatures = [
        DefectBacklogItem(
            signature=signature,
            count=count,
            likely_owner=likely_owner,
            recommended_fix=recommended_fix,
        )
        for (signature, likely_owner, recommended_fix), count in by_signature.most_common(10)
    ]

    backlog = DefectBacklog(
        generated_at=_utc_now(),
        defects_path=str(_defects_path(store_dir)),
        total_defects=len(defects),
        open_defects=status_counts.get("open", 0),
        status_counts=dict(status_counts),
        top_signatures=top_signatures,
    )
    _backlog_path(store_dir).write_text(json.dumps(backlog.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8")
    return backlog


def submit_crash_defect(
    *,
    store_dir: Path,
    reporter: str,
    command: str,
    observed_error: str,
    stacktrace: str | None = None,
    context: str | None = None,
    season: str | None = None,
    policy_name: str | None = None,
    proposed_fix: str | None = None,
) -> CrashDefect:
    store_dir.mkdir(parents=True, exist_ok=True)

    likely_owner = _likely_owner(observed_error)
    defect = CrashDefect(
        defect_id=f"defect-{_utc_now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}",
        submitted_at=_utc_now(),
        reporter=reporter,
        command=command,
        observed_error=observed_error,
        stacktrace=stacktrace,
        context=context,
        season=season,
        policy_name=policy_name,
        likely_owner=likely_owner,
        proposed_fix=proposed_fix or _default_fix(likely_owner),
        status="open",
    )

    defects = load_crash_defects(store_dir)
    defects.append(defect)
    _write_crash_defects(store_dir, defects)
    build_defect_backlog(store_dir)
    return defect


def set_defect_status(*, store_dir: Path, defect_id: str, status: DefectStatus) -> CrashDefect:
    defects = load_crash_defects(store_dir)
    for index, defect in enumerate(defects):
        if defect.defect_id != defect_id:
            continue
        updated = defect.model_copy(update={"status": status})
        defects[index] = updated
        _write_crash_defects(store_dir, defects)
        build_defect_backlog(store_dir)
        return updated
    raise ValueError(f"Defect not found: {defect_id}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Crash defect intake/backlog for AI RL researcher workflows")
    parser.add_argument("--store-dir", default="./artifacts/ai_researcher/defects")

    subparsers = parser.add_subparsers(dest="action", required=True)

    submit = subparsers.add_parser("submit", help="Submit a crash defect")
    submit.add_argument("--reporter", required=True)
    submit.add_argument("--command", required=True)
    submit.add_argument("--observed-error", required=True)
    submit.add_argument("--stacktrace", default=None)
    submit.add_argument("--context", default=None)
    submit.add_argument("--season", default=None)
    submit.add_argument("--policy-name", default=None)
    submit.add_argument("--proposed-fix", default=None)

    status = subparsers.add_parser("set-status", help="Update defect status")
    status.add_argument("--defect-id", required=True)
    status.add_argument("--status", choices=["open", "triaged", "fixed", "dismissed"], required=True)

    subparsers.add_parser("backlog", help="Regenerate backlog summary")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    store_dir = Path(args.store_dir)

    if args.action == "submit":
        defect = submit_crash_defect(
            store_dir=store_dir,
            reporter=args.reporter,
            command=args.command,
            observed_error=args.observed_error,
            stacktrace=args.stacktrace,
            context=args.context,
            season=args.season,
            policy_name=args.policy_name,
            proposed_fix=args.proposed_fix,
        )
        print(f"defect_id={defect.defect_id}")
        print(f"status={defect.status}")
        print(f"store={store_dir}")
        return 0

    if args.action == "set-status":
        defect = set_defect_status(store_dir=store_dir, defect_id=args.defect_id, status=args.status)
        print(f"defect_id={defect.defect_id}")
        print(f"status={defect.status}")
        return 0

    backlog = build_defect_backlog(store_dir)
    print(f"total_defects={backlog.total_defects}")
    print(f"open_defects={backlog.open_defects}")
    print(f"output={_backlog_path(store_dir)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
