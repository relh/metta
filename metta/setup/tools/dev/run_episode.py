import platform
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Annotated

import typer

from metta.app_backend.clients.stats_client import StatsClient
from metta.setup.tools.dev.local_k8s import IMAGE
from metta.setup.utils import error, info
from metta.tools.utils.auto_config import auto_stats_server_uri
from mettagrid.runner.episode_runner import run_episode_isolated
from mettagrid.runner.types import SingleEpisodeJob
from mettagrid.util.uri_resolvers.schemes import localize_uri

PROD_IMAGE = "ghcr.io/metta-ai/episode-runner:latest"


def _resolve_job_id(client: StatsClient, uuid_id: uuid.UUID) -> uuid.UUID:
    """Resolve a UUID to a job ID, trying both job_id and episode_id lookups."""
    try:
        job_request = client.get_job(job_id=uuid_id)
        return job_request.id
    except Exception:
        pass
    result = client.sql_query(f"SELECT id FROM job_requests WHERE result->>'episode_id' = '{uuid_id}' LIMIT 1")
    if result.rows:
        return uuid.UUID(result.rows[0][0])
    raise ValueError(f"No job found for job_id or episode_id: {uuid_id}")


def _run_episode_local(job: SingleEpisodeJob, out: Path) -> None:
    results_path = out / "results.json"
    replay_path = out / "replay.json.z"
    debug_dir = out / "debug"
    debug_dir.mkdir(exist_ok=True)
    run_episode_isolated(job.episode_spec(), results_path, replay_path=replay_path, debug_dir=debug_dir)
    info(f"Results written to {results_path}")


def _localize_policy_for_docker(uri: str, index: int, volume_mounts: list[str]) -> str:
    """Resolve a policy URI on the host and return a file:// URI for the container."""
    local_path = localize_uri(uri)
    if local_path is None:
        raise ValueError(f"Cannot localize policy URI: {uri}")
    container_target = f"/workspace/policies/{index}"
    if local_path.is_dir():
        container_uri = f"file://{container_target}"
    else:
        container_uri = f"file://{container_target}/{local_path.name}"
        container_target = f"{container_target}/{local_path.name}"
    volume_mounts.extend(["-v", f"{local_path.resolve()}:{container_target}:ro"])
    return container_uri


def _run_episode_docker(job: SingleEpisodeJob, out: Path, image: str, docker_platform: str) -> None:
    with tempfile.TemporaryDirectory(prefix="observatory_run_episode_") as workspace:
        workspace_path = Path(workspace)
        spec_path = workspace_path / "spec.json"

        volume_mounts: list[str] = []
        container_policy_uris = [
            _localize_policy_for_docker(uri, i, volume_mounts) for i, uri in enumerate(job.policy_uris)
        ]

        docker_job = SingleEpisodeJob(
            policy_uris=container_policy_uris,
            assignments=job.assignments,
            env=job.env,
            seed=job.seed,
            max_action_time_ms=job.max_action_time_ms,
        )
        spec_path.write_text(docker_job.model_dump_json())

        cmd = [
            "docker",
            "run",
            "--rm",
            "--platform",
            docker_platform,
            "-e",
            "JOB_SPEC_URI=file:///workspace/io/spec.json",
            "-e",
            "RESULTS_URI=file:///workspace/io/results.json",
            "-e",
            "REPLAY_URI=file:///workspace/io/replay.json.z",
            "-e",
            "DEBUG_URI=file:///workspace/io/debug.zip",
            "-v",
            f"{workspace}:/workspace/io:rw",
            *volume_mounts,
            image,
        ]
        info(f"Running episode in Docker ({image}) for {docker_platform}")
        subprocess.run(cmd, check=True, timeout=600)

        for name in ("results.json", "replay.json.z", "debug.zip"):
            src = workspace_path / name
            if src.exists():
                (out / name).write_bytes(src.read_bytes())
        info(f"Results written to {out}")


def _load_job(source: str) -> SingleEpisodeJob:
    source_path = Path(source).expanduser()
    if source_path.exists():
        return SingleEpisodeJob.model_validate_json(source_path.read_text())
    uuid_id = uuid.UUID(source)
    stats_uri = auto_stats_server_uri()
    if not stats_uri:
        raise ValueError("No stats server URI configured")
    client = StatsClient.create(stats_server_uri=stats_uri)
    job_id = _resolve_job_id(client, uuid_id)
    job_request = client.get_job(job_id)
    job = SingleEpisodeJob.model_validate(job_request.job)
    info(f"Fetched job {job_id}")
    return job


def _check_docker_prerequisites(image: str) -> None:
    if not shutil.which("docker"):
        error("Docker not found. Install OrbStack: https://orbstack.dev")
        error("  Or use --mode local to skip Docker.")
        raise typer.Exit(1)
    if subprocess.run(["docker", "info"], capture_output=True).returncode != 0:
        error("Docker daemon not running. Start OrbStack first:")
        error("  orb start")
        error("  Or use --mode local to skip Docker.")
        raise typer.Exit(1)
    result = subprocess.run(["docker", "images", image, "--format", "{{.Repository}}"], capture_output=True, text=True)
    if not result.stdout.strip():
        error(f"Image {image} not found. Build it first:")
        error("  metta dev local-k8s build-image")
        error("  Or use --mode local to skip Docker.")
        raise typer.Exit(1)


def run_episode_cmd(
    source: Annotated[str, typer.Argument(help="Path to job spec JSON, or observatory job/episode UUID")],
    mode: Annotated[str, typer.Option("--mode", "-m", help="local, local-image, or prod-image")] = "local",
    output_dir: Annotated[str, typer.Option("--output-dir", "-o", help="Directory for results")] = "./episode-results",
    image: Annotated[
        str | None, typer.Option("--image", help="Override Docker image (local-image/prod-image modes)")
    ] = None,
):
    """Run a single episode locally or in a Docker image.

    Modes:
      local       - subprocess isolation, no Docker (default)
      local-image - uses episode-runner-local:latest (built from source)
      prod-image  - uses ghcr.io/metta-ai/episode-runner:latest (linux/amd64)
    """
    job = _load_job(source)
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)

    if mode == "local":
        _run_episode_local(job, out)
    elif mode == "local-image":
        img = image or IMAGE
        _check_docker_prerequisites(img)
        docker_platform = "linux/arm64" if platform.machine() in ("arm64", "aarch64") else "linux/amd64"
        _run_episode_docker(job, out, img, docker_platform)
    elif mode == "prod-image":
        img = image or PROD_IMAGE
        _check_docker_prerequisites(img)
        info(f"Pulling {img}...")
        subprocess.run(["docker", "pull", "--platform", "linux/amd64", img], check=True, timeout=300)
        _run_episode_docker(job, out, img, "linux/amd64")
    else:
        error(f"Unknown mode: {mode}. Use local, local-image, or prod-image")
        raise typer.Exit(1)
