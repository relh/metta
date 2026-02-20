from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StableCheckContext:
    job_name: str
    inputs: dict[str, str]
