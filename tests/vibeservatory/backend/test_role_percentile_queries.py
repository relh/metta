from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from cachetools import TTLCache

from metta.app_backend.config import DEFAULT_EPISODE_AGENT_METRIC_ALLOWLIST
from vibeservatory.backend.dashboard_backend.role_stats import queries as rpq


@pytest.mark.asyncio
async def test_metric_percentiles_uses_first_available_alias_source(monkeypatch: pytest.MonkeyPatch) -> None:
    policy_a = uuid4()
    policy_b = uuid4()
    source_metrics_by_policy = {
        policy_a: {
            "germanium.lost": {"avg": 6.0, "samples": 5},
            "germanium.deposited": {"avg": 2.0, "samples": 5},
        },
        policy_b: {
            "germanium.lost": {"avg": 1.0, "samples": 4},
        },
    }
    metric = rpq.RoleMetric(
        "germanium.deposited",
        ("germanium.deposited", "germanium.lost"),
        higher_is_better=True,
    )
    results = await rpq._metric_percentiles(metric, source_metrics_by_policy)
    by_policy = {row["policy_version_id"]: row for row in results}

    assert by_policy[policy_a]["avg_value"] == 2.0
    assert by_policy[policy_a]["sample_count"] == 5
    assert by_policy[policy_a]["source_metrics"] == {
        "germanium.lost": {"avg": 6.0, "samples": 5},
        "germanium.deposited": {"avg": 2.0, "samples": 5},
    }
    assert by_policy[policy_a]["percentile"] == pytest.approx(100.0)

    assert by_policy[policy_b]["avg_value"] == 1.0
    assert by_policy[policy_b]["sample_count"] == 4
    assert by_policy[policy_b]["source_metrics"] == {"germanium.lost": {"avg": 1.0, "samples": 4}}
    assert by_policy[policy_b]["percentile"] == pytest.approx(0.0)


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

    germanium_metric = next(metric for metric in rpq.ROLE_METRICS["miner"] if metric.key == "germanium.deposited")
    assert germanium_metric.source_names == ("germanium.deposited", "germanium.lost")
    assert germanium_metric.overall_weight == pytest.approx(5.0)

    death_metric = next(metric for metric in rpq.ROLE_METRICS["miner"] if metric.key == "death")
    assert death_metric.source_names == ("death",)

    # Priority metrics are listed first for visibility.
    assert rpq.ROLE_METRICS["aligner"][0].key == "junction.aligned"
    assert rpq.ROLE_METRICS["miner"][0].key == "germanium.deposited"
    assert rpq.ROLE_METRICS["scrambler"][0].key == "junction.scrambled"


@pytest.mark.asyncio
async def test_compute_role_percentile_payloads_uses_metric_weights(monkeypatch: pytest.MonkeyPatch) -> None:
    policy_id = uuid4()

    async def _fake_metric_percentiles(
        metric: rpq.RoleMetric,
        _source_metrics_by_policy: dict[UUID, dict[str, dict[str, float | int]]],
    ) -> list[dict[str, object]]:
        # Force one low priority metric percentile and high others to verify weighted averaging.
        percentile = 0.0 if metric.key == "junction.aligned" else 100.0
        return [
            {
                "policy_version_id": policy_id,
                "avg_value": 1.0,
                "sample_count": 10,
                "percentile": percentile,
                "source_metrics": {metric.source_names[0]: {"avg": 1.0, "samples": 10}},
            }
        ]

    async def _fake_pool_source_metrics_by_policy(
        _pool_id: UUID,
        _source_metric_names: tuple[str, ...],
    ) -> dict[UUID, dict[str, dict[str, float | int]]]:
        return {policy_id: {"junction.aligned_by_agent": {"avg": 1.0, "samples": 10}}}

    monkeypatch.setattr(rpq, "_pool_source_metrics_by_policy", _fake_pool_source_metrics_by_policy)
    monkeypatch.setattr(rpq, "_metric_percentiles", _fake_metric_percentiles)
    monkeypatch.setattr(rpq, "_role_percentile_payload_cache", TTLCache(maxsize=16, ttl=300))

    rows = await rpq._compute_role_percentile_payloads(uuid4(), roles=("aligner",))
    assert len(rows) == 1
    row = rows[0]
    assert row["role"] == "aligner"
    assert row["policy_version_id"] == policy_id

    # Aligner includes 7 overall metrics. With junction.aligned weighted x5:
    # weighted avg = (0*5 + 100*6) / (5 + 6) = 54.545...
    assert row["percentile"] == pytest.approx(54.5454545454)
    assert row["details"]["metrics"]["junction.aligned"]["overall_weight"] == pytest.approx(5.0)


def test_episode_agent_metric_allowlist_uses_canonical_death_metric() -> None:
    assert "death" in DEFAULT_EPISODE_AGENT_METRIC_ALLOWLIST
    assert "deaths" not in DEFAULT_EPISODE_AGENT_METRIC_ALLOWLIST
    assert "germanium.lost" in DEFAULT_EPISODE_AGENT_METRIC_ALLOWLIST
    assert "germanium.deposited" in DEFAULT_EPISODE_AGENT_METRIC_ALLOWLIST
