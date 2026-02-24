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
from metta.setup.tools.observatory.cli import LOCAL_OBSERVATORY_AUTH_SECRET
from metta.setup.utils import error, info
from softmax.aws.secrets_manager import get_secretsmanager_secret

repo_root = get_repo_root()

# Local dev configuration
LOCALHOST = "localhost"
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
    backend: Annotated[str, typer.Option("--backend", "-b", help="Select backend: local or prod")] = "local",
):
    compose_file = Path(__file__).parent / "process-compose.yaml"
    env = _postgres_env()

    if backend == "local":
        env["OBSERVATORY_API_URL"] = DEV_STATS_SERVER_URI
        env["OBSERVATORY_AUTH_SECRET"] = LOCAL_OBSERVATORY_AUTH_SECRET
    else:
        env["OBSERVATORY_API_URL"] = PROD_STATS_SERVER_URI
    info(f"Using backend: {backend} ({env['OBSERVATORY_API_URL']})")

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
    backend: Annotated[str, typer.Option("--backend", "-b", help="Select backend: local or prod")] = "local",
):
    env = _base_env()
    env["NEXTAUTH_URL"] = f"http://{LOCALHOST}:3002"  # must match the port from web/softmax.com/package.json
    env["NEXTAUTH_SECRET"] = "dev-nextauth-secret"
    env["DATABASE_URL"] = LOCAL_DB_URI

    # These are tied to a sandbox oauth app under nishu-builder's account.
    # These are not production keys.
    # In production, we use a custom Github App, which require two more fields:
    # GITHUB_INSTALLATION_ID and GITHUB_APP_PEM.
    # Those two fields are optional but allow us to populate GitHubTeamMember table.
    github_oauth_raw = get_secretsmanager_secret("github/oauth-dev", require_exists=False)
    if github_oauth_raw is not None:
        github_oauth_secret = json.loads(github_oauth_raw)
        env["GITHUB_CLIENT_ID"] = github_oauth_secret["GITHUB_CLIENT_ID"]
        env["GITHUB_CLIENT_SECRET"] = github_oauth_secret["GITHUB_CLIENT_SECRET"]

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


if __name__ == "__main__":
    app()
