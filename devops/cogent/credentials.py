#!/usr/bin/env python3
"""Fetch secrets from AWS Secrets Manager at runtime.

Replaces the old pattern of sourcing ~/.config/metta/credentials.sh.
Secrets live only in Secrets Manager and transiently in process memory.

The instance's IAM role (cogent-role) grants secretsmanager:GetSecretValue.
"""

import os
import subprocess
import time

REGION = "us-east-1"

# env-var name → Secrets Manager secret ID (matches cogent-boot.sh)
# Claude auth is handled by Bedrock via the instance IAM role — no API key needed.
SECRET_IDS: dict[str, str] = {
    "OPENAI_API_KEY": "openai/agent-api-key",
    "WANDB_API_KEY": "wandb/api-key",
    "DISCORD_WEBHOOK_URL": "discord/agent-webhook-url",
    "AGENT_GITHUB_APP_ID": "github/agent-app-id",
    "AGENT_GITHUB_APP_PRIVATE_KEY": "github/agent-app-private-key",
    "ASANA_TOKEN": "asana/api-key",
    "ASANA_WORKSPACE_GID": "asana/workspace-gid",
    "ASANA_AGENT_USER_GID": "asana/agent-user-gid",
    "ASANA_RUNNING_TAG_GID": "asana/running-tag-gid",
}

_cache: dict[str, str] = {}
_cache_time: float = 0
_CACHE_TTL_S = 300


def _fetch_secret(secret_id: str) -> str:
    result = subprocess.run(
        [
            "aws",
            "secretsmanager",
            "get-secret-value",
            "--secret-id",
            secret_id,
            "--query",
            "SecretString",
            "--output",
            "text",
            "--region",
            REGION,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def load_credentials(keys: list[str] | None = None):
    """Fetch secrets from Secrets Manager and set as env vars.

    Args:
        keys: Subset of SECRET_IDS keys to load. None means all.
    """
    global _cache, _cache_time  # noqa: PLW0603
    now = time.monotonic()

    if _cache and (now - _cache_time) < _CACHE_TTL_S:
        for k, v in _cache.items():
            if keys is None or k in keys:
                os.environ[k] = v
        return

    targets = keys or list(SECRET_IDS)
    new_cache: dict[str, str] = {}
    for env_key in targets:
        secret_id = SECRET_IDS.get(env_key)
        if not secret_id:
            continue
        value = _fetch_secret(secret_id)
        if value:
            os.environ[env_key] = value
            new_cache[env_key] = value

    _cache = new_cache
    _cache_time = now


if __name__ == "__main__":
    import sys

    if "--export" in sys.argv:
        load_credentials()
        for key in SECRET_IDS:
            val = os.environ.get(key, "")
            if val:
                print(f"export {key}={val!r}")
    else:
        print("Usage: credentials.py --export")
        print("  Prints shell export statements for all secrets.")
        sys.exit(1)
