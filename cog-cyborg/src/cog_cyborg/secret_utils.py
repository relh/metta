from __future__ import annotations

import os
from pathlib import Path


def resolve_api_key(
    *,
    direct_value: str | None,
    file_path: str | Path | None,
    env_var: str,
) -> str | None:
    if direct_value:
        return direct_value.strip()

    if file_path:
        return Path(file_path).read_text().strip()

    value = os.getenv(env_var)
    if value:
        return value.strip()

    return None
