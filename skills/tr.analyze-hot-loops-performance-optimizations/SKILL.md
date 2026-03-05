---
name: tr.analyze-hot-loops-performance-optimizations
description: 'Use when analyzing hot loops performance optimizations.'
---

# Analyze Hot Loops Performance Optimizations

## Trigger

- Primary: "analyzing hot loops performance optimizations"

## Workflow

- Start from profiling data (SPS/CPU hotspots/flamegraphs) and identify the top step-loop bottlenecks.
- Separate algorithmic cost from incidental overhead (allocations, conversions, logging, indirection).
- Propose optimizations with expected impact and risk on determinism/correctness.
- Recommend a verification protocol: before/after benchmarks, seed controls, and pass/fail thresholds.
