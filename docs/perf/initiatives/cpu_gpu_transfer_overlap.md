# Initiative: Overlap CPU→GPU Transfers With Compute

## Context

Even with `non_blocking=True`, CPU→GPU transfers can still show up as visible wall time if they are not effectively
overlapped with other GPU work (or if other synchronization points collapse concurrency).

See: `docs/perf/cpu_gpu_transfer_profile.md`.

## Goal

Hide transfer latency by overlapping data staging with inference/compute, reducing rollout wall time without changing
training behavior.

## Proposed Changes

- Audit the rollout loop for synchronization points that force transfers onto the critical path.
- If appropriate, move transfer staging onto a dedicated CUDA stream:
  - Record events on the transfer stream.
  - Ensure the compute stream waits only when tensors are actually needed.
- Confirm the upstream CPU tensors are pinned where possible (stream overlap won’t help if transfers aren’t async).

Candidate code locations (to confirm):

- `metta/rl/training/core.py` (rollout loop boundaries: td_prep / inference)

## Success Metrics

- Stopwatch: `_rollout.td_prep` decreases in wall time and/or overlaps with `_rollout.inference`.
- Improved SPS on dedicated GPU runs where transfers are measurable.

## Test Plan

- Baseline: profile cogsguard training with stopwatch and (optionally) torch profiler.
- Change: re-run and compare wall times; verify correctness (no race/sync bugs).

## Risks / Notes

- Incorrect stream/event usage can introduce subtle race conditions; require careful synchronization and testing.
- If the loop already synchronizes frequently (e.g. action send), overlap gains may be limited.
