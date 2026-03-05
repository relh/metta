---
name: tr.fix-agent-performance-regressions
description: 'Use when fixing agent performance regressions.'
---

# Fix Agent Performance Regressions

## Trigger

- Primary: "fixing agent performance regressions"

## Workflow

- Reproduce the regression with fixed seeds/checkpoints and a stable benchmark command.
- Isolate whether loss comes from policy logic, config drift, or runtime/perf regressions.
- Apply the smallest fix that restores baseline metrics without hiding underlying instability.
- Re-run benchmark comparisons and summarize metric deltas versus baseline.
