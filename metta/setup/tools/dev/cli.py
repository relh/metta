#!/usr/bin/env -S uv run
"""CLI for running local dev services.

This module orchestrates all services for local development:
- PostgreSQL database
- FastAPI backend server
- Softmax.com website frontend
- K8s job watcher
- Tournament commissioner

=============================================================================
DEVCONTAINER SUPPORT
=============================================================================

This CLI supports running inside a devcontainer on macOS. The key challenges:

1. DATABASE CONNECTION
   PostgreSQL runs via docker-compose on the HOST's Docker (not in devcontainer).
   From inside the container, we connect via host.docker.internal:5432.
   See get_db_uri() for the implementation.

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
import json
import os
import subprocess
from pathlib import Path
from typing import Annotated

import typer

from metta.common.util.constants import DEV_STATS_SERVER_URI, PROD_STATS_SERVER_URI
from metta.common.util.fs import get_repo_root
from metta.setup.tools.dev.env import base_env, postgres_env
from metta.setup.tools.dev.local_k8s import (
    K3D_CLUSTER_NAME,
    _get_orbstack_kubeconfig_for_container,
    detect_k8s_runtime,
    get_host_address,
    get_k8s_context,
    local_k8s_app,
)
from metta.setup.tools.dev.postgres import get_db_uri, postgres_cmd
from metta.setup.tools.dev.run_episode import run_episode_cmd
from metta.setup.tools.dev.utils import LOCAL_METTA_POLICY_EVAL_IMG_NAME
from metta.setup.utils import error, info
from softmax.aws.secrets_manager import get_secretsmanager_secret

repo_root = get_repo_root()

# =============================================================================
# LOCAL DEV CONFIGURATION
# =============================================================================
# These values are used for the local development environment.
# LOCALHOST is used for services binding and health checks.
# For container->host communication, we use host.docker.internal (see get_db_uri).

LOCALHOST = "127.0.0.1"
SERVER_PORT = 8000
PROCESS_COMPOSE_PORT = 8090
LOCALSTACK_PORT = 4566
LOCALSTACK_ENDPOINT_HOST = f"http://{LOCALHOST}:{LOCALSTACK_PORT}"
LOCALSTACK_ENDPOINT_K8S = f"http://host.docker.internal:{LOCALSTACK_PORT}"
LOCAL_EVAL_BUCKET = "eval-bucket"

LOCAL_BACKEND_URL = f"http://{LOCALHOST}:{SERVER_PORT}"
LOCAL_MACHINE_TOKEN = "local-dev-user@example.com"
LOCAL_AWS_PROFILE = "softmax"
LOCAL_OBSERVATORY_AUTH_SECRET = "local-observatory-auth-secret"
LOCAL_LOGIN_SERVICE_URL = "http://localhost:3002"  # Local softmax.com frontend
PROD_LOGIN_SERVICE_URL = "https://softmax.com"


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
Run services for local development.

[bold]Prerequisites:[/bold]
  On macOS: OrbStack is installed via 'metta install' (profile=softmax).
    Enable Kubernetes: orb config set k8s.enable true
    Then restart OrbStack (or: orbctl stop && orbctl start)

  In devcontainer/Linux: k3d is pre-installed. The setup command creates the cluster.

[bold]Quick start:[/bold]
  metta dev local-k8s setup  # One-time: build image and create jobs namespace
  metta dev up               # Start all services (postgres, server, watcher, tournament)

[bold]Start specific services:[/bold]
  metta dev up server  # Only server

[bold]Individual services:[/bold]
  metta dev postgres up -d   # Backgrounded postgres for api server
  metta dev server           # API server (uses LocalStack for S3)
  metta dev watcher          # Watches k8s jobs, reads results from S3
  metta dev tournament run    # Tournament commissioner (creates matches, updates scores)
  metta dev tournament roll-season <name>  # Roll a season to a new version

[bold]Upload policy:[/bold]
  uv run cogames submit -p baseline --server {LOCAL_BACKEND_URL} --skip-validation -n <your-policy-name>

[bold]Submit test jobs:[/bold]
  uv run python app_backend/scripts/submit_test_jobs.py --policy-uri metta://policy/<your-policy-name>

[bold]Monitor:[/bold]
  metta dev local-k8s status   # Show K8s runtime and context
  metta dev local-k8s get-pods # List job pods
  metta dev local-k8s logs     # Follow job logs

[bold]Teardown:[/bold]
  metta dev down             # Stop all services
  metta dev postgres down
  metta dev local-k8s clean

[bold]Run a single episode:[/bold]
  metta dev run-episode job.json                        # Local subprocess (default)
  metta dev run-episode job.json -m local-image         # In locally-built Docker image
  metta dev run-episode job.json -m prod-image          # In production Docker image
  metta dev run-episode <uuid> -m local-image           # Fetch from observatory, run in Docker

[bold]Rebuild job runner image:[/bold]
  metta dev local-k8s build-image
"""

app = typer.Typer(
    help=HELP_TEXT,
    rich_markup_mode="rich",
    no_args_is_help=True,
)


def _kill_stale_processes() -> None:
    """Kill any leftover processes from a previous run."""
    result = subprocess.run(
        ["process-compose", "down", "-p", str(PROCESS_COMPOSE_PORT)],
        capture_output=True,
        timeout=10,
    )
    if result.returncode == 0:
        info("Stopped previous instance")
        return

    # Fallback: kill anything holding our ports (process-compose was likely hard-killed)
    for port in (PROCESS_COMPOSE_PORT, SERVER_PORT):
        result = subprocess.run(["lsof", "-ti", f":{port}"], capture_output=True, text=True)
        pids = result.stdout.strip()
        if pids:
            info(f"Killing stale process on port {port}")
            subprocess.run(["kill", *pids.split("\n")])


def _local_dev_env() -> dict[str, str]:
    env = base_env()
    env["STATS_DB_URI"] = get_db_uri("metta")
    env["RUN_MIGRATIONS"] = "true"
    env["EPISODE_RUNNER_IMAGE"] = LOCAL_METTA_POLICY_EVAL_IMG_NAME
    env["MACHINE_TOKEN"] = LOCAL_MACHINE_TOKEN
    env["DEBUG_USER_EMAIL"] = LOCAL_MACHINE_TOKEN
    env["LOCAL_DEV"] = "true"
    env["LOCAL_DEV_K8S_CONTEXT"] = _get_k8s_context()
    env["LOCAL_DEV_AWS_PROFILE"] = LOCAL_AWS_PROFILE
    env["OBSERVATORY_AUTH_SECRET"] = LOCAL_OBSERVATORY_AUTH_SECRET
    env["ENABLE_MOCK_TOURNAMENTS"] = "true"

    discord_raw = get_secretsmanager_secret("discord/oauth-dev", require_exists=False)
    if discord_raw is not None:
        discord_secret = json.loads(discord_raw)
        env["DISCORD_BOT_TOKEN"] = discord_secret["DISCORD_BOT_TOKEN"]

    aws_path = os.path.expanduser("~/.aws")
    source_mounts = [
        f"{aws_path}:/root/.aws",
        f"{repo_root}/metta:/workspace/metta/metta",
        f"{repo_root}/app_backend:/workspace/metta/app_backend",
        f"{repo_root}/common:/workspace/metta/common",
    ]
    env["LOCAL_DEV_MOUNTS"] = ",".join(source_mounts)
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

    # some postgres vars are needed for health checks or other processes, so can't be localized to postgres process
    env = postgres_env()

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

    return env


@app.command(name="up", help="Start all services (postgres, server, watcher)")
@handle_errors
def up(
    services: Annotated[list[str] | None, typer.Argument(help="Services to start (default: all)")] = None,
    tui: Annotated[bool, typer.Option("-t", "--tui", help="Enable TUI mode")] = False,
    login_server: Annotated[str, typer.Option("--login-server", "-l", help="Login server: local or prod")] = "local",
    force: Annotated[bool, typer.Option("--force", "-f", help="Kill stale processes before starting")] = False,
):
    if force:
        _kill_stale_processes()
    compose_file = Path(__file__).parent / "process-compose.yaml"
    env = _process_compose_env()

    if login_server == "local":
        env["LOGIN_SERVICE_URL"] = LOCAL_LOGIN_SERVICE_URL
    else:
        env["LOGIN_SERVICE_URL"] = PROD_LOGIN_SERVICE_URL
    info(f"Using login server: {env['LOGIN_SERVICE_URL']}")

    cmd = ["process-compose", "-f", str(compose_file), "-p", str(PROCESS_COMPOSE_PORT)]
    if not tui:
        cmd.append("-t=false")
    if services:
        cmd.append("up")
        cmd.extend(services)
    info("Starting observatory services...")
    subprocess.run(cmd, cwd=repo_root, env=env, check=True)


@app.command(name="down", help="Stop all dev services")
@handle_errors
def down():
    subprocess.run(
        ["process-compose", "down", "-p", str(PROCESS_COMPOSE_PORT)],
        check=True,
    )


@app.command(name="restart", help="Restart one or more dev services (e.g. metta dev restart server)")
@handle_errors
def restart(
    services: Annotated[list[str], typer.Argument(help="Services to restart")],
):
    for svc in services:
        info(f"Restarting {svc}...")
        subprocess.run(
            ["process-compose", "process", "restart", svc, "-p", str(PROCESS_COMPOSE_PORT)],
            check=True,
        )


@app.command(name="stop", help="Stop one or more services (e.g. metta dev stop server)")
@handle_errors
def stop(
    services: Annotated[list[str], typer.Argument(help="Services to stop")],
):
    for svc in services:
        info(f"Stopping {svc}...")
        subprocess.run(
            ["process-compose", "process", "stop", svc, "-p", str(PROCESS_COMPOSE_PORT)],
            check=True,
        )


app.command(
    name="postgres",
    context_settings={"allow_extra_args": True, "allow_interspersed_args": False},
    help="Manage postgres. Usage: metta dev postgres [up|down|logs]",
)(handle_errors(postgres_cmd))


@app.command(name="server", help="Run the backend server on host")
@handle_errors
def server(
    login_server: Annotated[str, typer.Option("--login-server", "-l", help="Login server: local or prod")] = "local",
    otel_console: Annotated[bool, typer.Option("--otel-console", help="Print OTel metrics to stdout")] = False,
):
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
    if otel_console:
        env["OTEL_METRICS_CONSOLE"] = "true"

    # Respect LOGIN_SERVICE_URL from environment (set by `up` command), otherwise use --login-server flag
    if "LOGIN_SERVICE_URL" not in env:
        if login_server == "local":
            env["LOGIN_SERVICE_URL"] = LOCAL_LOGIN_SERVICE_URL
        else:
            env["LOGIN_SERVICE_URL"] = PROD_LOGIN_SERVICE_URL
    info(f"Login server URL: {env['LOGIN_SERVICE_URL']}")

    info("Starting backend server...")
    subprocess.run(
        ["uv", "run", "python", str(repo_root / "app_backend/src/metta/app_backend/server.py")],
        env=env,
        check=True,
    )


@app.command(
    name="softmax-com",
    help="Start the Softmax.com frontend. Usage: metta dev softmax-com [--backend local|prod]",
)
@handle_errors
def softmax_com(
    backend: Annotated[str, typer.Option("--backend", "-b", help="Select backend: local or prod")] = "local",
):
    env = base_env()
    env.setdefault("NEXTAUTH_URL", f"http://{LOCALHOST}:3002")  # must match the port from web/softmax.com/package.json
    env["SITE_URL"] = f"http://{LOCALHOST}:3002"
    env.setdefault("NEXTAUTH_SECRET", "dev-nextauth-secret")
    env["DATABASE_URL"] = get_db_uri("softmax-com")

    # These are tied to a sandbox oauth app under nishu-builder's account.
    # These are not production keys.
    # In production, we use a custom Github App, which require two more fields:
    # GITHUB_INSTALLATION_ID and GITHUB_APP_PEM.
    # Those two fields are optional but allow us to populate GitHubTeamMember table.
    github_oauth_raw = get_secretsmanager_secret("github/oauth-dev", require_exists=False)
    if github_oauth_raw is not None:
        github_oauth_secret = json.loads(github_oauth_raw)
        env.setdefault("GITHUB_CLIENT_ID", github_oauth_secret["GITHUB_CLIENT_ID"])
        env.setdefault("GITHUB_CLIENT_SECRET", github_oauth_secret["GITHUB_CLIENT_SECRET"])

    discord_oauth_raw = get_secretsmanager_secret("discord/oauth-dev", require_exists=False)
    if discord_oauth_raw is not None:
        discord_oauth_secret = json.loads(discord_oauth_raw)
        env["DISCORD_CLIENT_ID"] = discord_oauth_secret["DISCORD_CLIENT_ID"]
        env["DISCORD_CLIENT_SECRET"] = discord_oauth_secret["DISCORD_CLIENT_SECRET"]

    # Respect OBSERVATORY_API_URL from environment (set by `up` command), otherwise use --backend flag
    if "OBSERVATORY_API_URL" not in env:
        if backend == "local":
            env["OBSERVATORY_API_URL"] = DEV_STATS_SERVER_URI
            env["OBSERVATORY_AUTH_SECRET"] = LOCAL_OBSERVATORY_AUTH_SECRET
        else:
            env["OBSERVATORY_API_URL"] = PROD_STATS_SERVER_URI

    info(f"Observatory API URL: {env.get('OBSERVATORY_API_URL')}")
    info("Generating Prisma client")
    subprocess.run(["pnpm", "db:generate"], env=env, check=True, cwd=repo_root / "web/softmax.com")

    info("Starting Softmax.com frontend")

    subprocess.run(["pnpm", "run", "dev"], env=env, check=True, cwd=repo_root / "web/softmax.com")


@app.command(name="softmax-com-db-migrate", help="Apply Prisma migrations to the local softmax_com database")
@handle_errors
def db_migrate():
    env = base_env()
    env["DATABASE_URL"] = get_db_uri("softmax-com")
    info("Applying Prisma migrations to local softmax_com database")
    subprocess.run(["pnpm", "db:migrate"], env=env, check=True, cwd=repo_root / "web/softmax.com")


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


@app.command(name="event-processor", help="Run the job event processor on host")
@handle_errors
def event_processor():
    env = _local_dev_env()
    env["STATS_SERVER_URI"] = LOCAL_BACKEND_URL
    env["AWS_ENDPOINT_URL_S3"] = LOCALSTACK_ENDPOINT_HOST
    env["EVAL_S3_BUCKET"] = LOCAL_EVAL_BUCKET
    env["HEALTH_PORT"] = "8082"  # Avoid collision with watcher (8080) and tournament (8081)

    info("Starting event processor...")
    subprocess.run(
        ["uv", "run", "python", "-m", "metta.app_backend.job_runner.event_processor"],
        env=env,
        check=True,
    )


@app.command(
    name="generate-api-types",
    help="Generate TypeScript and Python API types from the OpenAPI spec",
)
@handle_errors
def generate_api_types():
    # TypeScript types (softmax.com frontend)
    roots = [repo_root / "web/softmax.com"]
    for root in roots:
        subprocess.run(["pnpm", "run", "generate-api-types"], cwd=root, check=True)

    # Python models (cogames CLI)
    info("Generating cogames Python models...")
    subprocess.run(
        ["uv", "run", "python", str(repo_root / "packages" / "cogames" / "scripts" / "generate_models.py")],
        check=True,
    )


app.command(name="run-episode")(handle_errors(run_episode_cmd))


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


ROLL_SEASON_SCRIPT = str(repo_root / "app_backend/src/metta/app_backend/tournament/scripts/roll_season.py")


@tournament_app.command(name="roll-season")
@handle_errors
def tournament_roll_season(
    season_name: Annotated[str, typer.Argument(help="Season name to roll (e.g. beta-cogsguard)")],
    migrate_players: Annotated[
        bool, typer.Option("--migrate-players", help="Migrate active players to the new season")
    ] = False,
    compat_version: Annotated[
        str | None, typer.Option("--compat-version", help="Set compat version (default: carry forward from previous)")
    ] = None,
):
    """Roll a season to a new version."""
    env = _local_dev_env()
    cmd = ["uv", "run", "python", ROLL_SEASON_SCRIPT, season_name]
    if migrate_players:
        cmd.append("--migrate-players")
    if compat_version is not None:
        cmd.extend(["--compat-version", compat_version])
    subprocess.run(cmd, env=env, check=True)


app.add_typer(tournament_app, name="tournament")
app.add_typer(local_k8s_app, name="local-k8s")


def main():
    app()


if __name__ == "__main__":
    main()
