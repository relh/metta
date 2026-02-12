# Logging Follow-Up 3: Metric Decimation Tiers

## Area

`#6907` Logging/metrics

## Hypothesis

Logging 100+ metrics every epoch is overkill for many runs. Tiered frequencies (high/medium/low cadence) should cut
serialization/network overhead with minimal observability loss.

## Proposed Change

Add metric tiers with separate reporting intervals (e.g., every epoch, every 5 epochs, every 20 epochs) and classify
metrics by operational importance.

## Code Touch Points

- `metta/rl/training/stats_reporter.py` (payload builder + interval logic)
- `metta/rl/stats.py` (metric grouping helpers)

## Benchmark Plan

1. Baseline: full metric payload each epoch.
2. Variant: tiered decimation only.
3. Measure:

- payload size per log call
- `_process_stats` time
- agent-SPS
- usefulness of dashboards during run triage

## Success Criteria

- > = 40% payload size reduction
- > = 15% stats-phase time reduction
- no loss of must-have run-health metrics

## Guardrails

- Keep critical safety/health metrics always high-frequency.
- Expose config to disable tiering when full telemetry is needed.
