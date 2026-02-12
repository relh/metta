# Initiative: Elide / Reduce Minibatch `.clone()` In PPO Training

## Context

Memory profiling shows minibatch sampling currently uses `.clone()`, which creates full copies proportional to minibatch
size. This contributes directly to peak memory during training.

See: `metta/rl/training/torch_profiler.py` (trace capture) and `metta/rl/training/experience.py` (minibatch sampling).

## Goal

Reduce peak memory and allocation churn during PPO training by avoiding unnecessary minibatch copies.

## Proposed Changes

- Audit why `.clone()` is needed (mutation safety). If training is read-only on rollout buffers:
  - Use views instead of clones; or
  - Clone only the fields that are mutated; or
  - Add a “read-only minibatch” contract and enforce it.
- If some losses mutate in-place, refactor them to avoid in-place writes.

Candidate code locations (to confirm):

- `metta/rl/training/experience.py` minibatch sampling (`sample_from_indices` / slicing path)
- Loss implementations that might write in-place

## Success Metrics

- Lower CUDA peak memory during the training phase when running a short Cogsguard job with torch profiler enabled:
  - `TORCH_PROFILER_FIRST_EPOCH=1 uv run ./tools/run.py train cogsguard run=perf_minibatch_clone torch_profiler.interval_epochs=1 torch_profiler.profile_dir=./profiler_output`
- Fewer allocations per minibatch (torch profiler / memory stats).

## Test Plan

- Add a regression test that asserts rollout buffers are unchanged by a training step.
- Compare memory peaks before/after on a mettabox.

## Risks / Notes

- Any in-place mutation on views can corrupt the rollout buffer and silently break training. This needs strong tests.
