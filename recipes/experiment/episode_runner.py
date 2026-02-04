import json
import logging
import tempfile
import uuid
from pathlib import Path

from metta.app_backend.clients.stats_client import StatsClient
from metta.common.tool import Tool
from metta.tools.utils.auto_config import auto_stats_server_uri
from mettagrid.runner.episode_runner import run_episode_isolated
from mettagrid.runner.types import SingleEpisodeJob

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


RESULTS_FILENAME = "results.json"
REPLAY_FILENAME = "replay.json.z"


def _run_job(job: SingleEpisodeJob, output_dir: str) -> int:
    logger.info(f"Running job: {len(job.policy_uris)} policies, seed={job.seed}")
    logger.info(f"Output directory: {output_dir}")

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    config_path = out_path / "job_config.json"
    config_path.write_text(json.dumps(job.model_dump(), indent=2, default=str))
    logger.info(f"Wrote job config to {config_path}")

    with tempfile.TemporaryDirectory() as work_dir:
        work_path = Path(work_dir)
        results_path = work_path / RESULTS_FILENAME
        replay_path = work_path / REPLAY_FILENAME
        result = run_episode_isolated(
            job.episode_spec(),
            results_path,
            replay_path=replay_path,
            debug_dir=Path(tempfile.mkdtemp()),
        )
        results_path.rename(out_path / RESULTS_FILENAME)
        if replay_path.exists():
            replay_path.rename(out_path / REPLAY_FILENAME)
        logger.info(f"Episode finished: {result.steps} steps, rewards={result.rewards}")
    return 0


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
        logger.info(f"Fetched job {job_id}")
        return _run_job(job, self.output_dir)


class SingleEpisodeFileTool(Tool):
    output_dir: str = "."
    file: str

    def invoke(self, args: dict[str, str]) -> int:
        path = Path(self.file).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"Job spec file not found: {path}")
        job = SingleEpisodeJob.model_validate_json(path.read_text())
        logger.info(f"Loaded job from {path}")
        return _run_job(job, self.output_dir)


def repro(source: str, output_dir: str = ".") -> Tool:
    """
    ./tools/run.py recipes.experiment.episode_runner.repro source=<uuid-or-path-to-job.json>

    You can find a job id at https://observatory.softmax-research.net/episode-jobs, or an episode ID on an episode page

    If you click on the leftmost button on the episode page, you will download its specification: a
    `job-<job_id>.json` file. You can provide a path to that (or a modified version of it), to this tool, too.
    """
    if Path(source).expanduser().exists():
        return SingleEpisodeFileTool(file=source, output_dir=output_dir)
    try:
        uuid_id = uuid.UUID(source)
    except ValueError as e:
        raise ValueError(f"'{source}' is not a valid UUID or existing file path") from e
    return SingleEpisodeTool(id=uuid_id, output_dir=output_dir)
