import logging
import uuid

import duckdb

from metta.app_backend.clients.stats_client import StatsClient
from metta.app_backend.episode_stats_db import (
    episode_stats_db,
    insert_agent_metric,
    insert_agent_policy,
    insert_episode,
    insert_episode_tag,
)
from metta.app_backend.metta_scheme_resolver import MettaSchemeResolver
from metta.app_backend.models.job_request import JobRequestUpdate
from mettagrid.runner.job_specs import SingleEpisodeJob
from mettagrid.runner.rollout import PureSingleEpisodeResult
from mettagrid.util.file import http_url

logger = logging.getLogger(__name__)


def resolve_policy_version_id(uri: str, stats_client: StatsClient) -> uuid.UUID | None:
    if not uri.startswith("metta://"):
        return None
    try:
        resolver = MettaSchemeResolver(stats_client=stats_client)
        return resolver.get_policy_version_id(uri)
    except Exception:
        return None


def resolve_policy_version_ids(policy_uris: list[str], stats_client: StatsClient) -> list[uuid.UUID | None]:
    return [resolve_policy_version_id(uri, stats_client) for uri in policy_uris]


def populate_single_episode_duckdb(
    conn: duckdb.DuckDBPyConnection,
    *,
    episode_tags: dict[str, str],
    policy_version_ids: list[uuid.UUID | None],
    replay_uri: str | None,
    assignments: list[int],
    results: PureSingleEpisodeResult,
) -> uuid.UUID:
    episode_id = uuid.uuid4()

    insert_episode(
        conn,
        episode_id=str(episode_id),
        replay_url=http_url(replay_uri) if replay_uri else None,
        thumbnail_url=None,
        attributes=results.model_dump(),
        eval_task_id=None,
    )

    for key, value in episode_tags.items():
        insert_episode_tag(conn, str(episode_id), key, value)

    for agent_id, assignment in enumerate(assignments):
        policy_version_id = policy_version_ids[assignment]
        if policy_version_id:
            insert_agent_policy(conn, str(episode_id), str(policy_version_id), agent_id)

        insert_agent_metric(conn, str(episode_id), agent_id, "reward", results.rewards[agent_id])
        insert_agent_metric(conn, str(episode_id), agent_id, "action_timeout", float(results.action_timeouts[agent_id]))

        agent_stats = results.stats["agent"][agent_id]
        for metric_name, metric_value in agent_stats.items():
            insert_agent_metric(conn, str(episode_id), agent_id, metric_name, metric_value)

    return episode_id


def write_single_episode_to_observatory(
    *,
    episode_tags: dict[str, str],
    policy_version_ids: list[uuid.UUID | None],
    replay_uri: str | None,
    assignments: list[int],
    results: PureSingleEpisodeResult,
    stats_client: StatsClient,
) -> uuid.UUID:
    with episode_stats_db() as (conn, db_path):
        episode_id = populate_single_episode_duckdb(
            conn,
            episode_tags=episode_tags,
            policy_version_ids=policy_version_ids,
            replay_uri=replay_uri,
            assignments=assignments,
            results=results,
        )
        conn.execute("CHECKPOINT")
        response = stats_client.bulk_upload_episodes(str(db_path))
        logger.info(f"Uploaded episode: {response.episodes_created} episodes at {response.duckdb_s3_uri}")
    return episode_id


def record_job_episode(
    job_id: uuid.UUID,
    job: SingleEpisodeJob,
    results: PureSingleEpisodeResult,
    stats_client: StatsClient,
    result_data: dict[str, str] | None = None,
) -> uuid.UUID:
    policy_version_ids = resolve_policy_version_ids(job.policy_uris, stats_client)
    episode_tags = {"job_id": str(job_id), **job.episode_tags}

    episode_id = write_single_episode_to_observatory(
        episode_tags=episode_tags,
        policy_version_ids=policy_version_ids,
        replay_uri=job.replay_uri,
        assignments=job.assignments,
        results=results,
        stats_client=stats_client,
    )

    final_result = {**(result_data or {}), "episode_id": str(episode_id)}
    stats_client.update_job(job_id, JobRequestUpdate(result=final_result))
    logger.info(f"Recorded episode {episode_id} for job {job_id}")
    return episode_id
