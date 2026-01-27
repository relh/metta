import io
import json
import logging
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import uuid
import zipfile
from contextlib import nullcontext
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests
from metta_alo.rollout import PureSingleEpisodeJob, PureSingleEpisodeResult, SingleEpisodeJob

from metta.app_backend.clients.stats_client import StatsClient
from metta.app_backend.job_runner.episode_recording import record_job_episode
from metta.app_backend.models.job_request import JobRequestUpdate
from metta.common.auth.auth_config_reader_writer import observatory_auth_config
from metta.common.util.log_config import init_logging, suppress_noisy_logs
from metta.common.util.perf_profiler import PerfProfiler
from mettagrid.policy.prepare_policy_spec import download_policy_spec_from_s3_as_zip
from mettagrid.util.file import copy_data, read, write_data
from mettagrid.util.uri_resolvers.schemes import resolve_uri

logger = logging.getLogger(__name__)


def _is_presigned_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        return False
    query_params = parse_qs(parsed.query)
    return "X-Amz-Algorithm" in query_params or "AWSAccessKeyId" in query_params


def _upload_debug_dir(local_debug_dir: str | None, debug_uri: str | None) -> None:
    if local_debug_dir is None or debug_uri is None:
        return
    if not os.path.isdir(local_debug_dir):
        return
    try:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for abs_dir, _, filenames in os.walk(local_debug_dir):
                for filename in filenames:
                    abs_file = os.path.join(abs_dir, filename)
                    arcname = os.path.relpath(abs_file, local_debug_dir)
                    zf.write(abs_file, arcname)
        write_data(debug_uri, buf.getvalue(), content_type="application/zip")
        logger.info(f"Uploaded debug.zip to {debug_uri}")
    except Exception as e:
        logger.warning(f"Failed to upload debug.zip: {e}")


def _download_presigned_policy(url: str) -> Path:
    response = requests.get(url)
    response.raise_for_status()
    temp_dir = tempfile.mkdtemp()
    local_path = Path(temp_dir) / "policy.zip"
    local_path.write_bytes(response.content)
    return local_path


def _localize_policy_uri(uri: str) -> str:
    if _is_presigned_url(uri):
        local_path = _download_presigned_policy(uri)
        return local_path.as_uri()

    resolved = resolve_uri(uri)
    if resolved.scheme == "file":
        if resolved.local_path is None or not resolved.local_path.exists():
            raise FileNotFoundError(f"Policy path does not exist: {uri}")
        return resolved.local_path.as_uri()
    if resolved.scheme == "s3":
        local_path = download_policy_spec_from_s3_as_zip(
            resolved.canonical,
            remove_downloaded_copy_on_exit=True,
        )
        return local_path.as_uri()
    raise ValueError(f"Unsupported policy URI: {uri}")


def _localize_policy_uris(policy_uris: list[str]) -> list[str]:
    return [_localize_policy_uri(uri) for uri in policy_uris]


def run_episode(
    job: SingleEpisodeJob,
    upload_results_uri: str | None = None,
    upload_replay_uri: str | None = None,
    upload_debug_uri: str | None = None,
    use_profiler: bool = False,
) -> PureSingleEpisodeResult:
    local_debug_dir = tempfile.mkdtemp() if upload_debug_uri else None

    def sigterm_handler(_signum, _frame):
        logger.warning("Received SIGTERM, uploading debug_dir before exit...")
        _upload_debug_dir(local_debug_dir, upload_debug_uri)
        sys.exit(128 + signal.SIGTERM)

    signal.signal(signal.SIGTERM, sigterm_handler)

    try:
        local_policy_uris = _localize_policy_uris(job.policy_uris)

        local_results_uri = "file://results.json"
        local_replay_uri = "file://replay.json.z" if upload_replay_uri else None

        pure_job = PureSingleEpisodeJob(
            policy_uris=local_policy_uris,
            assignments=job.assignments,
            env=job.env,
            results_uri=local_results_uri,
            replay_uri=local_replay_uri,
            debug_dir=local_debug_dir,
            seed=job.seed,
            max_action_time_ms=job.max_action_time_ms,
        )

        with tempfile.NamedTemporaryFile(delete=True) as temp_file:
            pure_job_spec = {
                "job": pure_job.model_dump(),
                "device": "cpu",
                "allow_network": False,
            }
            temp_file.write(json.dumps(pure_job_spec).encode("utf-8"))
            temp_file.flush()

            # Enable Python perf support when profiling (writes /tmp/perf-<pid>.map)
            env = {**os.environ, "PYTHONPERFSUPPORT": "1"} if local_debug_dir else None
            proc = subprocess.Popen(
                [sys.executable, "-m", "metta_alo.pure_single_episode_runner", temp_file.name],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )

            if use_profiler and local_debug_dir:
                debug_path = Path(local_debug_dir)
                profiler_ctx = PerfProfiler(
                    pid=proc.pid,
                    data_path=debug_path / f"perf.{proc.pid}.data",
                    log_path=debug_path / f"perf.{proc.pid}.log",
                )
            else:
                profiler_ctx = nullcontext()

            with profiler_ctx:
                stdout, stderr = proc.communicate()

            if proc.returncode != 0:
                if proc.returncode < 0:
                    signal_num = -proc.returncode
                    raise RuntimeError(f"Killed by signal {signal_num}")
                error_output = stderr or stdout or "No output"
                if len(error_output) > 200000:
                    error_output = error_output[:200000] + "\n... (truncated)"
                raise RuntimeError(
                    f"metta_alo.pure_single_episode_runner failed (exit {proc.returncode}):\n{error_output}"
                )

        results = PureSingleEpisodeResult.model_validate_json(read(local_results_uri))

        if upload_results_uri:
            copy_data(local_results_uri, upload_results_uri, content_type="application/json")
            logger.info(f"Uploaded results to {upload_results_uri[:50]}...")

        if upload_replay_uri and local_replay_uri:
            copy_data(local_replay_uri, upload_replay_uri, content_type="application/x-compress")
            logger.info(f"Uploaded replay to {upload_replay_uri[:50]}...")

        _upload_debug_dir(local_debug_dir, upload_debug_uri)

        return results

    finally:
        if local_debug_dir is not None:
            shutil.rmtree(local_debug_dir, ignore_errors=True)


def run_with_presigned_urls(job_spec_uri: str, results_uri: str | None, replay_uri: str | None):
    logger.info(f"Running with presigned URLs: spec={job_spec_uri[:50]}...")

    response = requests.get(job_spec_uri)
    response.raise_for_status()
    job = SingleEpisodeJob.model_validate(response.json())

    run_episode(job, upload_results_uri=results_uri, upload_replay_uri=replay_uri)
    logger.info("Job completed successfully")


def run_with_observatory(job_id: uuid.UUID):
    observatory_auth_config.save_token(os.environ["MACHINE_TOKEN"], os.environ["STATS_SERVER_URI"])
    stats_client = StatsClient.create(os.environ["STATS_SERVER_URI"])

    try:
        job_data = stats_client.get_job(job_id)
        logger.info(f"Started job {job_id}")

        job = SingleEpisodeJob.model_validate(job_data.job)

        results = run_episode(
            job,
            upload_results_uri=job.results_uri,
            upload_replay_uri=job.replay_uri,
            upload_debug_uri=job.debug_uri,
            use_profiler=True,
        )

        record_job_episode(job_id, job, results, stats_client)
        logger.info(f"Completed job {job_id}")

    except Exception as e:
        logger.exception(f"Job {job_id} failed")
        stats_client.update_job(job_id, JobRequestUpdate(result={"error": str(e)}))
        raise
    finally:
        stats_client.close()


def main():
    job_spec_uri = os.environ.get("JOB_SPEC_URI")
    results_uri = os.environ.get("RESULTS_URI")
    replay_uri = os.environ.get("REPLAY_URI")

    if job_spec_uri:
        run_with_presigned_urls(job_spec_uri, results_uri, replay_uri)
        return

    if len(sys.argv) < 2:
        print("Usage: python -m metta.sim.single_episode_runner <job_id>")
        print("Or set JOB_SPEC_URI, RESULTS_URI, REPLAY_URI env vars")
        sys.exit(1)

    job_id = uuid.UUID(sys.argv[1])
    run_with_observatory(job_id)


if __name__ == "__main__":
    init_logging()
    suppress_noisy_logs()
    main()
