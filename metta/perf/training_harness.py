"""Reusable training performance benchmark harness.

Generalizes the configure/inject/invoke pattern from scripts/cogsguard_microbench.py
into a library that any recipe can use for structured SPS measurement, baseline
comparison, and scorecard integration.

The harness does NOT own the training loop — it configures a TrainTool, injects
MicrobenchReporter, runs training via the normal recipe path, then post-processes
the resulting JSON artifact.
"""

from __future__ import annotations

import importlib
import json
import shutil
import statistics
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Pydantic models for structured data flowing through the harness.
#
# EpochRecord matches _EpochRecord.__dict__ from microbench_reporter.py but is
# intentionally a separate type — the JSON artifact file is the boundary.
# ---------------------------------------------------------------------------


class EpochRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    epoch: int
    agent_step: int
    sps: float | None
    train_time: float | None
    rollout_time: float | None
    stats_time: float | None
    rollout_env_wait_time: float | None
    rollout_td_prep_time: float | None
    rollout_inference_time: float | None
    rollout_send_time: float | None


class ArtifactSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sps_mean: float
    sps_median: float
    sps_p10: float
    sps_p90: float
    samples: int = Field(ge=0)


class MicrobenchArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    warmup_epochs: int = Field(ge=0)
    records: list[EpochRecord]
    effective_records: list[EpochRecord]
    summary: ArtifactSummary
    run_metadata: dict[str, Any]


class PhaseStats(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mean: float
    count: int = Field(ge=0)
    pct: float


class TrainingStatistics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sps_mean: float
    sps_median: float
    sps_std: float = Field(ge=0)
    sps_p10: float
    sps_p90: float
    cv: float = Field(ge=0)
    stability: str
    epochs: int = Field(ge=0)
    phases: dict[str, PhaseStats]
    rollout_mean: float
    rollout_pct: float


class SavedResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp: str
    phase: str
    config: dict[str, Any]
    metrics: TrainingStatistics


class Comparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    baseline_phase: str
    current_phase: str
    baseline_sps: float
    current_sps: float
    sps_improvement_pct: float
    phase_pct_changes: dict[str, float]


class GitInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    git_head: str
    git_branch: str


class PhaseReportRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phase: str
    sps: float
    cv: float
    epochs: int = Field(ge=0)
    timestamp: str


# ---------------------------------------------------------------------------
# Preset definitions (data-only — no recipe imports at module load time)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TrainingPreset:
    name: str
    description: str
    recipe_module: str
    recipe_function: str
    total_timesteps: int
    warmup_epochs: int


PRESET_CONFIGS: dict[str, TrainingPreset] = {
    "smoke": TrainingPreset(
        name="smoke",
        description="16 timesteps, serial, no GPU (verifies harness wiring)",
        recipe_module="recipes.experiment.ci",
        recipe_function="train",
        total_timesteps=16,
        warmup_epochs=0,
    ),
    "quick": TrainingPreset(
        name="quick",
        description="2M timesteps, arena, single GPU (~5-10 min)",
        recipe_module="recipes.prod.arena_basic_easy_shaped",
        recipe_function="train",
        total_timesteps=2_000_000,
        warmup_epochs=2,
    ),
    "standard": TrainingPreset(
        name="standard",
        description="10M timesteps, arena, single GPU (~30-60 min)",
        recipe_module="recipes.prod.arena_basic_easy_shaped",
        recipe_function="train",
        total_timesteps=10_000_000,
        warmup_epochs=2,
    ),
    "prod_single": TrainingPreset(
        name="prod_single",
        description="100M timesteps, arena, full production single-GPU",
        recipe_module="recipes.prod.arena_basic_easy_shaped",
        recipe_function="train_100m",
        total_timesteps=100_000_000,
        warmup_epochs=2,
    ),
}

# Training phases tracked by MicrobenchReporter (via StatsReporter/Stopwatch).
TRAINING_PHASES = [
    "rollout_inference_time",
    "train_time",
    "rollout_env_wait_time",
    "rollout_td_prep_time",
    "rollout_send_time",
    "stats_time",
]


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------


def load_preset(name: str) -> Any:
    """Lazy-import a recipe and return a configured TrainTool.

    Returns a TrainTool instance. Caller reads PRESET_CONFIGS[name].warmup_epochs
    separately. Uses Any return type to avoid importing TrainTool at module level
    (which pulls in torch).
    """
    preset = PRESET_CONFIGS[name]
    module = importlib.import_module(preset.recipe_module)
    maker = getattr(module, preset.recipe_function)
    tool = maker()
    tool.trainer.total_timesteps = preset.total_timesteps
    return tool


def configure_for_benchmark(
    tool: Any,
    *,
    run_name: str,
    output_path: Path,
    warmup_epochs: int = 2,
    print_per_epoch: bool = False,
    run_metadata: dict[str, Any] | None = None,
) -> None:
    """Mutate a TrainTool in-place to prepare it for benchmarking.

    Strips external services, disables eval/checkpoint overhead, and injects
    MicrobenchReporter via extra_components.

    Extracted from scripts/cogsguard_microbench.py lines 156-254.
    """
    # Lazy imports to avoid pulling in torch at module load time.
    from metta.common.wandb.context import WandbConfig  # noqa: PLC0415
    from metta.rl.training import MicrobenchReporter, MicrobenchReporterConfig  # noqa: PLC0415

    # Strip external services.
    tool.wandb = WandbConfig.Off()
    tool.stats_server_uri = None
    tool.group = None

    # Disable eval and checkpoint overhead.
    tool.evaluator.epoch_interval = 0
    tool.evaluator.evaluate_local = False
    for asset in tool.policy_assets.values():
        asset.checkpoint = False

    # Ensure StatsReporter reports every epoch (MicrobenchReporter reads its payload).
    tool.stats_reporter.report_to_wandb = False
    tool.stats_reporter.interval = 1

    # Prevent Darwin auto-minimization from shrinking batch sizes.
    tool.disable_macbook_optimize = True

    # Set the benchmark run name directly so apply_defaults_and_mutations sees
    # self.run as already set (run_from_cli=False).  This avoids the single-asset
    # guard in _finalize_policy_assets that rejects CLI run overrides for
    # multi-policy recipes.
    tool.run = run_name

    # Inject MicrobenchReporter.
    tool.extra_components.append(
        MicrobenchReporter(
            MicrobenchReporterConfig(
                warmup_epochs=warmup_epochs,
                output_path=output_path,
                print_per_epoch=print_per_epoch,
            ),
            run_metadata=run_metadata,
        )
    )


# ---------------------------------------------------------------------------
# Artifact loading and statistics
# ---------------------------------------------------------------------------


def load_artifact(path: Path) -> MicrobenchArtifact:
    """Load a MicrobenchReporter JSON artifact."""
    if not path.exists():
        raise FileNotFoundError(
            f"MicrobenchReporter artifact not found at {path}. Training may have crashed before writing the artifact."
        )
    return MicrobenchArtifact.model_validate(json.loads(path.read_text(encoding="utf-8")))


def compute_training_statistics(artifact: MicrobenchArtifact) -> TrainingStatistics:
    """Compute extended statistics from a MicrobenchReporter artifact.

    Adds CV, phase timing breakdown, and stability assessment to the
    existing summary produced by MicrobenchReporter.
    """
    summary = artifact.summary
    effective = artifact.effective_records

    sps_mean = summary.sps_mean
    sps_median = summary.sps_median
    samples = summary.samples

    # Compute SPS std and CV from effective records.
    sps_vals = [r.sps for r in effective if r.sps is not None]
    sps_std = statistics.stdev(sps_vals) if len(sps_vals) >= 2 else 0.0
    cv = sps_std / sps_mean if sps_mean > 0 else 0.0

    # Phase timing breakdown.
    phase_stats: dict[str, PhaseStats] = {}
    for phase in TRAINING_PHASES:
        vals = [getattr(r, phase) for r in effective if getattr(r, phase) is not None]
        mean = statistics.fmean(vals) if vals else 0.0
        phase_stats[phase] = PhaseStats(mean=mean, count=len(vals), pct=0.0)

    # Rollout subtotal for verification.
    rollout_vals = [r.rollout_time for r in effective if r.rollout_time is not None]
    rollout_mean = statistics.fmean(rollout_vals) if rollout_vals else 0.0

    # Compute total epoch time (rollout + train + stats) for percentages.
    epoch_total = rollout_mean + phase_stats["train_time"].mean + phase_stats["stats_time"].mean
    for phase in TRAINING_PHASES:
        pct = (phase_stats[phase].mean / epoch_total) * 100 if epoch_total > 0 else 0.0
        phase_stats[phase] = phase_stats[phase].model_copy(update={"pct": pct})
    # Rollout subtotal percentage.
    rollout_pct = (rollout_mean / epoch_total * 100) if epoch_total > 0 else 0.0

    if cv < 0.05:
        stability = "Excellent (CV < 5%)"
    elif cv < 0.10:
        stability = "Good (CV < 10%)"
    elif cv < 0.20:
        stability = "Fair (CV < 20%)"
    else:
        stability = "Poor (CV >= 20%) - results may be unreliable"

    return TrainingStatistics(
        sps_mean=sps_mean,
        sps_median=sps_median,
        sps_std=sps_std,
        sps_p10=summary.sps_p10,
        sps_p90=summary.sps_p90,
        cv=cv,
        stability=stability,
        epochs=samples,
        phases=phase_stats,
        rollout_mean=rollout_mean,
        rollout_pct=rollout_pct,
    )


# ---------------------------------------------------------------------------
# Output and comparison
# ---------------------------------------------------------------------------


def save_results(
    stats: TrainingStatistics,
    config: dict[str, Any],
    phase: str,
    output_path: Path,
) -> None:
    """Save benchmark results in the standard harness format."""
    result = SavedResult(
        timestamp=datetime.now().isoformat(),
        phase=phase,
        config=config,
        metrics=stats,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8")
    print(f"\nResults saved to: {output_path}")


def compare_results(
    baseline_path: Path,
    current_stats: TrainingStatistics,
    current_phase: str,
) -> Comparison:
    """Compare current results against a baseline."""
    baseline = SavedResult.model_validate(json.loads(baseline_path.read_text(encoding="utf-8")))

    base_sps = baseline.metrics.sps_mean
    curr_sps = current_stats.sps_mean
    improvement = ((curr_sps - base_sps) / base_sps) * 100 if base_sps > 0 else 0.0

    # Per-phase timing changes.
    phase_changes: dict[str, float] = {}
    for phase_name in TRAINING_PHASES:
        bp = baseline.metrics.phases[phase_name].pct
        cp = current_stats.phases[phase_name].pct
        phase_changes[phase_name] = cp - bp

    return Comparison(
        baseline_phase=baseline.phase,
        current_phase=current_phase,
        baseline_sps=base_sps,
        current_sps=curr_sps,
        sps_improvement_pct=improvement,
        phase_pct_changes=phase_changes,
    )


def compare_multiple(
    baseline_paths: list[Path],
    current_stats: TrainingStatistics,
    current_phase: str,
) -> list[Comparison]:
    """Compare current results against multiple baselines."""
    return [compare_results(baseline_path, current_stats, current_phase) for baseline_path in baseline_paths]


# ---------------------------------------------------------------------------
# Printing / reporting
# ---------------------------------------------------------------------------


def print_phase_breakdown(stats: TrainingStatistics) -> None:
    """Print timing breakdown by training phase."""
    print(f"\n  {'Phase':<28} {'Mean (s)':>10} {'% of epoch':>12}")
    print(f"  {'-' * 52}")
    for phase_name in TRAINING_PHASES:
        p = stats.phases[phase_name]
        print(f"  {phase_name:<28} {p.mean:>10.3f} {p.pct:>11.1f}%")
    print(f"  {'-' * 52}")
    print(f"  {'rollout_time (subtotal)':<28} {stats.rollout_mean:>10.3f} {stats.rollout_pct:>11.1f}%")


def print_comparison(comparison: Comparison) -> None:
    """Print a single comparison."""
    print(f"\n  vs {comparison.baseline_phase}:")
    print(f"    Baseline SPS: {comparison.baseline_sps:,.0f}")
    print(f"    Current SPS:  {comparison.current_sps:,.0f}")
    print(f"    SPS Improvement: {comparison.sps_improvement_pct:+.1f}%")

    changed = {k: v for k, v in comparison.phase_pct_changes.items() if abs(v) > 0.5}
    if changed:
        print("    Phase shifts:")
        for phase_name, delta in sorted(changed.items(), key=lambda x: abs(x[1]), reverse=True):
            print(f"      {phase_name}: {delta:+.1f}pp")


def print_scorecard_row(
    stats: TrainingStatistics,
    *,
    config_label: str,
    phase: str = "",
    baseline_paths: list[Path] | None = None,
    output_path: Path | None = None,
) -> None:
    """Print a scorecard-ready row for docs/perf/scorecard.md."""
    delta = ""
    if baseline_paths:
        first = baseline_paths[0]
        baseline = SavedResult.model_validate(json.loads(first.read_text(encoding="utf-8")))
        base_sps = baseline.metrics.sps_mean
        pct = ((stats.sps_mean - base_sps) / base_sps) * 100 if base_sps > 0 else 0.0
        delta = f"{pct:+.0f}% SPS"

    print(f"\n{'=' * 60}")
    print("Scorecard row (paste into docs/perf/scorecard.md):")
    print(f"| #???? | {config_label} | {phase or 'main'} | {stats.epochs} epochs | 1 | {delta or 'TBD'} | TBD | |")
    if output_path:
        print(f"\nUpdate perf scorecard → /tr.perf-scorecard {output_path}")
    else:
        print("\nUpdate perf scorecard → /tr.perf-scorecard")


def generate_phase_report(results_dir: str) -> None:
    """Generate a summary report from a directory of result JSON files."""
    results_path = Path(results_dir)
    if not results_path.is_dir():
        raise FileNotFoundError(f"Results directory not found: {results_dir}")

    result_files = sorted(results_path.glob("*.json"))
    if not result_files:
        raise ValueError(f"No .json result files in {results_dir}")

    print(f"\n{'=' * 60}")
    print("Phase-by-Phase Training Performance Summary")
    print(f"{'=' * 60}")

    rows: list[PhaseReportRow] = []
    for rf in result_files:
        result = SavedResult.model_validate(json.loads(rf.read_text(encoding="utf-8")))
        rows.append(
            PhaseReportRow(
                phase=result.phase,
                sps=result.metrics.sps_mean,
                cv=result.metrics.cv,
                epochs=result.metrics.epochs,
                timestamp=result.timestamp,
            )
        )

    print(f"\n{'Phase':<20} {'SPS':>10} {'vs Baseline':>12} {'CV':>8} {'Epochs':>8}")
    print("-" * 60)

    baseline_sps = rows[0].sps
    for row in rows:
        improvement = ((row.sps - baseline_sps) / baseline_sps * 100) if baseline_sps > 0 else 0.0
        print(f"{row.phase:<20} {row.sps:>10,.0f} {improvement:>+11.1f}% {row.cv:>7.2f} {row.epochs:>8}")

    if len(rows) >= 2:
        total = ((rows[-1].sps - rows[0].sps) / rows[0].sps) * 100 if rows[0].sps > 0 else 0.0
        print("-" * 60)
        print(f"{'Total improvement':<20} {'':>10} {total:>+11.1f}%")


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def best_effort_git_info() -> GitInfo | None:
    """Collect git HEAD and branch for artifact metadata.

    Returns None if git is not installed or not in a repository.
    """
    if shutil.which("git") is None:
        return None

    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    if head.returncode != 0:
        return None

    branch = subprocess.run(
        ["git", "branch", "--show-current"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )

    return GitInfo(
        git_head=head.stdout.strip(),
        git_branch=branch.stdout.strip() if branch.returncode == 0 else "",
    )
