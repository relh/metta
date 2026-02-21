import asyncio
import logging
from collections.abc import Callable
from uuid import UUID

import boto3
from fastapi import HTTPException

from metta.app_backend.job_runner.config import get_dispatch_config

logger = logging.getLogger(__name__)


def job_prefix(job_id: UUID) -> str:
    return f"jobs/{job_id}"


def job_spec_key(job_id: UUID) -> str:
    return f"{job_prefix(job_id)}/spec.json"


def job_results_key(job_id: UUID) -> str:
    return f"{job_prefix(job_id)}/results.json"


def job_replay_key(job_id: UUID) -> str:
    return f"{job_prefix(job_id)}/replay.json.z"


def job_debug_key(job_id: UUID) -> str:
    return f"{job_prefix(job_id)}/debug.zip"


def job_logs_key(job_id: UUID) -> str:
    return f"{job_prefix(job_id)}/logs.txt"


def job_runtime_info_key(job_id: UUID) -> str:
    return f"{job_prefix(job_id)}/runtime_info.json"


# Policy logs require an agent_idx parameter, so they can't use ARTIFACT_TYPES (which only
# supports job_id -> key mappings). If ARTIFACT_TYPES gains support for parameterized
# artifacts, these could be unified with the artifacts endpoint.
def job_policy_log_key(job_id: UUID, agent_idx: int) -> str:
    """S3 key for a policy log file."""
    return f"{job_prefix(job_id)}/policy_agent_{agent_idx}.txt"


def job_policy_log_prefix(job_id: UUID) -> str:
    """S3 prefix to list all policy logs for a job."""
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
