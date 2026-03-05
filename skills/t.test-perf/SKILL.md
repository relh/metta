---
name: t.test-perf
description: 'Use when testing perf.'
---

# Test Perf

## Trigger

- Primary: "perf again"
- Variant: "perf changes before we merge please"
- Variant: "perf ppo memory profiling diff to main"

## Workflow

- Define the perf target up front (metric, threshold, hardware context, and workload/seed settings).
- Run a repeatable protocol (same config, multiple runs) instead of single-sample conclusions.
- Compare against an explicit baseline and flag both regressions and statistically noisy results.
- Report commands, median/variance, and whether the change clears the perf gate.
