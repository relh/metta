import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from metta.app_backend.route_logger import timed_http_handler
from vibeservatory.backend.dashboard_backend.auth import SoftmaxUser
from vibeservatory.backend.dashboard_backend.config import settings

_REPO_SENTINEL = "pnpm-workspace.yaml"
_HALL_ORDER = {"fame": 0, "same": 1, "lame": 2}
_LOG = logging.getLogger(__name__)


class PantheonStory(BaseModel):
    story_id: str
    hall: Literal["fame", "same", "lame"]
    title: str
    motif: str
    summary: str
    policy: str
    run_id: str | None = None
    episode_id: str | None = None
    replay_url: str | None = None
    source: str = "seeded"
    tags: list[str] = Field(default_factory=list)
    created_at: str


class PantheonStoriesResponse(BaseModel):
    generated_at: str
    source_root: str | None = None
    stories: list[PantheonStory] = Field(default_factory=list)


def _isoformat_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _resolve_repo_root() -> Path | None:
    current = Path.cwd()
    while True:
        if (current / _REPO_SENTINEL).is_file():
            return current
        if current.parent == current:
            return None
        current = current.parent


def _resolve_pantheon_root() -> Path | None:
    if settings.DASHBOARD_PANTHEON_ROOT:
        return Path(settings.DASHBOARD_PANTHEON_ROOT)
    return repo_root / "outputs" / "pantheon" if (repo_root := _resolve_repo_root()) is not None else None


def _seeded_pantheon_stories() -> list[PantheonStory]:
    return [
        PantheonStory(
            story_id="motif-junction-lock-001",
            hall="fame",
            title="Frozen Junction Hold",
            motif="A disciplined hold pattern that secures the junction while maintaining support routes.",
            summary=(
                "The policy kept two defenders in alternating positions, preserved movement tempo, "
                "and held control through final ticks."
            ),
            policy="glanky:v11",
            run_id="sample-fame-20260301",
            episode_id="episode-fame-17",
            replay_url="https://metta-ai.github.io/metta/mettascope/mettascope.html",
            source="seeded",
            tags=["junction-control", "coordination", "closing-discipline"],
            created_at="2026-03-01T04:18:00Z",
        ),
        PantheonStory(
            story_id="motif-stall-loop-002",
            hall="lame",
            title="Resource Stall Loop",
            motif="Repeated cargo shuttling with low conversion and missed pressure windows.",
            summary=(
                "A miner/aligner pair cycled near home base for too long, producing low conversion "
                "and exposing the team to late scramble losses."
            ),
            policy="cranky:v5",
            run_id="sample-lame-20260301",
            episode_id="episode-lame-09",
            replay_url="https://metta-ai.github.io/metta/mettascope/mettascope.html",
            source="seeded",
            tags=["stall", "resource-loop", "timing-failure"],
            created_at="2026-03-01T04:23:00Z",
        ),
        PantheonStory(
            story_id="motif-mirror-opener-003",
            hall="same",
            title="Mirror Opener Meta",
            motif="A high-frequency opener pattern common across multiple policies and seasons.",
            summary=(
                "Different policies independently converged on the same opening route and early role split. "
                "Useful as baseline behavior for supervised motif training."
            ),
            policy="multi-policy",
            run_id="sample-same-20260301",
            episode_id="episode-same-31",
            replay_url="https://metta-ai.github.io/metta/mettascope/mettascope.html",
            source="seeded",
            tags=["meta", "opener", "high-frequency"],
            created_at="2026-03-01T04:27:00Z",
        ),
    ]


def _story_timestamp(created_at: str) -> float:
    normalized = created_at.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized).timestamp()


def _sorted_stories(stories: list[PantheonStory]) -> list[PantheonStory]:
    return sorted(
        stories,
        key=lambda story: (
            _HALL_ORDER[story.hall],
            -_story_timestamp(story.created_at),
            story.story_id,
        ),
    )


def _story_files(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    files: list[Path] = []
    stories_bundle = root / "stories.json"
    if stories_bundle.is_file():
        files.append(stories_bundle)

    stories_dir = root / "stories"
    if stories_dir.is_dir():
        files.extend(sorted(path for path in stories_dir.glob("*.json") if path.is_file()))
    return files


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _story_payloads(payload: Any, *, file_path: Path) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        if not all(isinstance(entry, dict) for entry in payload):
            raise ValueError(f"Pantheon story list must contain objects: {file_path}")
        return payload
    if not isinstance(payload, dict):
        raise ValueError(f"Pantheon story payload must be an object or list: {file_path}")

    nested_stories = payload.get("stories")
    if nested_stories is None:
        return [payload]
    if not isinstance(nested_stories, list):
        raise ValueError(f"Pantheon stories field must be a list: {file_path}")
    if not all(isinstance(entry, dict) for entry in nested_stories):
        raise ValueError(f"Pantheon stories field must contain objects: {file_path}")
    return nested_stories


def _load_file_backed_stories(root: Path) -> list[PantheonStory]:
    stories: list[PantheonStory] = []
    for file_path in _story_files(root):
        try:
            payload = _read_json(file_path)
            story_payloads = _story_payloads(payload, file_path=file_path)
        except Exception as error:
            _LOG.warning("Skipping invalid Pantheon file %s: %s", file_path, error)
            continue

        for story_index, raw_story in enumerate(story_payloads):
            story_payload = {**raw_story}
            story_payload.setdefault("source", "filesystem")
            try:
                stories.append(PantheonStory.model_validate(story_payload))
            except Exception as error:
                _LOG.warning(
                    "Skipping invalid Pantheon story %s[%d]: %s",
                    file_path,
                    story_index,
                    error,
                )
    return stories


def load_pantheon_stories() -> tuple[list[PantheonStory], str | None]:
    pantheon_root = _resolve_pantheon_root()
    seeded = _sorted_stories(_seeded_pantheon_stories())
    if pantheon_root is None:
        return seeded, None

    stories = _load_file_backed_stories(pantheon_root)
    if stories:
        return _sorted_stories(stories), str(pantheon_root)
    return seeded, str(pantheon_root)


def create_pantheon_router() -> APIRouter:
    router = APIRouter(prefix="/pantheon/v1", tags=["pantheon"])

    @router.get("/stories")
    @timed_http_handler
    async def get_stories(user: SoftmaxUser) -> PantheonStoriesResponse:
        stories, source_root = load_pantheon_stories()
        return PantheonStoriesResponse(
            generated_at=_isoformat_utc(datetime.now(UTC)),
            source_root=source_root,
            stories=stories,
        )

    return router
