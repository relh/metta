import logging
import uuid

from sqlalchemy import Engine

from metta.app_backend.models.job_request import JobRequestUpdate
from metta.app_backend.otel.job_metrics import get_job_metrics
from metta.app_backend.queries.job_queries import (
    get_job_policy_version_ids,
    record_episode_direct,
    update_job,
)
from mettagrid.runner.types import EpisodeJobSummary, PureSingleEpisodeResult
from mettagrid.util.file import http_url

logger = logging.getLogger(__name__)


def record_job_episode(
    job_id: uuid.UUID,
    job: EpisodeJobSummary,
    results: PureSingleEpisodeResult,
    engine: Engine,
    result_data: dict[str, str] | None = None,
    replay_uri: str | None = None,
) -> uuid.UUID:
    policy_version_ids = get_job_policy_version_ids(engine, job_id)
    if len(policy_version_ids) != len(job.policy_uris):
        raise ValueError(
            f"Job {job_id} has {len(policy_version_ids)} stored policy versions for {len(job.policy_uris)} policy URIs"
        )
    episode_tags = {"job_id": str(job_id), **job.episode_tags}
    episode_id = uuid.uuid4()

    agent_metrics: list[tuple[int, str, float]] = []
    for agent_id, _assignment in enumerate(job.assignments):
        agent_metrics.append((agent_id, "reward", results.rewards[agent_id]))
        agent_metrics.append((agent_id, "action_timeout", float(results.action_timeouts[agent_id])))
        for metric_name, metric_value in results.stats["agent"][agent_id].items():
            agent_metrics.append((agent_id, metric_name, metric_value))

    record_episode_direct(
        engine,
        episode_id=episode_id,
        job_id=job_id,
        episode_tags=episode_tags,
        policy_version_ids=policy_version_ids,
        replay_uri=http_url(replay_uri) if replay_uri else None,
        assignments=job.assignments,
        agent_metrics=agent_metrics,
    )

    get_job_metrics().record_episode_length(results.steps, job_type="episode")

    final_result = {**(result_data or {}), "episode_id": str(episode_id)}
    update_job(engine, job_id, JobRequestUpdate(result=final_result))
    logger.info(f"Recorded episode {episode_id} for job {job_id}")
    return episode_id
