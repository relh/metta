from typing import Union
from uuid import UUID


def job_prefix(job_id: Union[UUID, str]) -> str:
    return f"jobs/{job_id}"


def job_spec_key(job_id: Union[UUID, str]) -> str:
    return f"{job_prefix(job_id)}/spec.json"


def job_results_key(job_id: Union[UUID, str]) -> str:
    return f"{job_prefix(job_id)}/results.json"


def job_replay_key(job_id: Union[UUID, str]) -> str:
    return f"{job_prefix(job_id)}/replay.json.z"


def job_debug_key(job_id: Union[UUID, str]) -> str:
    return f"{job_prefix(job_id)}/debug.zip"


def job_logs_key(job_id: Union[UUID, str]) -> str:
    return f"{job_prefix(job_id)}/logs.txt"
