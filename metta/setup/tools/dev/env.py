import os

from dotenv import dotenv_values

from metta.common.util.fs import get_repo_root
from metta.setup.tools.dev.local_k8s import _is_running_in_container

POSTGRES_PORT = 5432
POSTGRES_USER = "postgres"
POSTGRES_PASSWORD = "password"
POSTGRES_DB = "metta"


def base_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("VIRTUAL_ENV", None)
    # .env provides defaults — real env vars take precedence.
    # dotenv_values returns None for keys with no value; we skip those.
    for key, value in dotenv_values(get_repo_root() / ".env").items():
        if key not in env and value is not None:
            env[key] = value
    return env


def postgres_env() -> dict[str, str]:
    env = base_env()
    env["POSTGRES_HOST"] = "127.0.0.1"
    env["POSTGRES_PORT"] = str(POSTGRES_PORT)
    env["POSTGRES_USER"] = POSTGRES_USER
    env["POSTGRES_PASSWORD"] = POSTGRES_PASSWORD
    env["POSTGRES_DB"] = POSTGRES_DB

    # POSTGRES READINESS PROBE:
    # The postgres readiness probe in process-compose.yaml checks if postgres
    # is accepting connections. In a container, postgres runs on the host's
    # Docker, so we probe host.docker.internal instead of 127.0.0.1.
    if _is_running_in_container():
        env["POSTGRES_PROBE_HOST"] = "host.docker.internal"

    return env
