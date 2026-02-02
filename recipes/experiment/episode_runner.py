import logging
import uuid

from metta_alo.job_specs import SingleEpisodeJob

from metta.app_backend.clients.stats_client import StatsClient
from metta.common.tool import Tool
from metta.sim.single_episode_runner import run_episode
from metta.tools.utils.auto_config import auto_stats_server_uri

logger = logging.getLogger(__name__)


def _resolve_job_id(client: StatsClient, uuid_id: uuid.UUID) -> uuid.UUID:
    try:
        job_request = client.get_job(job_id=uuid_id)
        return job_request.id
    except Exception:
        pass
    result = client.sql_query(f"SELECT id FROM job_requests WHERE result->>'episode_id' = '{uuid_id}' LIMIT 1")
    if result.rows:
        return uuid.UUID(result.rows[0][0])

    raise ValueError(f"No job found for job_id or episode_id: {uuid_id}")


class SingleEpisodeTool(Tool):
    stats_server_uri: str | None = auto_stats_server_uri()
    output_dir: str = "."
    id: uuid.UUID

    def invoke(self, args: dict[str, str]) -> int:
        if not self.stats_server_uri:
            raise ValueError("Stats server URI is not set")
        client = StatsClient.create(stats_server_uri=self.stats_server_uri)

        job_id = _resolve_job_id(client, self.id)
        job_request = client.get_job(job_id)
        job = SingleEpisodeJob.model_validate(job_request.job)
        job.replay_uri = f"file://{self.output_dir}/replay.json.z"
        job.debug_uri = f"file://{self.output_dir}/debug.zip"
        job.results_uri = f"file://{self.output_dir}/results.json"
        logger.info(f"Fetched job {job_id}: {len(job.policy_uris)} policies, seed={job.seed}")
        logger.info(f"Output directory: {self.output_dir}")

        result = run_episode(
            job,
            upload_replay_uri=job.replay_uri,
            upload_debug_uri=job.debug_uri,
            upload_results_uri=job.results_uri,
        )
        logger.info(f"Episode finished: {result.steps} steps, rewards={result.rewards}")
        return 0


def repro(id: str, output_dir: str = ".") -> SingleEpisodeTool:
    """
    ./tools/run.py recipes.experiment.episode_runner.repro id=<job-or-episode-uuid>
    """
    try:
        uuid_id = uuid.UUID(id)
    except ValueError as e:
        raise ValueError(f"Invalid UUID: {id}") from e
    return SingleEpisodeTool(id=uuid_id, output_dir=output_dir)
