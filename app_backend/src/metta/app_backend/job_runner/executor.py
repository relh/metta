import io
import logging
import os
import shutil
import signal
import sys
import tempfile
import zipfile
from pathlib import Path

import requests
from pydantic import Field
from pydantic_settings import BaseSettings

from metta.common.util.log_config import init_logging, suppress_noisy_logs
from mettagrid.runner.episode_runner import run_episode_isolated
from mettagrid.runner.types import RuntimeInfo, SingleEpisodeJob
from mettagrid.util.file import copy_data, write_data

logger = logging.getLogger(__name__)


class ExecutorSettings(BaseSettings):
    """Environment variables consumed by the episode executor entrypoint.

    TODO: RESULTS_URI, REPLAY_URI live here as env vars, but debug_uri comes from
    SingleEpisodeJob. All three are output upload destinations and should be sourced
    the same way -- either all on the job spec or all as env vars.
    """

    JOB_SPEC_URI: str | None = Field(default=None, description="Presigned URL to fetch the job spec from")
    RESULTS_URI: str | None = Field(default=None, description="Presigned URL to upload episode results to")
    REPLAY_URI: str | None = Field(default=None, description="Presigned URL to upload the replay to")
    RUNTIME_INFO_URI: str | None = Field(default=None, description="Presigned URL to upload runtime info to")
    GIT_COMMIT: str | None = Field(default=None, description="Git commit hash of the running build")


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


def _upload_results(
    results_path: Path,
    replay_path: Path | None,
    results_uri: str | None,
    replay_uri: str | None,
    debug_dir: Path | None,
    debug_uri: str | None,
) -> None:
    if results_uri and results_path.exists():
        copy_data(results_path.as_uri(), results_uri, content_type="application/json")
        logger.info(f"Uploaded results to {results_uri}")

    if replay_uri and replay_path is not None and replay_path.exists():
        copy_data(replay_path.as_uri(), replay_uri, content_type="application/x-compress")
        logger.info(f"Uploaded replay to {replay_uri}")

    _upload_debug_dir(str(debug_dir) if debug_dir else None, debug_uri)


def _collect_runtime_info(settings: ExecutorSettings) -> RuntimeInfo:
    instance_type: str | None = None
    try:
        resp = requests.get("http://169.254.169.254/latest/meta-data/instance-type", timeout=2)
        if resp.ok:
            instance_type = resp.text.strip()
    except Exception:
        pass
    return RuntimeInfo(git_commit=settings.GIT_COMMIT, instance_type=instance_type)


def main() -> None:
    settings = ExecutorSettings()

    os.environ["EPISODE_RUNNER_USE_ISOLATED_VENVS"] = "0"

    if not settings.JOB_SPEC_URI:
        print("Set JOB_SPEC_URI, RESULTS_URI, REPLAY_URI env vars")
        sys.exit(1)
        return

    logger.info(f"Running with presigned URLs: spec={settings.JOB_SPEC_URI[:50]}...")

    if settings.RUNTIME_INFO_URI:
        runtime_info = _collect_runtime_info(settings)
        try:
            payload = runtime_info.model_dump_json(exclude_none=True)
            write_data(settings.RUNTIME_INFO_URI, payload.encode("utf-8"), content_type="application/json")
            logger.info(f"Uploaded runtime info: {payload}")
        except Exception as e:
            logger.warning(f"Failed to upload runtime info: {e}")

    # TODO: we use a combination of httpx and requests; should this use httpx?
    response = requests.get(settings.JOB_SPEC_URI, timeout=30)
    response.raise_for_status()
    job = SingleEpisodeJob.model_validate(response.json())

    debug_uri = job.debug_uri
    capture_replay = settings.REPLAY_URI is not None

    with tempfile.TemporaryDirectory() as output_dir_str:
        output_dir = Path(output_dir_str)
        debug_dir = Path(tempfile.mkdtemp()) if debug_uri else None

        results_path = output_dir / "results.json"
        replay_path = output_dir / "replay.json.z" if capture_replay else None

        def sigterm_handler(_signum: int, _frame: object) -> None:
            logger.warning("Received SIGTERM, uploading debug_dir before exit...")
            _upload_debug_dir(str(debug_dir) if debug_dir else None, debug_uri)
            sys.exit(128 + signal.SIGTERM)

        if debug_dir:
            signal.signal(signal.SIGTERM, sigterm_handler)

        try:
            run_episode_isolated(
                job.episode_spec(),
                results_path,
                replay_path=replay_path,
                debug_dir=debug_dir,
            )
            _upload_results(results_path, replay_path, settings.RESULTS_URI, settings.REPLAY_URI, debug_dir, debug_uri)
            logger.info("Job completed successfully")
        finally:
            if debug_dir:
                shutil.rmtree(debug_dir, ignore_errors=True)


if __name__ == "__main__":
    init_logging()
    suppress_noisy_logs()
    main()
