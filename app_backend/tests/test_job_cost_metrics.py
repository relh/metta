"""Tests for job cost metrics: counter emission, edge cases, EC2 pricing, and Datadog monitor."""

import time
from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4

import pytest

import metta.app_backend.ec2_pricing as pricing_mod
from devops.datadog.monitors import ALL_MONITORS, job_daily_cost_monitor
from metta.app_backend.clients.stats_client import StatsClient
from metta.app_backend.ec2_pricing import get_instance_hourly_cost
from metta.app_backend.models.job_request import JobRequest, JobRequestCreate, JobRequestUpdate, JobStatus, JobType
from metta.app_backend.otel.job_metrics import JobMetrics, get_job_metrics

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
        """A 1-hour job at $0.20/hr should emit exactly $0.20."""
        metrics, recorded = _make_metrics()
        now = datetime.now(UTC)
        job = _make_job(running_at=now - timedelta(hours=1))

        metrics.record_transition(
            JobStatus.running, JobStatus.completed, job, now, error_type=None, cost_per_pod_hour=0.20
        )

        assert len(recorded) == 1
        assert recorded[0]["amount"] == pytest.approx(0.20, abs=1e-9)
        assert recorded[0]["attributes"] == {"job_type": "episode"}

    def test_running_to_failed_emits_cost(self):
        """Failed jobs still consumed compute; cost must be recorded."""
        metrics, recorded = _make_metrics()
        now = datetime.now(UTC)
        job = _make_job(running_at=now - timedelta(minutes=30))

        metrics.record_transition(
            JobStatus.running, JobStatus.failed, job, now, error_type="oom", cost_per_pod_hour=0.20
        )

        assert len(recorded) == 1
        assert recorded[0]["amount"] == pytest.approx(0.10, abs=1e-9)

    def test_fractional_duration(self):
        """90 seconds at $1.00/hr = $0.025."""
        metrics, recorded = _make_metrics()
        now = datetime.now(UTC)
        job = _make_job(running_at=now - timedelta(seconds=90))

        metrics.record_transition(
            JobStatus.running, JobStatus.completed, job, now, error_type=None, cost_per_pod_hour=1.00
        )

        assert len(recorded) == 1
        assert recorded[0]["amount"] == pytest.approx(90 / 3600, abs=1e-9)

    def test_long_running_job(self):
        """24-hour job at $0.20/hr = $4.80."""
        metrics, recorded = _make_metrics()
        now = datetime.now(UTC)
        job = _make_job(running_at=now - timedelta(hours=24))

        metrics.record_transition(
            JobStatus.running, JobStatus.completed, job, now, error_type=None, cost_per_pod_hour=0.20
        )

        assert len(recorded) == 1
        assert recorded[0]["amount"] == pytest.approx(4.80, abs=1e-9)


# ── No-emit cases (false positive prevention) ──────────────────────────


class TestNoCostEmission:
    def test_pending_to_dispatched_no_cost(self):
        """Non-running transitions must never emit cost."""
        metrics, recorded = _make_metrics()
        job = _make_job(created_at=datetime.now(UTC) - timedelta(seconds=5))

        metrics.record_transition(
            JobStatus.pending, JobStatus.dispatched, job, datetime.now(UTC), error_type=None, cost_per_pod_hour=0.20
        )

        assert len(recorded) == 0

    def test_dispatched_to_running_no_cost(self):
        metrics, recorded = _make_metrics()
        job = _make_job(dispatched_at=datetime.now(UTC) - timedelta(seconds=5))

        metrics.record_transition(
            JobStatus.dispatched, JobStatus.running, job, datetime.now(UTC), error_type=None, cost_per_pod_hour=0.20
        )

        assert len(recorded) == 0

    def test_dispatched_to_completed_no_cost(self):
        """Reconciliation path: dispatched -> completed (skipped running). No running_at, no cost."""
        metrics, recorded = _make_metrics()
        job = _make_job(dispatched_at=datetime.now(UTC) - timedelta(seconds=30))

        metrics.record_transition(
            JobStatus.dispatched,
            JobStatus.completed,
            job,
            datetime.now(UTC),
            error_type=None,
            cost_per_pod_hour=0.20,
        )

        assert len(recorded) == 0

    def test_dispatched_to_failed_no_cost(self):
        metrics, recorded = _make_metrics()
        job = _make_job(dispatched_at=datetime.now(UTC) - timedelta(seconds=5))

        metrics.record_transition(
            JobStatus.dispatched, JobStatus.failed, job, datetime.now(UTC), error_type="unknown", cost_per_pod_hour=0.20
        )

        assert len(recorded) == 0

    def test_zero_cost_rate_no_emit(self):
        """Default cost_per_pod_hour=0 must not emit."""
        metrics, recorded = _make_metrics()
        now = datetime.now(UTC)
        job = _make_job(running_at=now - timedelta(hours=1))

        metrics.record_transition(JobStatus.running, JobStatus.completed, job, now, error_type=None)

        assert len(recorded) == 0

    def test_running_at_none_no_emit(self):
        """If running_at was never set (shouldn't happen, but guard), no cost."""
        metrics, recorded = _make_metrics()
        job = _make_job(running_at=None)

        metrics.record_transition(
            JobStatus.running,
            JobStatus.completed,
            job,
            datetime.now(UTC),
            error_type=None,
            cost_per_pod_hour=0.20,
        )

        assert len(recorded) == 0

    def test_negative_duration_no_emit(self):
        """If transition_time < running_at (clock skew), must not emit negative cost."""
        metrics, recorded = _make_metrics()
        now = datetime.now(UTC)
        job = _make_job(running_at=now + timedelta(hours=1))  # running_at in the future

        metrics.record_transition(
            JobStatus.running, JobStatus.completed, job, now, error_type=None, cost_per_pod_hour=0.20
        )

        assert len(recorded) == 0


# ── Timezone handling ───────────────────────────────────────────────────


class TestTimezoneHandling:
    def test_naive_datetimes(self):
        """Naive datetimes (no tzinfo) must be treated as UTC and produce correct cost."""
        metrics, recorded = _make_metrics()
        naive_now = datetime(2025, 6, 15, 12, 0, 0)
        job = _make_job(running_at=datetime(2025, 6, 15, 11, 0, 0))  # 1 hour earlier, naive

        metrics.record_transition(
            JobStatus.running,
            JobStatus.completed,
            job,
            naive_now,
            error_type=None,
            cost_per_pod_hour=0.50,
        )

        assert len(recorded) == 1
        assert recorded[0]["amount"] == pytest.approx(0.50, abs=1e-9)

    def test_mixed_aware_and_naive(self):
        """One aware, one naive -- should still work (both treated as UTC)."""
        metrics, recorded = _make_metrics()
        aware_running = datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC)
        naive_transition = datetime(2025, 6, 15, 12, 0, 0)  # 2 hours later, naive
        job = _make_job(running_at=aware_running)

        metrics.record_transition(
            JobStatus.running,
            JobStatus.completed,
            job,
            naive_transition,
            error_type=None,
            cost_per_pod_hour=0.20,
        )

        assert len(recorded) == 1
        assert recorded[0]["amount"] == pytest.approx(0.40, abs=1e-9)

    def test_non_utc_timezone(self):
        """Aware datetimes in non-UTC zone should still produce correct duration."""
        metrics, recorded = _make_metrics()
        est = timezone(timedelta(hours=-5))
        running = datetime(2025, 6, 15, 10, 0, 0, tzinfo=est)
        transition = datetime(2025, 6, 15, 13, 0, 0, tzinfo=est)  # 3 hours later
        job = _make_job(running_at=running)

        metrics.record_transition(
            JobStatus.running,
            JobStatus.completed,
            job,
            transition,
            error_type=None,
            cost_per_pod_hour=0.20,
        )

        assert len(recorded) == 1
        assert recorded[0]["amount"] == pytest.approx(0.60, abs=1e-9)


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


# ── Integration: multiple jobs accumulate cost ──────────────────────────


class TestCostAccumulation:
    def test_multiple_jobs_accumulate(self):
        """Simulating several jobs finishing: total recorded cost should match sum."""
        metrics, recorded = _make_metrics()
        now = datetime.now(UTC)

        # 3 jobs of 30min, 1hr, 2hr at $0.20/hr
        durations_hours = [0.5, 1.0, 2.0]
        for dur in durations_hours:
            job = _make_job(running_at=now - timedelta(hours=dur))
            metrics.record_transition(
                JobStatus.running, JobStatus.completed, job, now, error_type=None, cost_per_pod_hour=0.20
            )

        assert len(recorded) == 3
        total = sum(r["amount"] for r in recorded)
        expected = sum(d * 0.20 for d in durations_hours)
        assert total == pytest.approx(expected, abs=1e-9)

    def test_mixed_completed_and_failed(self):
        """Both completed and failed jobs should contribute cost."""
        metrics, recorded = _make_metrics()
        now = datetime.now(UTC)

        # completed: 1hr
        job1 = _make_job(running_at=now - timedelta(hours=1))
        metrics.record_transition(
            JobStatus.running, JobStatus.completed, job1, now, error_type=None, cost_per_pod_hour=0.20
        )

        # failed: 2hr
        job2 = _make_job(running_at=now - timedelta(hours=2))
        metrics.record_transition(
            JobStatus.running, JobStatus.failed, job2, now, error_type="timeout", cost_per_pod_hour=0.20
        )

        assert len(recorded) == 2
        total = sum(r["amount"] for r in recorded)
        assert total == pytest.approx(0.60, abs=1e-9)


# ── Route integration: verify cost_per_pod_hour is passed via real HTTP ─


def _patch_pricing(monkeypatch: pytest.MonkeyPatch):
    """Mock AWS pricing APIs and clear caches for route integration tests."""
    _clear_pricing_caches()
    monkeypatch.setattr(pricing_mod, "_fetch_on_demand_price", _mock_on_demand_fetch)
    monkeypatch.setattr(pricing_mod, "_fetch_spot_price", lambda it, r: _MOCK_ON_DEMAND.get(it, 0.0) * 0.3)


class TestRouteIntegration:
    """End-to-end tests through the actual HTTP route with a real DB.

    These use the stats_client fixture (requires Docker/Postgres). They verify
    that the route code actually passes cost_per_pod_hour to record_transition
    — something unit tests can't prove.
    """

    def test_update_route_passes_cost_on_running_to_completed(self, stats_client, monkeypatch: pytest.MonkeyPatch):
        """Full lifecycle: create → dispatched → running → completed.
        Verify record_transition receives cost_per_pod_hour derived from instance pricing."""
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
            [
                JobRequestCreate(job_type=JobType.episode, job={"assignments": [0, 1], "env": {}, "seed": 1}),
            ]
        )
        assert len(job_ids) == 1

        # batch-create calls record_transition for pending→dispatched with cost_per_pod_hour=0.0
        batch_calls = [c for c in captured]
        assert len(batch_calls) >= 1
        assert batch_calls[-1]["kwargs"]["cost_per_pod_hour"] == 0.0

        captured.clear()

        # Transition dispatched → running
        client.update_job(job_ids[0], JobRequestUpdate(status=JobStatus.running, worker="test-worker"))
        assert len(captured) == 1
        assert captured[0]["args"][0] == JobStatus.dispatched

        captured.clear()

        # Set instance_type and capacity_type via result
        client.update_job(
            job_ids[0],
            JobRequestUpdate(result={"instance_type": "m5.xlarge", "capacity_type": "on-demand"}),
        )
        captured.clear()

        # Transition running → completed (THIS is where cost matters)
        client.update_job(job_ids[0], JobRequestUpdate(status=JobStatus.completed))
        assert len(captured) == 1
        # m5.xlarge on-demand costs $0.192/hr (from mock)
        assert captured[0]["kwargs"]["cost_per_pod_hour"] == pytest.approx(0.192)
        assert captured[0]["args"][0] == JobStatus.running

    def test_update_route_derives_cost_from_instance_type(self, stats_client, monkeypatch: pytest.MonkeyPatch):
        """When job.result has instance_type and capacity_type, cost should be derived from EC2 pricing."""
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
            [JobRequestCreate(job_type=JobType.episode, job={"assignments": [0, 1], "env": {}, "seed": 1})]
        )
        captured.clear()

        # dispatched → running
        client.update_job(job_ids[0], JobRequestUpdate(status=JobStatus.running, worker="test-worker"))
        captured.clear()

        # Set instance_type via result, then complete
        client.update_job(
            job_ids[0],
            JobRequestUpdate(result={"instance_type": "m5.xlarge", "capacity_type": "on-demand"}),
        )
        captured.clear()

        client.update_job(job_ids[0], JobRequestUpdate(status=JobStatus.completed))
        assert len(captured) == 1
        # m5.xlarge on-demand costs $0.192/hr (from mock)
        assert captured[0]["kwargs"]["cost_per_pod_hour"] == pytest.approx(0.192)

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

        # No cost should have been recorded — this was a pending→dispatched transition
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

        # Set result with instance info before completing
        stats_client.update_job(
            job_ids[0],
            JobRequestUpdate(result={"instance_type": "m5.xlarge", "capacity_type": "on-demand"}),
        )

        stats_client.update_job(job_ids[0], JobRequestUpdate(status=JobStatus.completed))
        assert len(cost_adds) == 1  # running→completed: cost emitted exactly once
        assert cost_adds[0]["amount"] > 0
        assert cost_adds[0]["attributes"] == {"job_type": "episode"}

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

        # Set result with instance info, then fail
        stats_client.update_job(
            job_ids[0],
            JobRequestUpdate(result={"instance_type": "m5.xlarge", "capacity_type": "on-demand"}),
        )

        stats_client.update_job(job_ids[0], JobRequestUpdate(status=JobStatus.failed, error="boom", error_type="oom"))
        assert len(cost_adds) == 1
        assert cost_adds[0]["amount"] > 0

    def test_failed_with_instance_type_derives_cost(self, stats_client, monkeypatch: pytest.MonkeyPatch):
        """running→failed with instance_type in result should use EC2 pricing."""
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
        captured.clear()

        # Fail with instance_type in result — cost should derive from pricing API
        client.update_job(
            job_ids[0],
            JobRequestUpdate(
                status=JobStatus.failed,
                error="oom",
                error_type="oom",
                result={"instance_type": "c5.xlarge", "capacity_type": "on-demand"},
            ),
        )
        assert len(captured) == 1
        # c5.xlarge on-demand costs $0.17/hr (from mock)
        assert captured[0]["kwargs"]["cost_per_pod_hour"] == pytest.approx(0.17)

    def test_no_instance_type_emits_zero_cost(self, stats_client, monkeypatch: pytest.MonkeyPatch):
        """When no instance_type in result, cost_per_pod_hour should be 0.0."""
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
        captured.clear()

        # Complete without setting result — no instance info available
        client.update_job(job_ids[0], JobRequestUpdate(status=JobStatus.completed))
        assert len(captured) == 1
        assert captured[0]["kwargs"]["cost_per_pod_hour"] == 0.0
