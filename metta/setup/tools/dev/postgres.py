import subprocess
from pathlib import Path
from typing import Literal

import typer

from metta.setup.tools.dev.env import POSTGRES_PASSWORD, POSTGRES_PORT, POSTGRES_USER, postgres_env
from metta.setup.tools.dev.local_k8s import _is_running_in_container


def get_db_uri(db: Literal["metta", "softmax-com"]) -> str:
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

    host = "127.0.0.1"
    if _is_running_in_container():
        # Postgres runs on the host's Docker, so use host.docker.internal
        host = "host.docker.internal"
    return f"postgres://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{host}:{POSTGRES_PORT}/{db}"


def postgres_cmd(ctx: typer.Context):
    cmd = ["docker", "compose", "-f", str(Path(__file__).parent / "docker-compose.yml")]
    args = ctx.args if ctx.args else ["up"]
    if "up" in args and "-d" in args and "--wait" not in args:
        args = args + ["--wait"]
    cmd.extend(args)
    subprocess.run(cmd, env=postgres_env(), check=True)
