"""Tests for job cost metrics: counter emission, edge cases, EC2 pricing, and Datadog monitor."""

import time
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import pytest

import metta.app_backend.ec2_pricing as pricing_mod
from devops.datadog.monitors import (
    ALL_MONITORS,
    episode_length_spike_monitor,
    job_daily_cost_monitor,
)
from metta.app_backend.clients.stats_client import StatsClient
from metta.app_backend.ec2_pricing import get_instance_hourly_cost
from metta.app_backend.job_runner.event_processor import _build_result_metadata
from metta.app_backend.models.job_request import JobRequest, JobRequestCreate, JobRequestUpdate, JobStatus, JobType
from metta.app_backend.otel.job_metrics import JobMetrics, compute_job_cost, get_job_metrics
from mettagrid.runner.types import RuntimeInfo

# Known prices for mocking AWS API responses
_MOCK_ON_DEMAND = {"m5.xlarge": 0.192, "c5.xlarge": 0.17}


def _mock_on_demand_fetch(instance_type: str, region: str) -> float | None:
    return _MOCK_ON_DEMAND.get(instance_type)


def _make_job(
    *,
    job_type: JobType = JobType.episode,
    running_at: datetime | None = None,
    created_at: datetime | None = None,
    dispatched_at: datetime | None = None,
) -> JobRequest:
    return JobRequest(
        id=uuid4(),
        job_type=job_type,
        job={},
        status=JobStatus.running,
        user_id="test",
        created_at=created_at or datetime.now(UTC),
        dispatched_at=dispatched_at,
        running_at=running_at,
    )


def _make_metrics():
    """Create a JobMetrics instance with instrumented cost counter."""
    metrics = JobMetrics()
    recorded: list[dict] = []
    orig_add = metrics._cost_counter.add

    def capture_add(amount, attributes=None, context=None):
        recorded.append({"amount": amount, "attributes": attributes})
        orig_add(amount, attributes=attributes, context=context)

    metrics._cost_counter.add = capture_add  # type: ignore[assignment]
    return metrics, recorded


def _clear_pricing_caches():
    pricing_mod._on_demand_cache.clear()
    pricing_mod._spot_cache.clear()
    pricing_mod._ec2_clients.clear()


# ── Happy path ──────────────────────────────────────────────────────────


class TestCostEmission:
    def test_running_to_completed_emits_cost(self):
        """Pre-computed cost_usd should be emitted as-is."""
        metrics, recorded = _make_metrics()
        now = datetime.now(UTC)
        job = _make_job(running_at=now - timedelta(hours=1))

        metrics.record_transition(JobStatus.running, JobStatus.completed, job, now, error_type=None, cost_usd=0.20)

        assert len(recorded) == 1
        assert recorded[0]["amount"] == pytest.approx(0.20, abs=1e-9)
        assert recorded[0]["attributes"] == {"job_type": "episode", "outcome": "completed"}

    def test_running_to_failed_emits_cost(self):
        """Failed jobs still consumed compute; cost must be recorded."""
        metrics, recorded = _make_metrics()
        now = datetime.now(UTC)
        job = _make_job(running_at=now - timedelta(minutes=30))

        metrics.record_transition(JobStatus.running, JobStatus.failed, job, now, error_type="oom", cost_usd=0.10)

        assert len(recorded) == 1
        assert recorded[0]["amount"] == pytest.approx(0.10, abs=1e-9)
        assert recorded[0]["attributes"] == {"job_type": "episode", "outcome": "failed"}

    def test_cost_usd_passed_directly(self):
        """When cost_usd is provided, it should be used directly."""
        metrics, recorded = _make_metrics()
        now = datetime.now(UTC)
        job = _make_job(running_at=now - timedelta(hours=1))

        metrics.record_transition(
            JobStatus.running,
            JobStatus.completed,
            job,
            now,
            error_type=None,
            cost_usd=0.42,
        )

        assert len(recorded) == 1
        assert recorded[0]["amount"] == pytest.approx(0.42)

    def test_dispatched_to_failed_emits_cost_usd(self):
        """Pod failed during startup (never reached running). Pre-computed cost_usd should still emit."""
        metrics, recorded = _make_metrics()
        now = datetime.now(UTC)
        job = _make_job(dispatched_at=now - timedelta(minutes=30))

        metrics.record_transition(
            JobStatus.dispatched,
            JobStatus.failed,
            job,
            now,
            error_type="unknown",
            cost_usd=0.15,
        )

        assert len(recorded) == 1
        assert recorded[0]["amount"] == pytest.approx(0.15)
        assert recorded[0]["attributes"] == {"job_type": "episode", "outcome": "failed"}

    def test_dispatched_to_failed_no_cost_without_cost_usd(self):
        """dispatched→failed without pre-computed cost_usd should not emit."""
        metrics, recorded = _make_metrics()
        now = datetime.now(UTC)
        job = _make_job(dispatched_at=now - timedelta(minutes=30))

        metrics.record_transition(
            JobStatus.dispatched,
            JobStatus.failed,
            job,
            now,
            error_type="unknown",
        )

        assert len(recorded) == 0


# ── No-emit cases (false positive prevention) ──────────────────────────


class TestNoCostEmission:
    def test_pending_to_dispatched_no_cost(self):
        """Non-running transitions must never emit cost."""
        metrics, recorded = _make_metrics()
        job = _make_job(created_at=datetime.now(UTC) - timedelta(seconds=5))

        metrics.record_transition(JobStatus.pending, JobStatus.dispatched, job, datetime.now(UTC), error_type=None)

        assert len(recorded) == 0

    def test_dispatched_to_running_no_cost(self):
        metrics, recorded = _make_metrics()
        job = _make_job(dispatched_at=datetime.now(UTC) - timedelta(seconds=5))

        metrics.record_transition(JobStatus.dispatched, JobStatus.running, job, datetime.now(UTC), error_type=None)

        assert len(recorded) == 0

    def test_dispatched_to_completed_no_cost(self):
        """Reconciliation path: dispatched -> completed (skipped running). No cost_usd, no cost."""
        metrics, recorded = _make_metrics()
        job = _make_job(dispatched_at=datetime.now(UTC) - timedelta(seconds=30))

        metrics.record_transition(
            JobStatus.dispatched,
            JobStatus.completed,
            job,
            datetime.now(UTC),
            error_type=None,
        )

        assert len(recorded) == 0

    def test_dispatched_to_failed_no_cost(self):
        metrics, recorded = _make_metrics()
        job = _make_job(dispatched_at=datetime.now(UTC) - timedelta(seconds=5))

        metrics.record_transition(JobStatus.dispatched, JobStatus.failed, job, datetime.now(UTC), error_type="unknown")

        assert len(recorded) == 0

    def test_no_cost_usd_no_emit(self):
        """Without cost_usd, running→completed must not emit cost."""
        metrics, recorded = _make_metrics()
        now = datetime.now(UTC)
        job = _make_job(running_at=now - timedelta(hours=1))

        metrics.record_transition(JobStatus.running, JobStatus.completed, job, now, error_type=None)

        assert len(recorded) == 0

    def test_zero_cost_usd_no_emit(self):
        """cost_usd=0 should not emit (no billable compute)."""
        metrics, recorded = _make_metrics()
        now = datetime.now(UTC)
        job = _make_job(running_at=now - timedelta(hours=1))

        metrics.record_transition(JobStatus.running, JobStatus.completed, job, now, error_type=None, cost_usd=0.0)

        assert len(recorded) == 0


# ── EC2 pricing lookup ─────────────────────────────────────────────────


class TestEC2Pricing:
    @patch("metta.app_backend.ec2_pricing._fetch_on_demand_price", side_effect=_mock_on_demand_fetch)
    def test_on_demand_known_instance(self, _mock):
        _clear_pricing_caches()
        assert get_instance_hourly_cost("m5.xlarge", capacity_type="on-demand") == 0.192

    @patch("metta.app_backend.ec2_pricing._fetch_on_demand_price", side_effect=_mock_on_demand_fetch)
    def test_on_demand_none_capacity_type(self, _mock):
        """None capacity_type defaults to on-demand."""
        _clear_pricing_caches()
        assert get_instance_hourly_cost("m5.xlarge", capacity_type=None) == 0.192

    @patch("metta.app_backend.ec2_pricing._fetch_on_demand_price", return_value=None)
    def test_unknown_instance_type_returns_zero(self, _mock):
        _clear_pricing_caches()
        assert get_instance_hourly_cost("p4d.24xlarge", capacity_type="on-demand") == 0.0

    def test_none_instance_type_returns_zero(self):
        assert get_instance_hourly_cost(None, capacity_type="on-demand") == 0.0

    @patch("metta.app_backend.ec2_pricing._fetch_spot_price", return_value=0.065)
    def test_spot_lookup(self, mock_fetch):
        _clear_pricing_caches()
        result = get_instance_hourly_cost("m5.xlarge", capacity_type="spot")
        assert result == 0.065
        mock_fetch.assert_called_once_with("m5.xlarge", "us-east-1")

    @patch("metta.app_backend.ec2_pricing._fetch_on_demand_price", side_effect=_mock_on_demand_fetch)
    @patch("metta.app_backend.ec2_pricing._fetch_spot_price", side_effect=Exception("API error"))
    def test_spot_api_failure_falls_back_to_on_demand(self, _mock_spot, _mock_od):
        """When spot API fails, fall back to on-demand price."""
        _clear_pricing_caches()
        result = get_instance_hourly_cost("m5.xlarge", capacity_type="spot")
        assert result == 0.192  # on-demand price for m5.xlarge

    @patch("metta.app_backend.ec2_pricing._fetch_spot_price")
    def test_spot_cache_hit(self, mock_fetch):
        """Second call within TTL should not call the API again."""
        _clear_pricing_caches()
        mock_fetch.return_value = 0.07

        get_instance_hourly_cost("c5.xlarge", capacity_type="spot")
        get_instance_hourly_cost("c5.xlarge", capacity_type="spot")
        mock_fetch.assert_called_once()

    @patch("metta.app_backend.ec2_pricing._fetch_on_demand_price", side_effect=_mock_on_demand_fetch)
    def test_on_demand_cache_hit(self, mock_fetch):
        """Second on-demand call within TTL should not call the API again."""
        _clear_pricing_caches()

        get_instance_hourly_cost("m5.xlarge", capacity_type="on-demand")
        get_instance_hourly_cost("m5.xlarge", capacity_type="on-demand")
        mock_fetch.assert_called_once()

    @patch("metta.app_backend.ec2_pricing._fetch_on_demand_price", side_effect=Exception("API error"))
    def test_on_demand_api_failure_returns_zero(self, _mock):
        """When on-demand API fails, return 0.0."""
        _clear_pricing_caches()
        assert get_instance_hourly_cost("m5.xlarge", capacity_type="on-demand") == 0.0

    @patch("metta.app_backend.ec2_pricing._fetch_on_demand_price", return_value=None)
    @patch("metta.app_backend.ec2_pricing._fetch_spot_price", return_value=None)
    def test_all_apis_fail_returns_zero(self, _mock_spot, _mock_od):
        """When both APIs return nothing, return 0.0."""
        _clear_pricing_caches()
        assert get_instance_hourly_cost("z99.mega", capacity_type="spot") == 0.0

    def test_on_demand_stale_cache_on_api_failure(self):
        """When cache expires and API fails, serve the stale cached price."""
        _clear_pricing_caches()
        # Seed cache with a known price, then expire it
        pricing_mod._on_demand_cache[("m5.xlarge", "us-east-1")] = (0.192, time.monotonic() - 90000)

        with patch("metta.app_backend.ec2_pricing._fetch_on_demand_price", side_effect=Exception("API down")):
            result = get_instance_hourly_cost("m5.xlarge", capacity_type="on-demand")
        assert result == 0.192  # stale price, not 0.0

    def test_spot_stale_cache_on_api_failure(self):
        """When spot cache expires and API fails, serve the stale cached price."""
        _clear_pricing_caches()
        # Seed cache with a known price, then expire it
        pricing_mod._spot_cache[("m5.xlarge", "us-east-1")] = (0.065, time.monotonic() - 7200)

        with patch("metta.app_backend.ec2_pricing._fetch_spot_price", side_effect=Exception("API down")):
            result = get_instance_hourly_cost("m5.xlarge", capacity_type="spot")
        assert result == 0.065  # stale price, not fallback to on-demand


# ── Datadog monitor ────────────────────────────────────────────────────


class TestDatadogMonitor:
    def test_monitor_in_all_monitors(self):
        assert job_daily_cost_monitor in ALL_MONITORS

    def test_monitor_structure(self):
        m = job_daily_cost_monitor()
        assert m["type"] == "query alert"
        assert m["thresholds"]["critical"] == 10000
        assert m["thresholds"]["warning"] == 8000
        assert m["options"]["renotify_interval"] == 60
        assert "job.cost" in m["query"]
        assert "service:observatory-backend" in m["query"]
        assert ".as_count()" in m["query"]
        assert "> 10000" in m["query"]
        assert "last_1d" in m["query"]

    def test_monitor_query_uses_sum_aggregation(self):
        """Must use sum:sum: for a counter to get daily total, not avg or max."""
        q = job_daily_cost_monitor()["query"]
        assert q.startswith("sum(last_1d):sum:job.cost")

    def test_monitor_has_discord_webhook(self):
        m = job_daily_cost_monitor()
        assert "@webhook-Discord" in m["message"]

    def test_episode_length_spike_monitor_pages_oncall(self):
        m = episode_length_spike_monitor()
        assert "@webhook-Discord" in m["message"]
        assert "@oncall-on-call" in m["message"]


# ── Episode-length histogram ──────────────────────────────────────────


def _make_episode_metrics():
    """Create a JobMetrics instance with instrumented episode-length histogram."""
    metrics = JobMetrics()
    recorded: list[dict] = []
    orig_record = metrics._episode_length_histogram.record

    def capture_record(amount, attributes=None, context=None):
        recorded.append({"amount": amount, "attributes": attributes})
        orig_record(amount, attributes=attributes, context=context)

    metrics._episode_length_histogram.record = capture_record  # type: ignore[assignment]
    return metrics, recorded


class TestEpisodeLengthEmission:
    def test_record_episode_length_emits_histogram(self):
        """A single call should record exactly one data point with correct value and attributes."""
        metrics, recorded = _make_episode_metrics()
        metrics.record_episode_length(500, job_type="episode")

        assert len(recorded) == 1
        assert recorded[0]["amount"] == 500
        assert recorded[0]["attributes"] == {"job_type": "episode"}

    def test_multiple_episodes_accumulate(self):
        """Multiple calls should each produce a separate data point."""
        metrics, recorded = _make_episode_metrics()
        for steps in [100, 200, 300]:
            metrics.record_episode_length(steps, job_type="episode")

        assert len(recorded) == 3
        assert [r["amount"] for r in recorded] == [100, 200, 300]

    def test_zero_steps(self):
        """Zero-step episodes should still be recorded (degenerate but valid)."""
        metrics, recorded = _make_episode_metrics()
        metrics.record_episode_length(0, job_type="episode")

        assert len(recorded) == 1
        assert recorded[0]["amount"] == 0


# ── Integration: multiple jobs accumulate cost ──────────────────────────


class TestCostAccumulation:
    def test_multiple_jobs_accumulate(self):
        """Simulating several jobs finishing: total recorded cost should match sum."""
        metrics, recorded = _make_metrics()
        now = datetime.now(UTC)

        costs = [0.10, 0.20, 0.40]
        for cost in costs:
            job = _make_job(running_at=now - timedelta(hours=1))
            metrics.record_transition(JobStatus.running, JobStatus.completed, job, now, error_type=None, cost_usd=cost)

        assert len(recorded) == 3
        total = sum(r["amount"] for r in recorded)
        assert total == pytest.approx(0.70, abs=1e-9)

    def test_mixed_completed_and_failed(self):
        """Both completed and failed jobs should contribute cost."""
        metrics, recorded = _make_metrics()
        now = datetime.now(UTC)

        job1 = _make_job(running_at=now - timedelta(hours=1))
        metrics.record_transition(JobStatus.running, JobStatus.completed, job1, now, error_type=None, cost_usd=0.20)

        job2 = _make_job(running_at=now - timedelta(hours=2))
        metrics.record_transition(JobStatus.running, JobStatus.failed, job2, now, error_type="timeout", cost_usd=0.40)

        assert len(recorded) == 2
        total = sum(r["amount"] for r in recorded)
        assert total == pytest.approx(0.60, abs=1e-9)


# ── Route integration: verify cost_usd is passed via real HTTP ─────────


def _patch_pricing(monkeypatch: pytest.MonkeyPatch):
    """Mock AWS pricing APIs and clear caches for route integration tests."""
    _clear_pricing_caches()
    monkeypatch.setattr(pricing_mod, "_fetch_on_demand_price", _mock_on_demand_fetch)
    monkeypatch.setattr(pricing_mod, "_fetch_spot_price", lambda it, r: _MOCK_ON_DEMAND.get(it, 0.0) * 0.3)


class TestRouteIntegration:
    """End-to-end tests through the actual HTTP route with a real DB.

    These use the stats_client fixture (requires Docker/Postgres). They verify
    that the route code passes cost_usd from result to record_transition.
    """

    def test_stored_cost_usd_passed_to_record_transition(self, stats_client, monkeypatch: pytest.MonkeyPatch):
        """When cost_usd is in result, record_transition should receive it directly."""
        _patch_pricing(monkeypatch)

        metrics_instance = get_job_metrics()
        captured: list[dict] = []
        orig = metrics_instance.record_transition

        def spy(*args, **kwargs):
            captured.append({"args": args, "kwargs": kwargs})
            return orig(*args, **kwargs)

        monkeypatch.setattr(metrics_instance, "record_transition", spy)

        client: StatsClient = stats_client
        job_ids = client.create_jobs(
            [JobRequestCreate(job_type=JobType.episode, job={"assignments": [0], "env": {}, "seed": 1})]
        )
        client.update_job(job_ids[0], JobRequestUpdate(status=JobStatus.running, worker="w"))
        # Event processor sends result with pre-computed cost_usd
        client.update_job(
            job_ids[0],
            JobRequestUpdate(
                result={"instance_type": "m5.xlarge", "capacity_type": "on-demand", "cost_usd": 0.096},
            ),
        )
        captured.clear()

        client.update_job(job_ids[0], JobRequestUpdate(status=JobStatus.completed))
        assert len(captured) == 1
        assert captured[0]["kwargs"]["cost_usd"] == pytest.approx(0.096)

    def test_no_cost_usd_in_result_passes_none(self, stats_client, monkeypatch: pytest.MonkeyPatch):
        """When result has no cost_usd, record_transition receives cost_usd=None."""
        _patch_pricing(monkeypatch)

        metrics_instance = get_job_metrics()
        captured: list[dict] = []
        orig = metrics_instance.record_transition

        def spy(*args, **kwargs):
            captured.append({"args": args, "kwargs": kwargs})
            return orig(*args, **kwargs)

        monkeypatch.setattr(metrics_instance, "record_transition", spy)

        client: StatsClient = stats_client
        job_ids = client.create_jobs(
            [JobRequestCreate(job_type=JobType.episode, job={"assignments": [0], "env": {}, "seed": 1})]
        )
        client.update_job(job_ids[0], JobRequestUpdate(status=JobStatus.running, worker="w"))
        client.update_job(
            job_ids[0],
            JobRequestUpdate(result={"instance_type": "m5.xlarge", "capacity_type": "on-demand"}),
        )
        captured.clear()

        client.update_job(job_ids[0], JobRequestUpdate(status=JobStatus.completed))
        assert len(captured) == 1
        assert captured[0]["kwargs"]["cost_usd"] is None

    def test_bool_cost_usd_rejected(self, stats_client, monkeypatch: pytest.MonkeyPatch):
        """Boolean cost_usd in result (True/False) should be rejected as non-numeric."""
        _patch_pricing(monkeypatch)

        metrics_instance = get_job_metrics()
        captured: list[dict] = []
        orig = metrics_instance.record_transition

        def spy(*args, **kwargs):
            captured.append({"args": args, "kwargs": kwargs})
            return orig(*args, **kwargs)

        monkeypatch.setattr(metrics_instance, "record_transition", spy)

        client: StatsClient = stats_client
        job_ids = client.create_jobs(
            [JobRequestCreate(job_type=JobType.episode, job={"assignments": [0], "env": {}, "seed": 1})]
        )
        client.update_job(job_ids[0], JobRequestUpdate(status=JobStatus.running, worker="w"))
        client.update_job(
            job_ids[0],
            JobRequestUpdate(result={"cost_usd": True}),
        )
        captured.clear()

        client.update_job(job_ids[0], JobRequestUpdate(status=JobStatus.completed))
        assert len(captured) == 1
        assert captured[0]["kwargs"]["cost_usd"] is None

    def test_batch_create_does_not_emit_cost(self, stats_client, monkeypatch: pytest.MonkeyPatch):
        """Batch create transitions pending→dispatched. Cost counter must not fire."""
        _patch_pricing(monkeypatch)

        metrics_instance = get_job_metrics()
        cost_adds: list[float] = []
        orig_add = metrics_instance._cost_counter.add

        def spy_add(amount, attributes=None, context=None):
            cost_adds.append(amount)
            return orig_add(amount, attributes=attributes, context=context)

        monkeypatch.setattr(metrics_instance._cost_counter, "add", spy_add)

        stats_client.create_jobs(
            [
                JobRequestCreate(job_type=JobType.episode, job={"assignments": [0], "env": {}, "seed": 1}),
            ]
        )

        assert len(cost_adds) == 0

    def test_full_lifecycle_emits_cost_only_once(self, stats_client, monkeypatch: pytest.MonkeyPatch):
        """Through create→dispatch→running→completed, cost counter fires exactly once."""
        _patch_pricing(monkeypatch)

        metrics_instance = get_job_metrics()
        cost_adds: list[dict] = []
        orig_add = metrics_instance._cost_counter.add

        def spy_add(amount, attributes=None, context=None):
            cost_adds.append({"amount": amount, "attributes": attributes})
            return orig_add(amount, attributes=attributes, context=context)

        monkeypatch.setattr(metrics_instance._cost_counter, "add", spy_add)

        job_ids = stats_client.create_jobs(
            [
                JobRequestCreate(job_type=JobType.episode, job={"assignments": [0], "env": {}, "seed": 1}),
            ]
        )
        assert len(cost_adds) == 0  # pending→dispatched: no cost

        stats_client.update_job(job_ids[0], JobRequestUpdate(status=JobStatus.running, worker="w"))
        assert len(cost_adds) == 0  # dispatched→running: no cost

        # Set result with cost_usd before completing
        stats_client.update_job(
            job_ids[0],
            JobRequestUpdate(result={"instance_type": "m5.xlarge", "capacity_type": "on-demand", "cost_usd": 0.192}),
        )

        stats_client.update_job(job_ids[0], JobRequestUpdate(status=JobStatus.completed))
        assert len(cost_adds) == 1  # running→completed: cost emitted exactly once
        assert cost_adds[0]["amount"] == pytest.approx(0.192)
        assert cost_adds[0]["attributes"] == {"job_type": "episode", "outcome": "completed"}

    def test_failed_from_running_emits_cost(self, stats_client, monkeypatch: pytest.MonkeyPatch):
        """running→failed must also emit cost (compute was consumed)."""
        _patch_pricing(monkeypatch)

        metrics_instance = get_job_metrics()
        cost_adds: list[dict] = []
        orig_add = metrics_instance._cost_counter.add

        def spy_add(amount, attributes=None, context=None):
            cost_adds.append({"amount": amount, "attributes": attributes})
            return orig_add(amount, attributes=attributes, context=context)

        monkeypatch.setattr(metrics_instance._cost_counter, "add", spy_add)

        job_ids = stats_client.create_jobs(
            [
                JobRequestCreate(job_type=JobType.episode, job={"assignments": [0], "env": {}, "seed": 1}),
            ]
        )
        stats_client.update_job(job_ids[0], JobRequestUpdate(status=JobStatus.running, worker="w"))
        assert len(cost_adds) == 0

        # Set result with cost_usd, then fail
        stats_client.update_job(
            job_ids[0],
            JobRequestUpdate(
                result={"instance_type": "m5.xlarge", "capacity_type": "on-demand", "cost_usd": 0.096},
            ),
        )

        stats_client.update_job(job_ids[0], JobRequestUpdate(status=JobStatus.failed, error="boom", error_type="oom"))
        assert len(cost_adds) == 1
        assert cost_adds[0]["amount"] == pytest.approx(0.096)


class TestComputeJobCost:
    """Unit tests for the shared compute_job_cost helper."""

    def test_returns_cost_for_valid_inputs(self):
        start = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
        end = datetime(2026, 1, 1, 11, 0, 0, tzinfo=UTC)  # 1 hour later
        cost = compute_job_cost(start, end, 0.192)
        assert cost == pytest.approx(0.192)

    def test_returns_none_for_zero_rate(self):
        start = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
        end = datetime(2026, 1, 1, 11, 0, 0, tzinfo=UTC)
        assert compute_job_cost(start, end, 0.0) is None

    def test_returns_none_for_none_start(self):
        end = datetime(2026, 1, 1, 11, 0, 0, tzinfo=UTC)
        assert compute_job_cost(None, end, 0.192) is None

    def test_returns_none_for_negative_duration(self):
        start = datetime(2026, 1, 1, 11, 0, 0, tzinfo=UTC)
        end = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)  # before start
        assert compute_job_cost(start, end, 0.192) is None

    def test_handles_naive_datetimes(self):
        start = datetime(2026, 1, 1, 10, 0, 0)  # naive
        end = datetime(2026, 1, 1, 10, 30, 0)  # naive, 30 min later
        cost = compute_job_cost(start, end, 0.192)
        assert cost == pytest.approx(0.096)


class TestCostInResultData:
    """Verify cost_usd supplied in result_data is persisted through the route."""

    def test_cost_usd_in_result_is_preserved(self, stats_client, monkeypatch: pytest.MonkeyPatch):
        """cost_usd sent by event processor in result is stored in job.result."""
        _patch_pricing(monkeypatch)
        client: StatsClient = stats_client
        job_ids = client.create_jobs(
            [JobRequestCreate(job_type=JobType.episode, job={"assignments": [0], "env": {}, "seed": 1})]
        )
        client.update_job(job_ids[0], JobRequestUpdate(status=JobStatus.running, worker="w"))
        # Simulate event processor sending result with cost_usd already computed
        job = client.update_job(
            job_ids[0],
            JobRequestUpdate(
                result={"instance_type": "m5.xlarge", "capacity_type": "on-demand", "cost_usd": 0.096},
            ),
        )
        assert job.result is not None
        assert job.result["cost_usd"] == pytest.approx(0.096)
        assert job.result["instance_type"] == "m5.xlarge"

    def test_cost_usd_survives_status_update(self, stats_client, monkeypatch: pytest.MonkeyPatch):
        """cost_usd in result is not lost when a subsequent status-only update is applied."""
        _patch_pricing(monkeypatch)
        client: StatsClient = stats_client
        job_ids = client.create_jobs(
            [JobRequestCreate(job_type=JobType.episode, job={"assignments": [0], "env": {}, "seed": 1})]
        )
        client.update_job(job_ids[0], JobRequestUpdate(status=JobStatus.running, worker="w"))
        # Event processor sends result with cost_usd
        client.update_job(
            job_ids[0],
            JobRequestUpdate(
                result={"instance_type": "m5.xlarge", "capacity_type": "on-demand", "cost_usd": 0.096},
            ),
        )
        # Then sends status=completed (no result in this call)
        job = client.update_job(job_ids[0], JobRequestUpdate(status=JobStatus.completed))
        assert job.result is not None
        assert job.result["cost_usd"] == pytest.approx(0.096)


def _mock_k8s_node_event(*, with_node: bool = True) -> tuple[dict, Any]:
    """Create mock event_data and CoreV1Api for _build_result_metadata tests."""
    event_data = {
        "object": {
            "spec": {"nodeName": "test-node"} if with_node else {},
            "status": {"containerStatuses": [{"image": "runner:v1", "imageID": "sha256:abc"}] if with_node else []},
            "metadata": {"labels": {}},
        }
    }
    if not with_node:
        return event_data, type("CoreV1Api", (), {})()
    mock_node = type(
        "Node",
        (),
        {
            "metadata": type(
                "Meta",
                (),
                {
                    "labels": {
                        "node.kubernetes.io/instance-type": "m5.xlarge",
                        "karpenter.sh/capacity-type": "on-demand",
                    }
                },
            )(),
        },
    )()
    mock_core_v1 = type("CoreV1Api", (), {"read_node": lambda self, name: mock_node})()
    return event_data, mock_core_v1


class TestBuildResultMetadata:
    """Test _build_result_metadata with mocked K8s and pricing APIs."""

    def test_computes_cost_from_node_pricing(self):
        """_build_result_metadata should compute cost_usd from node labels + pricing API."""
        dispatched = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
        running = datetime(2026, 1, 1, 10, 5, 0, tzinfo=UTC)  # 5 min startup
        fixed_now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)  # 2 hours after dispatch
        event_data, mock_core_v1 = _mock_k8s_node_event()

        with (
            patch("metta.app_backend.job_runner.event_processor._read_runtime_info", return_value=RuntimeInfo()),
            patch("metta.app_backend.ec2_pricing._fetch_on_demand_price", side_effect=_mock_on_demand_fetch),
            patch("metta.app_backend.job_runner.event_processor.datetime") as mock_dt,
        ):
            mock_dt.now.return_value = fixed_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            _clear_pricing_caches()
            result = _build_result_metadata(
                event_data, mock_core_v1, uuid4(), dispatched_at=dispatched, running_at=running
            )

        assert result["instance_type"] == "m5.xlarge"
        assert result["capacity_type"] == "on-demand"
        assert result["runner_image"] == "runner:v1"
        # 2 hours from dispatched_at at $0.192/hr = $0.384
        assert result["cost_usd"] == pytest.approx(0.384, abs=0.001)

    def test_no_cost_without_node_info(self):
        """When pod has no node (e.g., still pending), cost_usd should be absent."""
        event_data, mock_core_v1 = _mock_k8s_node_event(with_node=False)

        with patch("metta.app_backend.job_runner.event_processor._read_runtime_info", return_value=RuntimeInfo()):
            result = _build_result_metadata(event_data, mock_core_v1, uuid4(), running_at=datetime.now(UTC))

        assert "cost_usd" not in result

    def test_uses_dispatched_at_over_running_at(self):
        """Cost should use dispatched_at (earlier) to include pod startup time."""
        dispatched = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
        running = datetime(2026, 1, 1, 10, 10, 0, tzinfo=UTC)  # 10 min startup
        fixed_now = datetime(2026, 1, 1, 11, 0, 0, tzinfo=UTC)  # 1 hour after dispatch
        event_data, mock_core_v1 = _mock_k8s_node_event()

        with (
            patch("metta.app_backend.job_runner.event_processor._read_runtime_info", return_value=RuntimeInfo()),
            patch("metta.app_backend.ec2_pricing._fetch_on_demand_price", side_effect=_mock_on_demand_fetch),
            patch("metta.app_backend.job_runner.event_processor.datetime") as mock_dt,
        ):
            mock_dt.now.return_value = fixed_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            _clear_pricing_caches()
            result = _build_result_metadata(
                event_data, mock_core_v1, uuid4(), dispatched_at=dispatched, running_at=running
            )

        # 1 hour at $0.192/hr = $0.192 (uses dispatched_at, not running_at)
        assert result["cost_usd"] == pytest.approx(0.192, abs=0.001)
