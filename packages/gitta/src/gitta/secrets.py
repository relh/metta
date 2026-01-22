from __future__ import annotations

import logging
import os
import subprocess

logger = logging.getLogger(__name__)


def get_github_token() -> str | None:
    """Get GitHub token from GITHUB_TOKEN env var or gh CLI."""
    if token := os.environ.get("GITHUB_TOKEN"):
        logger.debug("Using GITHUB_TOKEN from environment variable")
        return token

    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            check=True,
        )
        if token := result.stdout.strip():
            logger.debug("Using GitHub token from gh CLI")
            return token
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    return None
