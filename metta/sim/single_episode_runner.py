import io
import json
import logging
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import nullcontext
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests

from metta.common.util.log_config import init_logging, suppress_noisy_logs
from metta.common.util.perf_profiler import PerfProfiler
from mettagrid.policy.policy_env_interface import PolicyEnvInterface
from mettagrid.policy.prepare_policy_spec import download_policy_spec_from_s3_as_zip
from mettagrid.runner.job_specs import RuntimeInfo, SingleEpisodeJob
from mettagrid.runner.policy_server_manager import PolicyServerHandle, launch_policy_server
from mettagrid.runner.rollout import PureSingleEpisodeJob, PureSingleEpisodeResult
from mettagrid.util.file import copy_data, read, write_data
from mettagrid.util.uri_resolvers.schemes import resolve_uri

logger = logging.getLogger(__name__)


def _is_presigned_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in ("https", "http"):
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
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    temp_dir = tempfile.mkdtemp()
    local_path = Path(temp_dir) / "policy.zip"
    local_path.write_bytes(response.content)
    return local_path


def _localize_file_uri(resolved, uri: str) -> str:
    if resolved.local_path is None or not resolved.local_path.exists():
        raise FileNotFoundError(f"Policy path does not exist: {uri}")
    return resolved.local_path.as_uri()


def _localize_s3_uri(resolved, _uri: str) -> str:
    return download_policy_spec_from_s3_as_zip(
        resolved.canonical,
        remove_downloaded_copy_on_exit=True,
    ).as_uri()


_SCHEME_LOCALIZERS = {
    "mock": lambda resolved, _uri: resolved.canonical,
    "file": _localize_file_uri,
    "s3": _localize_s3_uri,
}


def _localize_policy_uri(uri: str) -> str:
    if _is_presigned_url(uri):
        return _download_presigned_policy(uri).as_uri()

    resolved = resolve_uri(uri)
    localizer = _SCHEME_LOCALIZERS.get(resolved.scheme)
    if localizer is None:
        raise ValueError(f"Unsupported policy URI: {uri}")
    return localizer(resolved, uri)


def _spawn_policy_servers(
    local_policy_uris: list[str],
    env_interface: PolicyEnvInterface,
) -> tuple[list[PolicyServerHandle], list[str]]:
    unique_uris = list(dict.fromkeys(local_policy_uris))
    uri_to_server: dict[str, PolicyServerHandle] = {}
    servers: list[PolicyServerHandle] = []
    futures: dict = {}
    try:
        with ThreadPoolExecutor(max_workers=len(unique_uris)) as pool:
            futures = {pool.submit(launch_policy_server, uri, env_interface): uri for uri in unique_uris}
            for future in as_completed(futures):
                uri = futures[future]
                handle = future.result()
                servers.append(handle)
                uri_to_server[uri] = handle
    except Exception:
        for f in futures:
            f.cancel()
        all_handles = set(servers)
        for f in futures:
            if f.done() and not f.cancelled() and f.exception() is None:
                all_handles.add(f.result())
        for h in all_handles:
            try:
                h.shutdown()
            except Exception:
                pass
        raise
    http_uris = [uri_to_server[uri].base_url for uri in local_policy_uris]
    return servers, http_uris


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

    work_dir = tempfile.mkdtemp()
    servers: list[PolicyServerHandle] = []
    try:
        local_policy_uris = [_localize_policy_uri(uri) for uri in job.policy_uris]
        env_interface = PolicyEnvInterface.from_mg_cfg(job.env)
        servers, http_policy_uris = _spawn_policy_servers(local_policy_uris, env_interface)

        local_results_uri = f"file://{work_dir}/results.json"
        local_replay_uri = f"file://{work_dir}/replay.json.z" if upload_replay_uri else None

        pure_job = PureSingleEpisodeJob(
            policy_uris=http_policy_uris,
            assignments=job.assignments,
            env=job.env,
            results_uri=local_results_uri,
            replay_uri=local_replay_uri,
            debug_dir=local_debug_dir,
            seed=job.seed,
            max_action_time_ms=job.max_action_time_ms,
        )

        with tempfile.NamedTemporaryFile(delete=True) as job_spec_tmp_file:
            pure_job_spec = {
                "job": pure_job.model_dump(),
                "device": "cpu",
            }
            job_spec_tmp_file.write(json.dumps(pure_job_spec).encode("utf-8"))
            job_spec_tmp_file.flush()

            # Enable Python perf support when profiling (writes /tmp/perf-<pid>.map)
            env = {**os.environ, "PYTHONPERFSUPPORT": "1"} if local_debug_dir else None
            proc = subprocess.Popen(
                [sys.executable, "-m", "mettagrid.runner.pure_single_episode_runner", job_spec_tmp_file.name],
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

            if stdout:
                logger.info("Episode runner stdout:\n%s", stdout.rstrip())
            if stderr:
                logger.info("Episode runner stderr:\n%s", stderr.rstrip())

            if proc.returncode != 0:
                code = proc.returncode
                detail = f"signal {-code}" if code < 0 else f"exit {code}"
                raise RuntimeError(f"pure_single_episode_runner failed ({detail})")

        results = PureSingleEpisodeResult.model_validate_json(read(local_results_uri))

        if upload_results_uri:
            copy_data(local_results_uri, upload_results_uri, content_type="application/json")
            logger.info(f"Uploaded results to {upload_results_uri}")

        if upload_replay_uri and local_replay_uri:
            copy_data(local_replay_uri, upload_replay_uri, content_type="application/x-compress")
            logger.info(f"Uploaded replay to {upload_replay_uri}")

        return results

    finally:
        for server in servers:
            server.shutdown()
        shutil.rmtree(work_dir, ignore_errors=True)
        if local_debug_dir is not None:
            _upload_debug_dir(local_debug_dir, upload_debug_uri)
            shutil.rmtree(local_debug_dir, ignore_errors=True)


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


def main():
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

    run_episode(
        job,
        upload_results_uri=results_uri,
        upload_replay_uri=replay_uri,
        upload_debug_uri=job.debug_uri,
        use_profiler=True,
    )
    logger.info("Job completed successfully")


if __name__ == "__main__":
    init_logging()
    suppress_noisy_logs()
    main()
