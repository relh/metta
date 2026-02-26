"""Tests for metta.perf.training_harness post-processing and comparison logic.

All tests use mock artifact data — no GPU or training required.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from metta.perf.training_harness import (
    PRESET_CONFIGS,
    TRAINING_PHASES,
    ArtifactSummary,
    EpochRecord,
    MicrobenchArtifact,
    SavedResult,
    compare_multiple,
    compare_results,
    compute_training_statistics,
    generate_phase_report,
    load_artifact,
    save_results,
)


def _make_artifact(
    num_records: int = 10,
    sps: float = 150000.0,
    sps_noise: float = 5000.0,
    train_time: float = 0.45,
    rollout_time: float = 0.55,
    stats_time: float = 0.02,
    rollout_env_wait_time: float = 0.07,
    rollout_td_prep_time: float = 0.02,
    rollout_inference_time: float = 0.44,
    rollout_send_time: float = 0.002,
    warmup_epochs: int = 2,
) -> MicrobenchArtifact:
    """Create a synthetic MicrobenchReporter artifact."""
    records: list[EpochRecord] = []
    effective: list[EpochRecord] = []
    for i in range(num_records):
        rec = EpochRecord(
            epoch=i,
            agent_step=i * 10000,
            sps=sps + (i - num_records / 2) * (sps_noise / num_records),
            train_time=train_time,
            rollout_time=rollout_time,
            stats_time=stats_time,
            rollout_env_wait_time=rollout_env_wait_time,
            rollout_td_prep_time=rollout_td_prep_time,
            rollout_inference_time=rollout_inference_time,
            rollout_send_time=rollout_send_time,
        )
        records.append(rec)
        if i > warmup_epochs:
            effective.append(rec)

    sps_vals = [r.sps for r in effective if r.sps is not None]
    sps_mean = sum(sps_vals) / len(sps_vals) if sps_vals else 0.0
    sps_sorted = sorted(sps_vals)
    sps_median = sps_sorted[len(sps_sorted) // 2] if sps_vals else 0.0

    return MicrobenchArtifact(
        status="completed",
        warmup_epochs=warmup_epochs,
        records=records,
        effective_records=effective,
        summary=ArtifactSummary(
            sps_mean=sps_mean,
            sps_median=sps_median,
            sps_p10=sps_sorted[1] if len(sps_sorted) > 1 else sps_mean,
            sps_p90=sps_sorted[-2] if len(sps_sorted) > 1 else sps_mean,
            samples=len(sps_vals),
        ),
        run_metadata={"run": "test"},
    )


class TestComputeTrainingStatistics:
    def test_basic(self):
        artifact = _make_artifact(num_records=10, sps=150000.0, sps_noise=5000.0)
        stats = compute_training_statistics(artifact)

        assert stats.sps_mean > 0
        assert stats.sps_median > 0
        assert stats.sps_std >= 0
        assert 0 <= stats.cv < 1.0
        assert stats.epochs > 0
        assert "Excellent" in stats.stability or "Good" in stats.stability

        # Phase breakdown should exist.
        assert "rollout_inference_time" in stats.phases
        assert "train_time" in stats.phases
        assert stats.phases["rollout_inference_time"].pct > 0
        assert stats.phases["train_time"].pct > 0

        # Percentages should roughly sum to 100.
        total_pct = sum(p.pct for p in stats.phases.values())
        assert 95 < total_pct < 105

    def test_single_record(self):
        """Edge case: one effective record means std=0, cv=0."""
        artifact = _make_artifact(num_records=2, warmup_epochs=0)
        stats = compute_training_statistics(artifact)
        assert stats.sps_std == 0.0
        assert stats.cv == 0.0
        assert "Excellent" in stats.stability

    def test_poor_stability(self):
        artifact = _make_artifact(num_records=10, sps=100000.0, sps_noise=50000.0)
        stats = compute_training_statistics(artifact)
        # With high noise relative to mean, CV should be elevated.
        assert stats.cv > 0

    def test_empty_effective_records(self):
        artifact = _make_artifact(num_records=2, warmup_epochs=5)
        # All records have epoch < warmup_epochs, so effective_records is empty.
        artifact = artifact.model_copy(
            update={
                "effective_records": [],
                "summary": ArtifactSummary(sps_mean=0, sps_median=0, sps_p10=0, sps_p90=0, samples=0),
            }
        )
        stats = compute_training_statistics(artifact)
        assert stats.sps_mean == 0
        assert stats.epochs == 0

    def test_none_timing_fields(self):
        """Records with None timing fields are excluded from phase mean/count."""
        records: list[EpochRecord] = []
        effective: list[EpochRecord] = []
        for i in range(10):
            rec = EpochRecord(
                epoch=i,
                agent_step=i * 10000,
                sps=150000.0,
                train_time=0.5 if i % 2 == 0 else None,
                rollout_time=0.5 if i % 2 == 0 else None,
                stats_time=0.02,
                rollout_env_wait_time=None,
                rollout_td_prep_time=None,
                rollout_inference_time=None,
                rollout_send_time=None,
            )
            records.append(rec)
            if i > 2:
                effective.append(rec)

        artifact = MicrobenchArtifact(
            status="completed",
            warmup_epochs=2,
            records=records,
            effective_records=effective,
            summary=ArtifactSummary(
                sps_mean=150000.0,
                sps_median=150000.0,
                sps_p10=150000.0,
                sps_p90=150000.0,
                samples=len(effective),
            ),
            run_metadata={"run": "test"},
        )
        stats = compute_training_statistics(artifact)

        # All-None phases: count=0, mean=0.
        assert stats.phases["rollout_env_wait_time"].count == 0
        assert stats.phases["rollout_env_wait_time"].mean == 0.0

        # Half-None phase: count < total effective records.
        assert 0 < stats.phases["train_time"].count < len(effective)

        # Always-present phase: count == total effective records.
        assert stats.phases["stats_time"].count == len(effective)

    def test_rollout_subphases_sum_to_rollout_pct(self):
        """Rollout sub-phase percentages should approximate rollout_pct."""
        stats = compute_training_statistics(_make_artifact())
        rollout_subphase_pct = sum(
            stats.phases[p].pct
            for p in ["rollout_env_wait_time", "rollout_td_prep_time", "rollout_inference_time", "rollout_send_time"]
        )
        # Sub-phases won't exactly equal rollout_pct because rollout_time is
        # measured independently, but they should be close.
        assert abs(rollout_subphase_pct - stats.rollout_pct) < 5

    def test_phase_pct_shifts_with_timing(self):
        """Doubling train_time shifts its share from ~50% to ~67%."""
        stats_a = compute_training_statistics(_make_artifact(train_time=0.5, rollout_time=0.5, stats_time=0.0))
        stats_b = compute_training_statistics(_make_artifact(train_time=1.0, rollout_time=0.5, stats_time=0.0))
        # train/(train+rollout): 0.5/1.0 = 50%, 1.0/1.5 ≈ 67%.
        assert 45 < stats_a.phases["train_time"].pct < 55
        assert 62 < stats_b.phases["train_time"].pct < 72
        assert stats_b.rollout_pct < stats_a.rollout_pct


class TestSaveAndLoadResults:
    def test_round_trip(self, tmp_path: Path):
        artifact = _make_artifact()
        stats = compute_training_statistics(artifact)
        config = {"preset": "quick", "total_timesteps": 2000000}
        output = tmp_path / "results.json"

        save_results(stats, config, "baseline", output)
        assert output.exists()

        loaded = SavedResult.model_validate_json(output.read_text())
        assert loaded.phase == "baseline"
        assert loaded.config["preset"] == "quick"
        assert loaded.metrics.sps_mean == stats.sps_mean
        assert loaded.timestamp

    def test_json_structure_keys(self, tmp_path: Path):
        """SavedResult JSON has an exact key structure for cross-version compatibility."""
        stats = compute_training_statistics(_make_artifact())
        path = tmp_path / "result.json"
        save_results(stats, {"preset": "quick"}, "baseline", path)

        raw = json.loads(path.read_text())

        # Top-level keys (exact — extra="forbid" guarantees no extras).
        assert set(raw.keys()) == {"timestamp", "phase", "config", "metrics"}

        # Metrics keys (exact).
        assert set(raw["metrics"].keys()) == {
            "sps_mean",
            "sps_median",
            "sps_std",
            "sps_p10",
            "sps_p90",
            "cv",
            "stability",
            "epochs",
            "phases",
            "rollout_mean",
            "rollout_pct",
        }

        # Every TRAINING_PHASE present with exact keys.
        assert set(raw["metrics"]["phases"].keys()) == set(TRAINING_PHASES)
        for phase_name in TRAINING_PHASES:
            assert set(raw["metrics"]["phases"][phase_name].keys()) == {"mean", "count", "pct"}


class TestCompareResults:
    def test_improvement(self, tmp_path: Path):
        # Baseline: 100k SPS.
        baseline_artifact = _make_artifact(sps=100000.0, sps_noise=1000.0)
        baseline_stats = compute_training_statistics(baseline_artifact)
        baseline_path = tmp_path / "baseline.json"
        save_results(baseline_stats, {}, "baseline", baseline_path)

        # Current: 120k SPS (20% improvement).
        current_artifact = _make_artifact(sps=120000.0, sps_noise=1000.0)
        current_stats = compute_training_statistics(current_artifact)

        comparison = compare_results(baseline_path, current_stats, "optimized")
        assert comparison.baseline_phase == "baseline"
        assert comparison.current_phase == "optimized"
        assert 18 < comparison.sps_improvement_pct < 22  # ~20%
        # Phase changes should cover all TRAINING_PHASES.
        assert set(comparison.phase_pct_changes.keys()) == set(TRAINING_PHASES)
        # Same timing defaults → deltas should be near zero.
        for delta in comparison.phase_pct_changes.values():
            assert abs(delta) < 0.1

    def test_regression(self, tmp_path: Path):
        baseline_artifact = _make_artifact(sps=100000.0)
        baseline_stats = compute_training_statistics(baseline_artifact)
        baseline_path = tmp_path / "baseline.json"
        save_results(baseline_stats, {}, "baseline", baseline_path)

        current_artifact = _make_artifact(sps=80000.0)
        current_stats = compute_training_statistics(current_artifact)

        comparison = compare_results(baseline_path, current_stats, "regressed")
        assert comparison.sps_improvement_pct < 0

    def test_zero_sps_baseline(self, tmp_path: Path):
        """Zero-SPS baseline should produce 0% improvement, not division error."""
        baseline_stats = compute_training_statistics(
            _make_artifact(num_records=2, warmup_epochs=5).model_copy(
                update={
                    "effective_records": [],
                    "summary": ArtifactSummary(sps_mean=0, sps_median=0, sps_p10=0, sps_p90=0, samples=0),
                }
            )
        )
        baseline_path = tmp_path / "baseline.json"
        save_results(baseline_stats, {}, "baseline", baseline_path)

        current_stats = compute_training_statistics(_make_artifact())
        comparison = compare_results(baseline_path, current_stats, "current")
        assert comparison.sps_improvement_pct == 0.0

    def test_baseline_missing_phase_crashes(self, tmp_path: Path):
        """Baselines saved before a new phase was added are incompatible.

        compare_results iterates TRAINING_PHASES and indexes into both
        baseline and current phases. If the baseline is missing a phase,
        it should crash (not silently skip).
        """
        baseline_stats = compute_training_statistics(_make_artifact())
        # Remove a phase to simulate an older baseline.
        reduced_phases = {k: v for k, v in baseline_stats.phases.items() if k != "stats_time"}
        baseline_stats = baseline_stats.model_copy(update={"phases": reduced_phases})
        baseline_path = tmp_path / "baseline.json"
        save_results(baseline_stats, {}, "baseline", baseline_path)

        current_stats = compute_training_statistics(_make_artifact())
        with pytest.raises(KeyError):
            compare_results(baseline_path, current_stats, "current")


class TestCompareMultiple:
    def test_missing_baseline(self, tmp_path: Path):
        current_stats = compute_training_statistics(_make_artifact())
        missing = tmp_path / "does_not_exist.json"
        with pytest.raises(FileNotFoundError):
            compare_multiple([missing], current_stats, "current")

    def test_overlapping_output_and_baseline(self, tmp_path: Path):
        """compare_multiple must read the baseline before save_results overwrites it.

        Simulates --output X --baseline X: iterative benchmarking where the
        same file holds the previous run's results and receives the new run's.
        """
        path = tmp_path / "results.json"

        # Previous run: 100k SPS.
        baseline_stats = compute_training_statistics(_make_artifact(sps=100000.0, sps_noise=1000.0))
        save_results(baseline_stats, {}, "baseline", path)

        # Current run: 120k SPS (~20% improvement).
        current_stats = compute_training_statistics(_make_artifact(sps=120000.0, sps_noise=1000.0))

        # Correct order: read baseline, then overwrite with new results.
        comparisons = compare_multiple([path], current_stats, "opt1")
        save_results(current_stats, {}, "opt1", path)

        # If save happened before compare, this would be ~0% (self-comparison).
        assert comparisons[0].sps_improvement_pct > 15


class TestLoadArtifact:
    def test_missing_file(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError, match="artifact not found"):
            load_artifact(tmp_path / "nonexistent.json")

    def test_valid_artifact(self, tmp_path: Path):
        artifact = _make_artifact()
        path = tmp_path / "artifact.json"
        path.write_text(json.dumps(artifact.model_dump(mode="json")))
        loaded = load_artifact(path)
        assert loaded.status == "completed"

    def test_extra_top_level_field_rejected(self, tmp_path: Path):
        """extra='forbid' catches schema drift at the artifact level."""
        raw = _make_artifact().model_dump(mode="json")
        raw["unexpected_field"] = "boom"
        path = tmp_path / "artifact.json"
        path.write_text(json.dumps(raw))
        with pytest.raises(ValidationError):
            load_artifact(path)

    def test_extra_epoch_field_rejected(self, tmp_path: Path):
        """extra='forbid' catches schema drift inside nested EpochRecords."""
        raw = _make_artifact().model_dump(mode="json")
        raw["records"][0]["new_metric"] = 42.0
        path = tmp_path / "artifact.json"
        path.write_text(json.dumps(raw))
        with pytest.raises(ValidationError):
            load_artifact(path)

    def test_extra_summary_field_rejected(self, tmp_path: Path):
        """extra='forbid' catches schema drift inside ArtifactSummary."""
        raw = _make_artifact().model_dump(mode="json")
        raw["summary"]["new_stat"] = 99.9
        path = tmp_path / "artifact.json"
        path.write_text(json.dumps(raw))
        with pytest.raises(ValidationError):
            load_artifact(path)


class TestGeneratePhaseReport:
    def test_missing_directory(self):
        with pytest.raises(FileNotFoundError):
            generate_phase_report("/nonexistent/path")

    def test_empty_directory(self, tmp_path: Path):
        with pytest.raises(ValueError, match="No .json"):
            generate_phase_report(str(tmp_path))

    def test_multi_phase_report(self, tmp_path: Path, capsys):
        """Multiple result files produce a table with baseline-relative deltas.

        Files are sorted alphabetically; the first file becomes the baseline.
        """
        for phase, sps in [("baseline", 100000.0), ("opt1", 110000.0), ("opt2", 125000.0)]:
            stats = compute_training_statistics(_make_artifact(sps=sps, sps_noise=1000.0))
            save_results(stats, {}, phase, tmp_path / f"{phase}.json")

        generate_phase_report(str(tmp_path))
        output = capsys.readouterr().out

        assert "baseline" in output
        assert "opt1" in output
        assert "opt2" in output
        # First file is the baseline reference — its delta should be +0.0%.
        assert "+0.0%" in output
        # Total improvement line should appear for 2+ files.
        assert "Total improvement" in output

    def test_single_file_report(self, tmp_path: Path, capsys):
        """Single result file: no 'Total improvement', self-delta is +0.0%."""
        stats = compute_training_statistics(_make_artifact())
        save_results(stats, {}, "baseline", tmp_path / "results.json")

        generate_phase_report(str(tmp_path))
        output = capsys.readouterr().out
        assert "baseline" in output
        assert "+0.0%" in output
        assert "Total improvement" not in output


class TestPresetNames:
    def test_all_presets_have_valid_modules(self):
        """All preset recipe_module values should be importable (no invocation)."""
        for name, preset in PRESET_CONFIGS.items():
            try:
                module = importlib.import_module(preset.recipe_module)
                assert hasattr(module, preset.recipe_function), (
                    f"Preset '{name}': {preset.recipe_module} has no function '{preset.recipe_function}'"
                )
            except ImportError:
                pytest.skip(f"Recipe module {preset.recipe_module} not installed")
