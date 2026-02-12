"""Microbench reporting utilities.

This is intentionally lightweight and intended for local perf work.
It records per-epoch SPS and timing breakdowns from StatsReporter payloads and
emits a small JSON artifact for before/after comparisons.
"""

from __future__ import annotations

import json
import logging
import numbers
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from metta.rl.training.component import TrainerComponent
from mettagrid.base_config import Config

logger = logging.getLogger(__name__)


class MicrobenchReporterConfig(Config):
    warmup_epochs: int = 2
    """Ignore the first N epochs when aggregating summary statistics."""

    output_path: Path | None = None
    """If set, write a JSON artifact at the end of the run."""

    print_per_epoch: bool = False
    """If True, log per-epoch microbench metrics as they are recorded."""

    max_records: int = 10_000
    """Safety cap so we don't accumulate unbounded memory."""


@dataclass(frozen=True)
class _EpochRecord:
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


def _get_float(payload: dict[str, float], key: str) -> float | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, numbers.Real):
        raise TypeError(f"Expected numeric payload for {key!r}, got {type(value).__name__}")
    return float(value)


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])
    xs = sorted(float(v) for v in values)
    n = len(xs)

    # Linear interpolation between adjacent ranks.
    pos = (n - 1) * (p / 100.0)
    lo = int(pos)
    hi = min(lo + 1, n - 1)
    frac = pos - lo
    return xs[lo] * (1.0 - frac) + xs[hi] * frac


def _p10_p90(values: list[float]) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    return _percentile(values, 10.0), _percentile(values, 90.0)


class MicrobenchReporter(TrainerComponent):
    """Collect per-epoch performance stats and emit a summary + optional artifact."""

    _master_only = True

    def __init__(self, config: MicrobenchReporterConfig, *, run_metadata: dict[str, Any] | None = None) -> None:
        super().__init__(epoch_interval=1)
        self._cfg = config
        self._records: list[_EpochRecord] = []
        self._run_metadata = dict(run_metadata or {})

    def on_epoch_end(self, epoch: int) -> None:  # type: ignore[override]
        if len(self._records) >= int(self._cfg.max_records):
            return

        stats_reporter = getattr(self.context, "stats_reporter", None)
        if stats_reporter is None:
            return

        payload = stats_reporter.get_latest_payload() or {}
        if not payload:
            return

        rec = _EpochRecord(
            epoch=int(epoch),
            agent_step=int(getattr(self.context, "agent_step", 0)),
            sps=_get_float(payload, "overview/steps_per_second"),
            train_time=_get_float(payload, "metric/train_time"),
            rollout_time=_get_float(payload, "metric/rollout_time"),
            stats_time=_get_float(payload, "metric/stats_time"),
            rollout_env_wait_time=_get_float(payload, "metric/rollout_env_wait_time"),
            rollout_td_prep_time=_get_float(payload, "metric/rollout_td_prep_time"),
            rollout_inference_time=_get_float(payload, "metric/rollout_inference_time"),
            rollout_send_time=_get_float(payload, "metric/rollout_send_time"),
        )
        self._records.append(rec)

        if self._cfg.print_per_epoch:
            sps = rec.sps
            if sps is None:
                return
            logger.info(
                "microbench epoch=%s agent_step=%s sps=%.0f rollout=%.3fs train=%.3fs stats=%.3fs",
                rec.epoch,
                rec.agent_step,
                sps,
                rec.rollout_time or 0.0,
                rec.train_time or 0.0,
                rec.stats_time or 0.0,
            )

    def on_training_complete(self) -> None:  # type: ignore[override]
        self._emit_summary_and_artifact(status="completed")

    def on_failure(self) -> None:  # type: ignore[override]
        self._emit_summary_and_artifact(status="failed")

    def _emit_summary_and_artifact(self, *, status: str) -> None:
        if not self._records:
            return

        warmup = int(self._cfg.warmup_epochs)
        effective = [r for r in self._records if r.epoch > warmup and r.sps is not None]
        if not effective:
            return

        sps_vals = [float(r.sps) for r in effective if r.sps is not None]
        sps_mean = statistics.fmean(sps_vals) if sps_vals else 0.0
        sps_median = statistics.median(sps_vals) if sps_vals else 0.0
        sps_p10, sps_p90 = _p10_p90(sps_vals)

        logger.info(
            "microbench summary status=%s warmup_epochs=%s samples=%s "
            "sps_mean=%.0f sps_median=%.0f sps_p10=%.0f sps_p90=%.0f",
            status,
            warmup,
            len(sps_vals),
            sps_mean,
            sps_median,
            sps_p10,
            sps_p90,
        )

        out_path = self._cfg.output_path
        if out_path is None:
            return

        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        artifact = {
            "status": status,
            "warmup_epochs": warmup,
            "records": [r.__dict__ for r in self._records],
            "effective_records": [r.__dict__ for r in effective],
            "summary": {
                "sps_mean": sps_mean,
                "sps_median": sps_median,
                "sps_p10": sps_p10,
                "sps_p90": sps_p90,
                "samples": len(sps_vals),
            },
            "run_metadata": self._run_metadata,
        }

        tmp = out_path.with_suffix(out_path.suffix + ".tmp")
        tmp.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(out_path)
