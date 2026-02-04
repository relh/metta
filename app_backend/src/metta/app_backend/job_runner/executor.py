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

from metta.common.util.log_config import init_logging, suppress_noisy_logs
from mettagrid.runner.episode_runner import EpisodeResult, run_episode
from mettagrid.runner.job_specs import RuntimeInfo, SingleEpisodeJob
from mettagrid.util.file import copy_data, write_data

logger = logging.getLogger(__name__)


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
    episode: EpisodeResult,
    results_uri: str | None,
    replay_uri: str | None,
    debug_uri: str | None,
) -> None:
    try:
        if results_uri:
            copy_data(episode.results_path.as_uri(), results_uri, content_type="application/json")
            logger.info(f"Uploaded results to {results_uri}")

        if replay_uri and episode.replay_path:
            copy_data(episode.replay_path.as_uri(), replay_uri, content_type="application/x-compress")
            logger.info(f"Uploaded replay to {replay_uri}")

        debug_dir_str = str(episode.debug_dir) if episode.debug_dir else None
        _upload_debug_dir(debug_dir_str, debug_uri)
    finally:
        shutil.rmtree(episode.results_path.parent, ignore_errors=True)
        if episode.debug_dir:
            shutil.rmtree(episode.debug_dir, ignore_errors=True)


def _collect_runtime_info() -> RuntimeInfo:
    git_commit = os.environ.get("GIT_COMMIT") or None
    instance_type: str | None = None
    try:
        resp = requests.get("http://169.254.169.254/latest/meta-data/instance-type", timeout=2)
        if resp.ok:
            instance_type = resp.text.strip()
    except Exception:
        pass
    return RuntimeInfo(git_commit=git_commit, instance_type=instance_type)


def main() -> None:
    job_spec_uri = os.environ.get("JOB_SPEC_URI")
    results_uri = os.environ.get("RESULTS_URI")
    replay_uri = os.environ.get("REPLAY_URI")

    if not job_spec_uri:
        print("Set JOB_SPEC_URI, RESULTS_URI, REPLAY_URI env vars")
        sys.exit(1)
        return

    logger.info(f"Running with presigned URLs: spec={job_spec_uri[:50]}...")

    runtime_info_uri = os.environ.get("RUNTIME_INFO_URI")
    if runtime_info_uri:
        runtime_info = _collect_runtime_info()
        try:
            payload = runtime_info.model_dump_json(exclude_none=True)
            write_data(runtime_info_uri, payload.encode("utf-8"), content_type="application/json")
            logger.info(f"Uploaded runtime info: {payload}")
        except Exception as e:
            logger.warning(f"Failed to upload runtime info: {e}")

    response = requests.get(job_spec_uri, timeout=30)
    response.raise_for_status()
    job = SingleEpisodeJob.model_validate(response.json())

    debug_uri = job.debug_uri
    capture_replay = replay_uri is not None
    debug_dir = Path(tempfile.mkdtemp()) if debug_uri else None

    def sigterm_handler(_signum: int, _frame: object) -> None:
        logger.warning("Received SIGTERM, uploading debug_dir before exit...")
        _upload_debug_dir(str(debug_dir) if debug_dir else None, debug_uri)
        sys.exit(128 + signal.SIGTERM)

    if debug_dir:
        signal.signal(signal.SIGTERM, sigterm_handler)

    episode = run_episode(job, capture_replay=capture_replay, debug_dir=debug_dir)

    _upload_results(episode, results_uri, replay_uri, debug_uri)
    logger.info("Job completed successfully")


if __name__ == "__main__":
    init_logging()
    suppress_noisy_logs()
    main()
