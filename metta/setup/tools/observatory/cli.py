#!/usr/bin/env -S uv run
"""Observatory CLI - Local development environment for the Observatory web app.

This module orchestrates all Observatory services for local development:
- PostgreSQL database
- FastAPI backend server
- Next.js frontend
- K8s job watcher
- Tournament commissioner

=============================================================================
DEVCONTAINER SUPPORT
=============================================================================

This CLI supports running inside a devcontainer on macOS. The key challenges:

1. DATABASE CONNECTION
   PostgreSQL runs via docker-compose on the HOST's Docker (not in devcontainer).
   From inside the container, we connect via host.docker.internal:5432.
   See _get_db_uri() for the implementation.

2. KUBERNETES ACCESS
   The devcontainer connects to the host's OrbStack K8s cluster.
   See local_k8s.py for how we modify the kubeconfig.

3. PORT FORWARDING
   Services bind to 0.0.0.0 so they're accessible from the host browser.
   Ports are forwarded via devcontainer.json runArgs (-p flags).

4. PROCESS-COMPOSE ENVIRONMENT
   The _process_compose_env() function sets up all the environment variables
   needed for services to communicate correctly when in a container.
"""

import functools
import os
import subprocess
from pathlib import Path
from typing import Annotated

import typer

from metta.app_backend.clients.base_client import get_machine_token
from metta.common.util.constants import PROD_STATS_SERVER_URI
from metta.common.util.fs import get_repo_root
from metta.setup.tools.observatory.local_k8s import (
    K3D_CLUSTER_NAME,
    detect_k8s_runtime,
    get_host_address,
    get_k8s_context,
    local_k8s_app,
)
from metta.setup.tools.observatory.utils import LOCAL_METTA_POLICY_EVAL_IMG_NAME
from metta.setup.utils import error, info

repo_root = get_repo_root()

# =============================================================================
# LOCAL DEV CONFIGURATION
# =============================================================================
# These values are used for the local development environment.
# LOCALHOST is used for services binding and health checks.
# For container->host communication, we use host.docker.internal (see _get_db_uri).

LOCALHOST = "127.0.0.1"
POSTGRES_PORT = 5432
POSTGRES_USER = "postgres"
POSTGRES_PASSWORD = "password"
POSTGRES_DB = "metta"
SERVER_PORT = 8000
PROCESS_COMPOSE_PORT = 8090
LOCALSTACK_PORT = 4566
LOCALSTACK_ENDPOINT_HOST = f"http://{LOCALHOST}:{LOCALSTACK_PORT}"
LOCALSTACK_ENDPOINT_K8S = f"http://host.docker.internal:{LOCALSTACK_PORT}"
LOCAL_EVAL_BUCKET = "eval-bucket"

# LOCAL_DB_URI is for direct Mac development (127.0.0.1 works).
# For container development, _get_db_uri() returns a different URI.
LOCAL_DB_URI = f"postgres://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{LOCALHOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
LOCAL_BACKEND_URL = f"http://{LOCALHOST}:{SERVER_PORT}"
LOCAL_MACHINE_TOKEN = "local-dev-user@example.com"
LOCAL_AWS_PROFILE = "softmax"


def _get_backend_url_from_k8s() -> str:
    """Get the URL that K8s pods should use to reach the backend server.

    K8s pods run in a different network namespace and can't use 127.0.0.1
    to reach the host. Each K8s runtime provides a DNS name for host access:
    - OrbStack: host.docker.internal
    - k3d: host.k3d.internal

    This URL is passed to job pods as STATS_SERVER_URI so they can report
    results back to the Observatory backend.
    """
    runtime = detect_k8s_runtime()
    if runtime is None:
        # Fallback for when no runtime is detected yet
        return f"http://host.docker.internal:{SERVER_PORT}"
    host_addr = get_host_address(runtime)
    return f"http://{host_addr}:{SERVER_PORT}"


def _get_k8s_context() -> str:
    """Get the kubectl context for the detected runtime.

    This is passed to process-compose as K8S_CONTEXT so all services
    use the correct context for kubectl commands.
    """
    runtime = detect_k8s_runtime()
    if runtime is None:
        return "orbstack"  # Fallback
    return get_k8s_context(runtime)


def handle_errors(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except subprocess.CalledProcessError as e:
            error(f"Failed: {e}")
            raise typer.Exit(1) from e
        except KeyboardInterrupt:
            raise typer.Exit(0) from None

    return wrapper


HELP_TEXT = f"""
Observatory local development.

[bold]Prerequisites:[/bold]
  On macOS: OrbStack is installed via 'metta install' (profile=softmax).
    Enable Kubernetes: orb config set k8s.enable true
    Then restart OrbStack (or: orbctl stop && orbctl start)

  In devcontainer/Linux: k3d is pre-installed. The setup command creates the cluster.

[bold]Quick start:[/bold]
  metta observatory local-k8s setup  # One-time: build image and create jobs namespace
  metta observatory up               # Start all services (postgres, server, frontend, watcher, tournament)

[bold]Start specific services:[/bold]
  metta observatory up server frontend  # Only server and frontend

[bold]Individual services:[/bold]
  metta observatory postgres up -d   # Backgrounded postgres for api server
  metta observatory server           # API server (uses LocalStack for S3)
  metta observatory frontend         # Observatory frontend
  metta observatory watcher          # Watches k8s jobs, reads results from S3
  metta observatory tournament run    # Tournament commissioner (creates matches, updates scores)
  metta observatory tournament roll-season <name>  # Roll a season to a new version

[bold]Upload policy:[/bold]
  uv run cogames submit -p baseline --server {LOCAL_BACKEND_URL} --skip-validation -n <your-policy-name>

[bold]Submit test jobs:[/bold]
  uv run python app_backend/scripts/submit_test_jobs.py --policy-uri metta://policy/<your-policy-name>

[bold]Monitor:[/bold]
  metta observatory local-k8s status   # Show K8s runtime and context
  metta observatory local-k8s get-pods # List job pods
  metta observatory local-k8s logs     # Follow job logs

[bold]Teardown:[/bold]
  metta observatory postgres down
  metta observatory local-k8s clean

[bold]Rebuild job runner image:[/bold]
  metta observatory local-k8s build-image
"""

app = typer.Typer(
    help=HELP_TEXT,
    rich_markup_mode="rich",
    no_args_is_help=True,
)


def _base_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("VIRTUAL_ENV", None)
    return env


def _get_db_uri() -> str:
    """Get the database URI, using host.docker.internal when in a container.

    CONTAINER NETWORKING EXPLAINED:
    When running in a devcontainer, PostgreSQL runs via docker-compose on the
    HOST's Docker daemon (not inside the devcontainer). This is because:
    1. We mount /var/run/docker.sock from the host
    2. docker-compose commands run against the host's Docker
    3. The postgres container runs in the host's Docker network

    From inside the devcontainer, 127.0.0.1:5432 refers to the devcontainer
    itself, not the host. We use Docker's host.docker.internal DNS name
    which resolves to the host machine from any container.

    DIRECT MAC DEVELOPMENT:
    When running directly on macOS (not in a container), 127.0.0.1 works
    because postgres runs on the same machine.
    """
    from metta.setup.tools.observatory.local_k8s import _is_running_in_container  # noqa: PLC0415

    if _is_running_in_container():
        # Postgres runs on the host's Docker, so use host.docker.internal
        return f"postgres://{POSTGRES_USER}:{POSTGRES_PASSWORD}@host.docker.internal:{POSTGRES_PORT}/{POSTGRES_DB}"
    return LOCAL_DB_URI


def _local_dev_env() -> dict[str, str]:
    env = _base_env()
    env["STATS_DB_URI"] = _get_db_uri()
    env["RUN_MIGRATIONS"] = "true"
    env["EPISODE_RUNNER_IMAGE"] = LOCAL_METTA_POLICY_EVAL_IMG_NAME
    env["MACHINE_TOKEN"] = LOCAL_MACHINE_TOKEN
    env["DEBUG_USER_EMAIL"] = LOCAL_MACHINE_TOKEN
    env["LOCAL_DEV"] = "true"
    env["LOCAL_DEV_K8S_CONTEXT"] = _get_k8s_context()
    env["LOCAL_DEV_AWS_PROFILE"] = LOCAL_AWS_PROFILE

    aws_path = os.path.expanduser("~/.aws")
    source_mounts = [
        f"{aws_path}:/root/.aws",
        f"{repo_root}/metta:/workspace/metta/metta",
        f"{repo_root}/app_backend:/workspace/metta/app_backend",
        f"{repo_root}/common:/workspace/metta/common",
    ]
    env["LOCAL_DEV_MOUNTS"] = ",".join(source_mounts)
    return env


def _postgres_env() -> dict[str, str]:
    env = _base_env()
    env["POSTGRES_HOST"] = LOCALHOST
    env["POSTGRES_PORT"] = str(POSTGRES_PORT)
    env["POSTGRES_USER"] = POSTGRES_USER
    env["POSTGRES_PASSWORD"] = POSTGRES_PASSWORD
    env["POSTGRES_DB"] = POSTGRES_DB
    return env


def _process_compose_env() -> dict[str, str]:
    """Environment for process-compose including K8s runtime detection.

    This function sets up all environment variables needed by process-compose.yaml.
    It handles the differences between direct Mac development and devcontainer.

    KEY ENVIRONMENT VARIABLES:
    - K8S_CONTEXT: kubectl context (orbstack or k3d-metta-local)
    - K8S_RUNTIME: Runtime type for conditional behavior
    - KUBECONFIG: Path to kubeconfig (modified for container access if needed)
    - POSTGRES_PROBE_HOST: Where to check for postgres (host.docker.internal in container)

    CONTAINER-SPECIFIC HANDLING:
    1. KUBECONFIG is set to the modified config with host.docker.internal
    2. POSTGRES_PROBE_HOST is set to host.docker.internal for readiness probes

    These allow process-compose services to work identically whether running
    directly on Mac or inside a devcontainer.
    """
    from metta.setup.tools.observatory.local_k8s import (  # noqa: PLC0415
        _get_orbstack_kubeconfig_for_container,
        _is_running_in_container,
    )

    env = _postgres_env()
    env["SERVER_HOST"] = LOCALHOST
    env["SERVER_PORT"] = str(SERVER_PORT)

    # Pass K8s context for kubectl commands in process-compose.yaml
    env["K8S_CONTEXT"] = _get_k8s_context()

    # Detect runtime for any conditional behavior
    runtime = detect_k8s_runtime()
    env["K8S_RUNTIME"] = runtime.value if runtime else "none"
    env["K3D_CLUSTER_NAME"] = K3D_CLUSTER_NAME

    # CONTAINER-TO-HOST KUBECONFIG:
    # When running in a container with OrbStack on the host, we need the
    # modified kubeconfig that uses host.docker.internal and skips TLS
    # verification. See local_k8s._get_orbstack_kubeconfig_for_container().
    modified_kubeconfig = _get_orbstack_kubeconfig_for_container()
    if modified_kubeconfig:
        env["KUBECONFIG"] = modified_kubeconfig

    # POSTGRES READINESS PROBE:
    # The postgres readiness probe in process-compose.yaml checks if postgres
    # is accepting connections. In a container, postgres runs on the host's
    # Docker, so we probe host.docker.internal instead of 127.0.0.1.
    if _is_running_in_container():
        env["POSTGRES_PROBE_HOST"] = "host.docker.internal"

    return env


@app.command(name="up", help="Start all observatory services (postgres, server, frontend, watcher)")
@handle_errors
def up(
    services: Annotated[list[str] | None, typer.Argument(help="Services to start (default: all)")] = None,
    tui: Annotated[bool, typer.Option("-t", "--tui", help="Enable TUI mode")] = False,
):
    compose_file = Path(__file__).parent / "process-compose.yaml"
    env = _process_compose_env()
    cmd = ["process-compose", "-f", str(compose_file), "-p", str(PROCESS_COMPOSE_PORT)]
    if not tui:
        cmd.append("-t=false")
    if services:
        cmd.append("up")
        cmd.extend(services)
    info("Starting observatory services...")
    subprocess.run(cmd, cwd=repo_root, env=env, check=True)


@app.command(
    name="postgres",
    context_settings={"allow_extra_args": True, "allow_interspersed_args": False},
    help="Manage postgres. Usage: metta observatory postgres [up|down|logs]",
)
@handle_errors
def postgres(ctx: typer.Context):
    cmd = ["docker", "compose", "-f", str(repo_root / "app_backend" / "docker-compose.dev.yml")]
    args = ctx.args if ctx.args else ["up"]
    if "up" in args and "-d" in args and "--wait" not in args:
        args = args + ["--wait"]
    cmd.extend(args)
    subprocess.run(cmd, env=_postgres_env(), check=True)


@app.command(name="server", help="Run the backend server on host")
@handle_errors
def server():
    env = _local_dev_env()
    env["HOST"] = "0.0.0.0"
    env["PORT"] = str(SERVER_PORT)
    env["STATS_SERVER_URI"] = _get_backend_url_from_k8s()
    # S3-specific endpoint so only S3 calls go to localstack.
    # Using the global AWS_ENDPOINT_URL would also route SSO credential refresh
    # through localstack, which breaks presigning.
    env["AWS_ENDPOINT_URL_S3"] = LOCALSTACK_ENDPOINT_HOST
    # Presigned URLs use host.docker.internal so pods can access them
    env["S3_PRESIGNED_ENDPOINT"] = LOCALSTACK_ENDPOINT_K8S
    env["EVAL_S3_BUCKET"] = LOCAL_EVAL_BUCKET
    env["POLICY_S3_BUCKET"] = LOCAL_EVAL_BUCKET

    info("Starting backend server...")
    subprocess.run(
        ["uv", "run", "python", str(repo_root / "app_backend/src/metta/app_backend/server.py")],
        env=env,
        check=True,
    )


@app.command(name="watcher", help="Run the job watcher on host")
@handle_errors
def watcher():
    env = _local_dev_env()
    env["STATS_SERVER_URI"] = LOCAL_BACKEND_URL
    env["AWS_ENDPOINT_URL_S3"] = LOCALSTACK_ENDPOINT_HOST
    env["EVAL_S3_BUCKET"] = LOCAL_EVAL_BUCKET

    info("Starting watcher...")
    subprocess.run(
        ["uv", "run", "python", "-m", "metta.app_backend.job_runner.watcher"],
        env=env,
        check=True,
    )


@app.command(name="frontend")
@handle_errors
def frontend(
    backend: Annotated[str, typer.Option("--backend", "-b", help="Select backend: local or prod")] = "local",
    skip_auto_auth: Annotated[
        bool, typer.Option("--skip-auto-auth", "-d", help="Don't authenticate with the backend on launch")
    ] = False,
):
    env = _base_env()

    if backend == "local":
        env["OBSERVATORY_API_URL"] = LOCAL_BACKEND_URL
        if not skip_auto_auth:
            env["DEV_AUTH_TOKEN"] = LOCAL_MACHINE_TOKEN
        info(f"Connecting to local backend at {LOCAL_BACKEND_URL}")
    else:
        env["OBSERVATORY_API_URL"] = PROD_STATS_SERVER_URI
        if not skip_auto_auth and (token := get_machine_token(env["OBSERVATORY_API_URL"])):
            env["DEV_AUTH_TOKEN"] = token
        info("Connecting to prod backend")

    info("Starting Observatory frontend")
    info(f"API URL: {env.get('OBSERVATORY_API_URL')}")

    subprocess.run(["pnpm", "run", "dev"], env=env, check=True, cwd=repo_root / "web/observatory")


tournament_app = typer.Typer(help="Tournament management", rich_markup_mode="rich", no_args_is_help=True)


@tournament_app.command(name="run")
@handle_errors
def tournament_run():
    """Run the tournament commissioner."""
    env = _local_dev_env()
    subprocess.run(
        ["uv", "run", "python", str(repo_root / "app_backend/src/metta/app_backend/tournament/cli.py")],
        env=env,
        check=True,
    )


@tournament_app.command(name="roll-season")
@handle_errors
def tournament_roll_season(
    season_name: Annotated[str, typer.Argument(help="Season name to roll (e.g. beta-cogsguard)")],
):
    """Roll a season to a new version, migrating active members."""
    env = _local_dev_env()
    subprocess.run(
        [
            "uv",
            "run",
            "python",
            "-c",
            f"from metta.app_backend.tournament.cli import roll_season; roll_season({season_name!r})",
        ],
        env=env,
        check=True,
    )


app.add_typer(tournament_app, name="tournament")
app.add_typer(local_k8s_app, name="local-k8s")


def main():
    app()


if __name__ == "__main__":
    main()
