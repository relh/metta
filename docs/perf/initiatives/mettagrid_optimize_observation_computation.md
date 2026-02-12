# Initiative: Optimize MettagGrid Observation Computation (C++)

## Context

Mettabox profiling shows the C++ `step()` time is dominated by the observation phase (measured ~83–89% across 8/16/32
agents). This is the primary “real work” hotspot in the simulator.

See: `docs/perf/mettagrid_pybind_profile.md`.

## Goal

Reduce C++ time spent in observation computation, improving env SPS directly (independent of Python overhead).

## Proposed Changes (Candidates)

- **Avoid full recomputation**: incremental/cached observation windows when the world changes sparsely per tick.
- **Memory/layout**: tighten data structures used by the encoder to improve cache locality.
- **Reduce branching** in the inner loops; consider precomputed tables for tokenization/encoding.
- **Vectorization**: SIMD-accelerate token packing/feature encoding if the loop structure supports it.
- **Parallelization** inside observation computation if safe (likely a larger change).

Candidate code locations (to confirm):

- C++ observation computation in `packages/mettagrid/cpp/bindings/mettagrid_c.cpp` and related encoder code.

## Success Metrics

- `METTAGRID_PROFILING=1` phase breakdown shows reduced `observations` time and reduced total C++ step time.
- Higher env SPS / agent SPS in `tests/perf/profile_mettagrid_pybind.py` for 8/16/32 agent configs.

## Results

**metta3 (RTX 4090), 2026-02-11, Cogsguard train throughput**

- `origin/main` @ `91e783f708`: **49.96 ksps** (run `perf_mg_obs_main_0211`)
- This PR @ `a3e5c58472`: **50.02 ksps** (run `perf_mg_obs_opt_0211`)
- Delta: **+0.1%** (within noise)

## Test Plan

- Baseline/after comparisons on a mettabox with `METTAGRID_PROFILING=1`.
- Add a microbench/regression guard that tracks observation time for a stable config (with a loose threshold).

## Risks / Notes

- Correctness risk: observation semantics are easy to subtly change; add focused tests for encoding correctness.
- Some optimizations (incremental caching) may depend heavily on how often the world changes per step.
