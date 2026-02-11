# Initiative: Reduce GPU→CPU Action Send Synchronization

## Context

The rollout loop typically includes a GPU→CPU action handoff (e.g. `actions.cpu().numpy()`), which can introduce a
blocking synchronization point. Even if the transfer itself is small, the sync can prevent overlap and increase
rollout-phase wall time.

See: `docs/perf/cpu_gpu_transfer_profile.md` (notes GPU→CPU transfer as a blocking point).

## Goal

Reduce rollout wall time by minimizing explicit synchronization on the action send path, ideally enabling overlap with
other work.

## Proposed Changes

- Audit the action send path in the rollout loop and identify sync points (likely a `.cpu()` + `.numpy()` conversion).
- If possible, replace with:
  - Pinned staging buffers for GPU→CPU transfers; and/or
  - A handoff mechanism that avoids forcing a full-device sync each step; and/or
  - Batching actions for transfer if latency constraints allow.

Candidate code locations (to confirm):

- `metta/rl/training/core.py` (rollout loop send phase)
- Vecenv / env interface that consumes actions

## Success Metrics

- Stopwatch: `_rollout.send` decreases and/or becomes a smaller fraction of rollout.
- Improved SPS for configs where `_rollout.send` is measurable.

## Test Plan

- Profile baseline on a dedicated mettabox GPU and capture stopwatch breakdown.
- Apply the change and compare `_rollout.send` and overall SPS.

## Risks / Notes

- Some env interfaces may require numpy arrays; avoid introducing extra copies.
- Batching actions trades latency for throughput; ensure it doesn’t break training dynamics if timing-sensitive.
