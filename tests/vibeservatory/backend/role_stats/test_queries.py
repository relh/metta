from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from cachetools import TTLCache

from vibeservatory.backend.dashboard_backend.role_stats import queries


class _MappingsResult:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def all(self) -> list[dict[str, Any]]:
        return self._rows


class _ExecuteResult:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def mappings(self) -> _MappingsResult:
        return _MappingsResult(self._rows)


class _FakeSession:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows
        self.execute_count = 0

    async def execute(self, _stmt: Any) -> _ExecuteResult:
        self.execute_count += 1
        return _ExecuteResult(self._rows)


def _metric_rows(policy_a: Any, policy_b: Any) -> list[dict[str, Any]]:
    return [
        {"policy_version_id": policy_a, "metric_name": "scout.gained", "avg_value": 10.0, "sample_count": 12},
        {"policy_version_id": policy_b, "metric_name": "scout.gained", "avg_value": 4.0, "sample_count": 12},
        {"policy_version_id": policy_a, "metric_name": "reward", "avg_value": 8.0, "sample_count": 12},
        {"policy_version_id": policy_b, "metric_name": "reward", "avg_value": 3.0, "sample_count": 12},
        {"policy_version_id": policy_a, "metric_name": "cell.visited", "avg_value": 20.0, "sample_count": 12},
        {"policy_version_id": policy_b, "metric_name": "cell.visited", "avg_value": 9.0, "sample_count": 12},
        {"policy_version_id": policy_a, "metric_name": "miner.gained", "avg_value": 1.0, "sample_count": 12},
        {"policy_version_id": policy_b, "metric_name": "miner.gained", "avg_value": 3.0, "sample_count": 12},
        {"policy_version_id": policy_a, "metric_name": "scrambler.gained", "avg_value": 1.0, "sample_count": 12},
        {"policy_version_id": policy_b, "metric_name": "scrambler.gained", "avg_value": 2.0, "sample_count": 12},
        {"policy_version_id": policy_a, "metric_name": "aligner.gained", "avg_value": 1.0, "sample_count": 12},
        {"policy_version_id": policy_b, "metric_name": "aligner.gained", "avg_value": 2.0, "sample_count": 12},
        {"policy_version_id": policy_a, "metric_name": "death", "avg_value": 0.0, "sample_count": 12},
        {"policy_version_id": policy_b, "metric_name": "death", "avg_value": 2.0, "sample_count": 12},
    ]


@pytest.mark.asyncio
async def test_compute_role_percentile_payloads_uses_single_metric_query(monkeypatch: pytest.MonkeyPatch) -> None:
    policy_a = uuid4()
    policy_b = uuid4()
    session = _FakeSession(_metric_rows(policy_a, policy_b))
    monkeypatch.setattr(queries, "get_db", lambda: session)
    monkeypatch.setattr(queries, "_role_percentile_payload_cache", TTLCache(maxsize=16, ttl=300))

    rows = await queries._compute_role_percentile_payloads(uuid4(), roles=("scout",))

    assert session.execute_count == 1
    matching = [row for row in rows if row["policy_version_id"] == policy_a and row["role"] == "scout"]
    assert len(matching) == 1
    assert matching[0]["details"]["metrics"]["scout.gained"]["avg"] == pytest.approx(10.0)


@pytest.mark.asyncio
async def test_compute_policy_role_percentiles_reuses_cached_pool_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    pool_id = uuid4()
    policy_a = uuid4()
    policy_b = uuid4()
    session = _FakeSession(_metric_rows(policy_a, policy_b))
    monkeypatch.setattr(queries, "get_db", lambda: session)
    monkeypatch.setattr(queries, "_role_percentile_payload_cache", TTLCache(maxsize=16, ttl=300))

    first = await queries.compute_policy_role_percentiles.__wrapped__(pool_id, policy_a)
    second = await queries.compute_policy_role_percentiles.__wrapped__(pool_id, policy_b)

    assert session.execute_count == 1
    assert "scout" in [row.role for row in first]
    assert "scout" in [row.role for row in second]
