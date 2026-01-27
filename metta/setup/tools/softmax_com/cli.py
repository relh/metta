#!/usr/bin/env -S uv run
import functools
import json
import os
import subprocess
from pathlib import Path
from typing import Annotated

import typer

from metta.common.util.constants import DEV_STATS_SERVER_URI, PROD_STATS_SERVER_URI
from metta.common.util.fs import get_repo_root
from metta.setup.utils import error, info
from softmax.aws.secrets_manager import get_secretsmanager_secret

repo_root = get_repo_root()

# Local dev configuration
LOCALHOST = "127.0.0.1"
POSTGRES_PORT = 5433  # next port after 5432, which is used by the observatory postgres
POSTGRES_USER = "postgres"
POSTGRES_PASSWORD = "password"
POSTGRES_DB = "softmax_com"
PROCESS_COMPOSE_PORT = 8091

LOCAL_DB_URI = f"postgres://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{LOCALHOST}:{POSTGRES_PORT}/{POSTGRES_DB}"


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


HELP_TEXT = """
Softmax.com local development.

[bold]Quick start:[/bold]
  metta softmax-com up               # Start all services (postgres, frontend)

[bold]Start specific services:[/bold]
  metta softmax-com up frontend  # Only frontend

[bold]Individual services:[/bold]
  metta softmax-com postgres up -d   # Backgrounded postgres
  metta softmax-com frontend         # Softmax.com frontend

[bold]Teardown:[/bold]
  metta softmax-com postgres down

[bold green]If you're starting this for the first time, you need to run:[/bold green]
  pnpm db:migrate   # From web/softmax.com directory
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


def _postgres_env() -> dict[str, str]:
    env = _base_env()
    env["POSTGRES_HOST"] = LOCALHOST
    env["POSTGRES_PORT"] = str(POSTGRES_PORT)
    env["POSTGRES_USER"] = POSTGRES_USER
    env["POSTGRES_PASSWORD"] = POSTGRES_PASSWORD
    env["POSTGRES_DB"] = POSTGRES_DB
    return env


@app.command(name="up", help="Start all Softmax.com services (postgres, frontend)")
@handle_errors
def up(
    services: Annotated[list[str] | None, typer.Argument(help="Services to start (default: all)")] = None,
    tui: Annotated[bool, typer.Option("-t", "--tui", help="Enable TUI mode")] = False,
):
    compose_file = Path(__file__).parent / "process-compose.yaml"
    env = _postgres_env()
    cmd = ["process-compose", "-f", str(compose_file), "-p", str(PROCESS_COMPOSE_PORT)]
    if not tui:
        cmd.append("-t=false")
    if services:
        cmd.extend(services)
    info("Starting Softmax.com services...")
    subprocess.run(cmd, cwd=repo_root, env=env, check=True)


@app.command(
    name="postgres",
    context_settings={"allow_extra_args": True, "allow_interspersed_args": False},
    help="Manage postgres. Usage: metta softmax-com postgres [up|down|logs]",
)
@handle_errors
def postgres(ctx: typer.Context):
    cmd = ["docker", "compose", "-f", str(repo_root / "web/softmax.com/docker-compose.dev.yml")]
    args = ctx.args if ctx.args else ["up"]
    if "up" in args and "-d" in args and "--wait" not in args:
        args = args + ["--wait"]
    cmd.extend(args)
    subprocess.run(cmd, env=_postgres_env(), check=True)


@app.command(
    name="frontend",
    help="Start the Softmax.com frontend. Usage: metta softmax-com frontend [--backend local|prod]",
)
@handle_errors
def frontend(
    backend: Annotated[str, typer.Option("--backend", "-b", help="Select backend: local or prod")] = "prod",
):
    env = _base_env()
    env["NEXTAUH_URL"] = f"http://{LOCALHOST}:3002"  # must match the port from web/softmax.com/package.json
    env["NEXTAUTH_SECRET"] = "dev-nextauth-secret"
    env["DATABASE_URL"] = LOCAL_DB_URI

    # These are tied to a sandbox oauth app under nishu-builder's account.
    # These are not production keys.
    # In production, we use a custom Github App, which require two more fields:
    # GITHUB_INSTALLATION_ID and GITHUB_APP_PEM.
    # Those two fields are optional but allow us to populate GitHubTeamMember table.
    oauth_secret = json.loads(get_secretsmanager_secret("github/oauth-dev"))
    env["GITHUB_CLIENT_ID"] = oauth_secret["GITHUB_CLIENT_ID"]
    env["GITHUB_CLIENT_SECRET"] = oauth_secret["GITHUB_CLIENT_SECRET"]

    if backend == "local":
        env["OBSERVATORY_API_URL"] = DEV_STATS_SERVER_URI
    else:
        env["OBSERVATORY_API_URL"] = PROD_STATS_SERVER_URI

    info(f"Observatory API URL: {env.get('OBSERVATORY_API_URL')}")
    info("Starting Softmax.com frontend")

    subprocess.run(["pnpm", "run", "dev"], env=env, check=True, cwd=repo_root / "web/softmax.com")


if __name__ == "__main__":
    app()
