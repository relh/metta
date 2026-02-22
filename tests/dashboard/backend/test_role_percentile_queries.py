from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import literal, select

from metta.app_backend.config import DEFAULT_EPISODE_AGENT_METRIC_ALLOWLIST
from metta.app_backend.queries import role_percentile_queries as rpq


class _FakeExecuteResult:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    def mappings(self) -> "_FakeExecuteResult":
        return self

    def all(self) -> list[dict[str, object]]:
        return self._rows


class _FakeSession:
    def __init__(self, rows: list[dict[str, object]], policy_ids: list[object]) -> None:
        self._rows = rows
        self._policy_ids = policy_ids

    async def execute(self, _query: object) -> _FakeExecuteResult:
        return _FakeExecuteResult(self._rows)

    async def scalars(self, _query: object) -> list[object]:
        return self._policy_ids


@pytest.mark.asyncio
async def test_metric_percentiles_uses_canonical_metric(monkeypatch: pytest.MonkeyPatch) -> None:
    policy_a = uuid4()
    policy_b = uuid4()
    rows = [
        {
            "policy_version_id": policy_a,
            "metric_name": "death",
            "avg_value": 2.0,
            "sample_count": 10,
        },
        {"policy_version_id": policy_b, "avg_value": 4.0, "sample_count": 7},
    ]
    session = _FakeSession(rows=rows, policy_ids=[policy_a, policy_b])

    monkeypatch.setattr(rpq, "get_db", lambda: session)
    monkeypatch.setattr(
        rpq,
        "_pool_episode_internal_ids",
        lambda _pool_id: select(literal(1).label("episode_internal_id")).subquery("pool_episodes"),
    )
    metric = rpq.RoleMetric("death", ("death",), higher_is_better=False)
    results = await rpq._metric_percentiles(uuid4(), metric)
    by_policy = {row["policy_version_id"]: row for row in results}

    assert by_policy[policy_a]["avg_value"] == 2.0
    assert by_policy[policy_a]["sample_count"] == 10
    assert by_policy[policy_a]["source_metrics"] == {"death": {"avg": 2.0, "samples": 10}}

    assert by_policy[policy_b]["avg_value"] == 4.0
    assert by_policy[policy_b]["sample_count"] == 7
    assert by_policy[policy_b]["source_metrics"] == {"death": {"avg": 4.0, "samples": 7}}


def test_role_metric_catalog_keeps_miner_deposits_and_death_metric() -> None:
    miner_keys = [metric.key for metric in rpq.ROLE_METRICS["miner"]]
    for key in [
        "miner.gained",
        "germanium.deposited",
        "silicon.deposited",
        "carbon.deposited",
        "oxygen.deposited",
        "death",
    ]:
        assert key in miner_keys

    death_metric = next(metric for metric in rpq.ROLE_METRICS["miner"] if metric.key == "death")
    assert death_metric.source_names == ("death",)


def test_episode_agent_metric_allowlist_uses_canonical_death_metric() -> None:
    assert "death" in DEFAULT_EPISODE_AGENT_METRIC_ALLOWLIST
    assert "deaths" not in DEFAULT_EPISODE_AGENT_METRIC_ALLOWLIST
