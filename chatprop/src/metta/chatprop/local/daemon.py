"""Transcript collection daemon for chatprop (local-first)."""

from __future__ import annotations

import json
import shutil
import tempfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from metta.chatprop.config import ChatPropConfig
from metta.chatprop.local.indexer import add_transcript_to_index, extract_branches_from_transcript
from metta.chatprop.local.models import BranchIndex, ManifestEntry, TranscriptMetadata, TranscriptSource, utc_now_iso


@dataclass(frozen=True)
class DaemonRunStats:
    scanned_files: int
    archived_files: int
    skipped_unchanged: int
    skipped_active: int


@dataclass(frozen=True)
class DaemonStatus:
    state_dir: Path
    archive_root: Path
    transcript_count: int
    metadata_count: int
    indexed_branch_count: int
    manifest_entry_count: int


def _archive_root(config: ChatPropConfig) -> Path:
    return config.state_dir.expanduser() / "archive"


def _manifest_path(config: ChatPropConfig) -> Path:
    return config.state_dir.expanduser() / "manifest.json"


def _index_path(config: ChatPropConfig) -> Path:
    return _archive_root(config) / "index.json"


def _archive_transcript_key(source: TranscriptSource, session_id: str, mtime_ns: int) -> str:
    return f"transcripts/{source}/{session_id}-{mtime_ns}.jsonl"


def _archive_metadata_key(session_id: str) -> str:
    return f"metadata/{session_id}.json"


def _read_json_dict(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    try:
        raw = path.read_text(encoding="utf-8")
        parsed = json.loads(raw)
    except (OSError, json.JSONDecodeError):
        return {}
    if isinstance(parsed, dict):
        return parsed
    return {}


def _write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        tmp_path = Path(handle.name)
        json.dump(payload, handle, indent=2)
        handle.write("\n")
    tmp_path.replace(path)


def _read_index(config: ChatPropConfig) -> BranchIndex:
    path = _index_path(config)
    payload = _read_json_dict(path)
    branches_raw = payload.get("branches")
    branches: dict[str, list[str]] = {}
    if isinstance(branches_raw, dict):
        for branch, values in branches_raw.items():
            if isinstance(branch, str) and isinstance(values, list):
                clean_values = [value for value in values if isinstance(value, str)]
                if clean_values:
                    branches[branch] = clean_values
    updated_at = payload.get("updated_at")
    return BranchIndex(
        updated_at=updated_at if isinstance(updated_at, str) and updated_at else utc_now_iso(),
        branches=branches,
    )


def _write_index(config: ChatPropConfig, index: BranchIndex) -> None:
    path = _index_path(config)
    _write_json_atomic(path, index.to_dict())


def _read_manifest(config: ChatPropConfig) -> dict[str, ManifestEntry]:
    manifest_path = _manifest_path(config)
    raw = _read_json_dict(manifest_path)

    entries: dict[str, ManifestEntry] = {}
    for transcript_path, payload in raw.items():
        if not isinstance(transcript_path, str) or not isinstance(payload, dict):
            continue
        source = payload.get("source")
        mtime_ns = payload.get("mtime_ns")
        size_bytes = payload.get("size_bytes")
        uploaded_at = payload.get("uploaded_at")
        transcript_path_key = payload.get("transcript_path_key")
        if (
            source in {"claude-code", "codex"}
            and isinstance(mtime_ns, int)
            and isinstance(size_bytes, int)
            and isinstance(uploaded_at, str)
            and isinstance(transcript_path_key, str)
        ):
            entries[transcript_path] = ManifestEntry(
                source=source,
                transcript_path=transcript_path,
                mtime_ns=mtime_ns,
                size_bytes=size_bytes,
                uploaded_at=uploaded_at,
                transcript_path_key=transcript_path_key,
            )
    return entries


def _write_manifest(config: ChatPropConfig, entries: dict[str, ManifestEntry]) -> None:
    manifest_path = _manifest_path(config)
    payload = {path: entry.to_dict() for path, entry in sorted(entries.items())}
    _write_json_atomic(manifest_path, payload)


def _write_metadata(config: ChatPropConfig, metadata: TranscriptMetadata) -> None:
    key = _archive_metadata_key(metadata.session_id)
    path = _archive_root(config) / key
    _write_json_atomic(path, metadata.to_dict())


def _archive_transcript(
    config: ChatPropConfig,
    source: TranscriptSource,
    session_id: str,
    mtime_ns: int,
    transcript_path: Path,
) -> str:
    key = _archive_transcript_key(source, session_id, mtime_ns)
    target = _archive_root(config) / key
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(transcript_path, target)
    return key


def _iter_source_files(config: ChatPropConfig):
    sources: list[tuple[TranscriptSource, Path]] = [
        ("claude-code", config.claude_code.path.expanduser()),
        ("codex", config.codex.path.expanduser()),
    ]
    for source, root in sources:
        if not root.is_dir():
            continue
        for path in root.rglob("*.jsonl"):
            yield source, path


def _timestamp_to_iso(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=UTC).isoformat()


def _extract_session_details(path: Path) -> tuple[str, str, str]:
    session_id = path.stem
    first_timestamp: str | None = None
    last_timestamp: str | None = None

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
            if isinstance(timestamp, str):
                if first_timestamp is None:
                    first_timestamp = timestamp
                last_timestamp = timestamp

            if payload.get("type") == "session_meta":
                item_payload = payload.get("payload")
                if isinstance(item_payload, dict):
                    candidate_id = item_payload.get("id")
                    if isinstance(candidate_id, str) and candidate_id.strip():
                        session_id = candidate_id.strip()

    stat = path.stat()
    fallback = _timestamp_to_iso(stat.st_mtime)
    return session_id, first_timestamp or fallback, last_timestamp or fallback


def _archive_path(
    *,
    config: ChatPropConfig,
    index: BranchIndex,
    source: TranscriptSource,
    transcript_path: Path,
) -> tuple[ManifestEntry, BranchIndex]:
    session_id, started_at, ended_at = _extract_session_details(transcript_path)
    stat = transcript_path.stat()
    mtime_ns = getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000))
    archive_key = _archive_transcript(config, source, session_id, mtime_ns, transcript_path)
    metadata = TranscriptMetadata(
        session_id=session_id,
        source=source,
        started_at=started_at,
        ended_at=ended_at,
        transcript_path=archive_key,
        size_bytes=stat.st_size,
    )
    _write_metadata(config, metadata)
    updated_index = add_transcript_to_index(index, archive_key, extract_branches_from_transcript(transcript_path))
    entry = ManifestEntry(
        source=source,
        transcript_path=str(transcript_path.resolve()),
        mtime_ns=mtime_ns,
        size_bytes=stat.st_size,
        uploaded_at=utc_now_iso(),
        transcript_path_key=archive_key,
    )
    return entry, updated_index


def run_daemon_once(config: ChatPropConfig) -> DaemonRunStats:
    manifest = _read_manifest(config)
    index = _read_index(config)

    now_ns = time.time_ns()
    threshold_ns = config.daemon.inactivity_threshold_seconds * 1_000_000_000
    scanned = 0
    archived = 0
    skipped_unchanged = 0
    skipped_active = 0

    for source, path in _iter_source_files(config):
        scanned += 1
        try:
            stat = path.stat()
        except OSError:
            continue
        mtime_ns = getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000))
        resolved = str(path.resolve())
        previous = manifest.get(resolved)
        if previous and previous.mtime_ns == mtime_ns and previous.size_bytes == stat.st_size:
            skipped_unchanged += 1
            continue
        if threshold_ns > 0 and now_ns - mtime_ns < threshold_ns:
            skipped_active += 1
            continue

        archived_entry, index = _archive_path(
            config=config,
            index=index,
            source=source,
            transcript_path=path,
        )
        manifest[resolved] = archived_entry
        archived += 1

    _write_manifest(config, manifest)
    _write_index(config, index)
    return DaemonRunStats(
        scanned_files=scanned,
        archived_files=archived,
        skipped_unchanged=skipped_unchanged,
        skipped_active=skipped_active,
    )


def run_daemon_forever(config: ChatPropConfig) -> None:
    while True:
        stats = run_daemon_once(config)
        print(
            "chatprop daemon: scanned="
            f"{stats.scanned_files} archived={stats.archived_files} "
            f"skipped_unchanged={stats.skipped_unchanged} skipped_active={stats.skipped_active}",
            flush=True,
        )
        time.sleep(config.daemon.poll_interval_seconds)


def upload_session(config: ChatPropConfig, session_id: str) -> TranscriptMetadata:
    target_id = session_id.strip()
    if not target_id:
        raise ValueError("session_id cannot be empty")

    manifest = _read_manifest(config)
    index = _read_index(config)
    for source, path in _iter_source_files(config):
        candidate_id, started_at, ended_at = _extract_session_details(path)
        if candidate_id != target_id and path.stem != target_id:
            continue
        entry, index = _archive_path(config=config, index=index, source=source, transcript_path=path)
        manifest[entry.transcript_path] = entry
        _write_manifest(config, manifest)
        _write_index(config, index)
        return TranscriptMetadata(
            session_id=candidate_id,
            source=source,
            started_at=started_at,
            ended_at=ended_at,
            transcript_path=entry.transcript_path_key,
            size_bytes=entry.size_bytes,
        )
    raise FileNotFoundError(f"session_id not found: {target_id}")


def get_status(config: ChatPropConfig) -> DaemonStatus:
    manifest = _read_manifest(config)
    index = _read_index(config)
    archive_root = _archive_root(config)
    transcripts_root = archive_root / "transcripts"
    metadata_root = archive_root / "metadata"
    transcript_count = len(list(transcripts_root.rglob("*.jsonl"))) if transcripts_root.is_dir() else 0
    metadata_count = len(list(metadata_root.glob("*.json"))) if metadata_root.is_dir() else 0
    return DaemonStatus(
        state_dir=config.state_dir.expanduser(),
        archive_root=archive_root,
        transcript_count=transcript_count,
        metadata_count=metadata_count,
        indexed_branch_count=len(index.branches),
        manifest_entry_count=len(manifest),
    )
