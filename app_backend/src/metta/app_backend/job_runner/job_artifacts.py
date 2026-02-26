import asyncio
import logging
from collections.abc import Callable
from enum import Enum
from typing import Literal
from uuid import UUID

import boto3
from fastapi import HTTPException

from metta.app_backend.job_runner.config import get_dispatch_config

logger = logging.getLogger(__name__)


class JobArtifact(Enum):
    """Single source of truth for every per-job S3 artifact.

    Each member is (filename, env_var_name, presign_direction, content_type).
    Adding a new artifact means adding one line here — dispatcher, executor,
    and routes all derive from this enum.
    """

    SPEC = ("spec.json", "JOB_SPEC_URI", "get", "application/json")
    RESULTS = ("results.json", "RESULTS_URI", "put", "application/json")
    RUNTIME_INFO = ("runtime_info.json", "RUNTIME_INFO_URI", "put", "application/json")
    REPLAY = ("replay.json.z", "REPLAY_URI", "put", "application/octet-stream")
    DEBUG = ("debug.zip", "DEBUG_URI", "put", "application/zip")
    LOGS = ("logs.txt", None, "put", "text/plain")  # written by event processor, not runner

    def __init__(self, filename: str, env_var: str | None, direction: str, content_type: str):
        self.filename = filename
        self.env_var = env_var
        self.direction: Literal["get", "put"] = direction  # type: ignore[assignment]
        self.content_type = content_type

    def key(self, job_id: UUID) -> str:
        return f"{job_prefix(job_id)}/{self.filename}"

    @classmethod
    def presigned(cls) -> list["JobArtifact"]:
        """Artifacts that need URI env vars passed to the runner."""
        return [a for a in cls if a.env_var is not None]


def job_prefix(job_id: UUID) -> str:
    return f"jobs/{job_id}"


# Policy logs are per-agent (N per job), not per-job like JobArtifact members.
# They use a separate JSON-dict env var (POLICY_LOG_URLS) and dedicated routes,
# so they intentionally live outside the enum.
POLICY_LOG_FILENAME = "policy_agent_{agent_idx}.txt"


def job_policy_log_key(job_id: UUID, agent_idx: int) -> str:
    return f"{job_prefix(job_id)}/{POLICY_LOG_FILENAME.format(agent_idx=agent_idx)}"


def job_policy_log_prefix(job_id: UUID) -> str:
    return f"{job_prefix(job_id)}/policy_agent_"


async def read_job_artifact(
    job_id: UUID,
    key_fn: Callable[[UUID], str],
    media_type: str,
    extract: Callable[[bytes], bytes] = lambda b: b,
    artifact_label: str = "artifact",
) -> tuple[bytes, str]:
    cfg = get_dispatch_config()
    if not cfg.EVAL_S3_BUCKET:
        raise HTTPException(status_code=501, detail="Storage not configured")

    def _read() -> bytes:
        s3 = boto3.client("s3")
        body = s3.get_object(Bucket=cfg.EVAL_S3_BUCKET, Key=key_fn(job_id))["Body"].read()
        return extract(body)

    try:
        content = await asyncio.to_thread(_read)
        return content, media_type
    except Exception as e:
        if "NoSuchKey" in type(e).__name__ or "NoSuchKey" in str(e) or isinstance(e, KeyError):
            raise HTTPException(status_code=404, detail=f"No {artifact_label} found for job {job_id}") from None
        logger.error(f"Failed to read {artifact_label} for job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to read {artifact_label}") from e
