"""Asana API utilities for Gas Town integration."""

from __future__ import annotations

import re
from urllib.parse import urlparse

import asana as asana_sdk


def asana_client(token: str) -> asana_sdk.ApiClient:
    """Create an authenticated Asana API client."""
    config = asana_sdk.Configuration()
    config.access_token = token
    config.connection_pool_kw = {"timeout": 30}
    return asana_sdk.ApiClient(config)


def extract_task_gid(value: str) -> str:
    """Extract task GID from URL or raw value.

    Asana URLs are typically: https://app.asana.com/0/<project_gid>/<task_gid>
    The task GID is the LAST numeric segment, not the first.
    """
    if value.isdigit():
        return value
    # Check for /task/<gid> pattern first (some Asana URLs use this)
    match = re.search(r"/task/(\d+)", value)
    if match:
        return match.group(1)
    # For standard URLs, extract the last numeric path segment (task GID).
    parsed = urlparse(value)
    if parsed.path:
        segments = [segment for segment in parsed.path.split("/") if segment]
        for segment in reversed(segments):
            if segment.isdigit():
                return segment
    # Fallback: take the last long numeric segment anywhere in the string.
    matches = re.findall(r"\b(\d{12,})\b", value)
    if matches:
        return matches[-1]
    raise ValueError(f"Could not extract task gid from: {value}")
