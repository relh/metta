# PufferLib 4.0 Performance Port Plan

> **Status:** Draft **Author:** relh + Codex **Created:** 2026-02-08

## Summary

PufferLib’s 4.0 branch (vs 3.0) is a performance-focused overhaul that pushes the PPO inner loop, environment
vectorization, and GPU execution model toward "static", graph-capturable, low-kernel-count execution. This doc records
the most important 3.0 -> 4.0 upgrades (with an emphasis on steps-per-second) and proposes a concrete plan to port the
highest ROI ideas into Metta’s RL training stack.

Scope here is deliberately biased toward throughput and predictable latency in the _training hot path_.

## Context

In this repo, we currently:

- Use PufferLib’s `pufferlib.vector` API for vectorization (serial or multiprocessing) via `metta/rl/vecenv.py`.
- Use a componentized trainer (TensorDict-based) with per-loss modularity (`metta/rl/training/*`, `metta/rl/loss/*`).
- Already depend on a small but important PufferLib extension: the advantage kernel
  (`torch.ops.pufferlib.compute_puff_advantage`) via `metta/rl/advantage.py`.

PufferLib 4.0 moves far beyond "an advantage kernel": it introduces a native C++/CUDA PPO engine, static env bindings,
CUDA-graph capture discipline, and fused kernels for sampling and loss computation.

This doc is written to support:

1. A measurable baseline (microbench).
2. A prioritized porting plan.
3. A shared vocabulary for discussing perf work.

## Executive Takeaways

1. PufferLib 4.0’s biggest perf wins come from reducing Python scheduling overhead and reducing GPU kernel launches.
2. CUDA graphs only help if tensor pointers, streams, and scalar inputs are stable. 4.0 spends real engineering effort
   on capture correctness; we should treat that as a first-class feature, not a toggle.
3. The "static" story is end-to-end: pinned host buffers, stable device buffers, fused kernels, contiguous weights, and
   a training loop implemented in native code. Porting individual pieces (fused kernels) helps, but the compounding
   effect comes from treating the entire step as a pipeline.

## What Changed (3.0 -> 4.0)

PufferLib 3.0 (branch `3.0`) is broadly:

- Python-driven training orchestration with some C++/CUDA extensions for advantage.
- Traditional PyTorch compute graphs for policy forward and PPO loss.
- Vectorization primarily via Python backends (`pufferlib.vector.Serial`, `pufferlib.vector.Multiprocessing`).

PufferLib 4.0 (branch `4.0`) adds:

- A C++ backend that can run rollouts and training with minimal Python overhead.
- A static vectorized environment interface with pinned host buffers and mirrored GPU buffers.
- CUDA graph capture and a codebase designed around capture invariants.
- Fused kernels for recurrent scanning (MinGRU), PPO loss, and action sampling.
- Multi-GPU plumbing (NCCL) and profiler tooling.

### ~10 Meaningful Upgrades (perf-biased)

These are the items that appear most load-bearing for SPS improvements, based on the 4.0 history and code structure.

1. **Native PPO Engine (C++ `PuffeRL` backend)**
   - `pufferlib/extensions/bindings.cpp`, `pufferlib/extensions/pufferlib.cpp`
   - Python becomes a thin wrapper around `_C.rollouts()` / `_C.train()`.
   - Enables "static shapes" assumptions that make CUDA graphs and fused kernels worthwhile.

2. **Static VecEnv with pinned host buffers and GPU mirrors**
   - `pufferlib/extensions/env_binding.c`, `pufferlib/extensions/env_binding.h`, `pufferlib/extensions/vecenv.h`
   - Uses `cudaHostAlloc` for observations/actions/rewards/terminals buffers and `cudaMalloc` for device copies.
   - Sets up per-buffer streams and buffer partitioning across env instances.
   - Goal: avoid per-step allocation and make H2D/D2H predictable.

3. **CUDA graphs become a design constraint, not an optional feature**
   - `pufferlib/extensions/pufferlib.cpp` uses `at::cuda::CUDAGraph` and graph pools.
   - Includes an explicit "capture correctness checklist" and careful stream handling.
   - Important implementation detail: do warmup + capture before creating extra streams/threads to avoid baking
     cross-stream dependencies into graphs.

4. **Fused PPO loss kernel**
   - `pufferlib/extensions/modules.h`, `pufferlib/extensions/modules.cu`, `pufferlib/extensions/cuda/kernels.cu`
   - Consolidates multiple PPO sub-ops (ratio/clipping, value clipping, entropy) into a small number of kernels.
   - Explicit support for MultiDiscrete action spaces and strided logits (to avoid `.contiguous()` costs).

5. **Fused action sampling kernel (discrete + continuous)**
   - `pufferlib/extensions/cuda/kernels.cu` (`sample_logits_kernel`)
   - Fuses `nan_to_num`, `log_softmax`, sampling, logprob gather, value copy, RNG offset bump.
   - Graph-safe RNG: offset is read via pointer at execution time, not captured by value.

6. **Fused recurrent kernels (MinGRU gate + checkpointed scan)**
   - `pufferlib/extensions/models.cpp`, `pufferlib/extensions/modules.h`, `pufferlib/extensions/cuda/kernels.cu`
   - Kernel count and memory bandwidth are the main target. Uses sparse checkpointing to reduce activation storage and
     backward cost.

7. **Static precision compilation**
   - `pufferlib/extensions/pufferlib.cpp`, `pufferlib/extensions/cuda/kernels.cu`
   - bf16 vs fp32 is chosen at compile time (`PRECISION_FLOAT`) rather than runtime dispatch.
   - This is a classic "remove dynamic overhead in the hot path" move.

8. **Contiguous weight buffers + native optimizer plumbing**
   - `pufferlib/extensions/muon.cpp`, `pufferlib/extensions/muon.h`
   - Explicit contiguous weight buffer ("master weights") is used for optimizer updates and syncing.
   - Avoids per-parameter overhead and improves memory locality.

9. **Multi-GPU integrated into the native backend**
   - `pufferlib/extensions/pufferlib.cpp` includes NCCL setup and rank/world size handling.
   - This is important if we ever chase multi-GPU SPS and want to avoid Python overhead per-rank.

10. **First-class profiling workflow**

- NVTX and dedicated profiling scripts (`profile_kernels.cu`, `profile_nvtx.sh`, `profile_torch.py`, etc.)
- The repo is set up to answer questions like:
  - how many kernels per step?
  - which kernels are dominating?
  - did a change make graph capture unstable?

## How This Maps To Metta

Metta is not PufferLib. We have:

- A flexible component system (loss composition, trajectory isolation, teacher phases).
- MettaGrid environments with a PufferEnv wrapper
  (`packages/mettagrid/python/src/mettagrid/envs/mettagrid_puffer_env.py`) designed for zero-copy behavior and stable
  buffers.

That said, the fundamental bottlenecks are universal:

- Python overhead in the rollout loop.
- Excessive tensor allocations / `.cpu().numpy()` conversions.
- Too many GPU kernel launches in PPO.
- Instability that blocks CUDA graph capture.

The key question is not "port PufferLib 4.0 wholesale" but "port the invariants and the highest ROI building blocks".

## Proposed Porting Strategy (Phased)

### Phase 0: Baseline and Guardrails (microbench first)

Goal: A repeatable benchmark harness for Cogsguard training that produces:

- SPS (agent steps/sec)
- Timing breakdown:
  - `_rollout.env_wait`
  - `_rollout.td_prep`
  - `_rollout.inference`
  - `_rollout.send`
  - `_train`
  - `_process_stats`
- Configuration snapshot
- Output JSON artifact for comparisons across commits/branches.

Deliverable:

- A single command to run locally on a representative machine and produce an artifact suitable for diffing.

Current microbench entrypoint:

```bash
uv run scripts/cogsguard_microbench.py --total-timesteps 1000000 --vectorization multiprocessing --num-workers 1
```

Artifacts:

- `train_dir/<run>/microbench.json`: per-epoch records + summary (after warmup)
- `train_dir/<run>/microbench_config.json`: full resolved tool config snapshot

Optional: capture a `torch.profiler` trace (compressed chrome trace):

```bash
uv run scripts/cogsguard_microbench.py --torch-profiler --torch-profiler-first-epoch 1
```

Optional: enable `torch.compile` (useful for comparisons, but can dominate short microbench runs):

```bash
uv run scripts/cogsguard_microbench.py --compile --compile-mode reduce-overhead
```

### Baseline Results (metta1)

Recorded on **2026-02-09** on `metta1` (RTX 4090, NVIDIA driver `570.153.02`) at repo commit `a14c5d6776`.

Cogsguard microbench (GPU):

- Run id: `microbench-cogsguard-puffer40-20260209-222544`
- Artifact: `/workspace/metta/train_dir/microbench-cogsguard-puffer40-20260209-222544/microbench.json`
- Config: warmup_epochs=1, total_timesteps=12,000,000, vectorization=multiprocessing, num_workers=2, async_factor=2,
  forward_pass_minibatch_target_size=4096, zero_copy=True, update_epochs=1.
- Summary (warmup excluded; samples=5):
  - `sps_mean`: 56,157
  - `sps_median`: 56,800
  - `sps_p10`: 54,215
  - `sps_p90`: 57,693

#### Rollout Bottleneck + Run-To-Run Variance

On `metta1`, we observed that short microbench runs can vary by a few percent even at the same git head, and the
variance is dominated by `_rollout.env_wait` (time spent inside `env.get_observations()`), not model inference.

Example (same code path; warmup excluded; `num_workers=2`, `async_factor=2`, `forward_pass_minibatch_target_size=4096`):

- Run `microbench-cogsguard-opregs-20260209-175245`: `sps_mean=56,376`
  - `rollout_env_wait_time_mean=9.180s`, `rollout_inference_time_mean=9.619s`
- Run `microbench-cogsguard-opregs-20260209-182028`: `sps_mean=53,847` (−4.5%)
  - `rollout_env_wait_time_mean=10.513s`, `rollout_inference_time_mean=9.704s`

Interpretation:

- The "regression" here is largely worker wait/scheduling noise (head-of-line blocking in the vecenv recv path can
  amplify this), so we should avoid drawing conclusions from a single run.
- The highest ROI near-term work is reducing `_rollout.env_wait` (faster env stepping and/or better overlap), not
  porting additional fused CUDA kernels that our current training loop does not call.

Practical note:

- Disabling `sync_traj` (`--no-sync-traj`) is currently not viable for Cogsguard training: it violates trainer
  invariants about `agent_slot_ids` staying constant across timesteps within a sequence.

#### Worker Tuning Can Eliminate Env Wait

Keeping `sync_traj=True`, increasing `num_workers` reduces per-worker env load and can dramatically cut env wait time.
In one run on `metta1` (same `forward_pass_minibatch_target_size=4096` and `async_factor=2`):

- `num_workers=2`: `sps_mean=53,119`, `rollout_env_wait_time_mean=10.704s`
- `num_workers=4`: `sps_mean=65,280`, `rollout_env_wait_time_mean=3.476s`

This suggests the throughput ceiling in this configuration is not GPU compute; it's the env worker pipeline keeping up
with the rollout loop.

#### Options To Reduce Remaining Hot-Path Time

After cutting env wait, the remaining major rollout costs are model inference and training compute. Practical next
options (in increasing implementation cost):

1. Tune `num_workers` per host and keep `sync_traj=True` for correctness (the main win we measured above).
2. Increase `async_factor` to improve overlap, but ensure `trainer.batch_size` is large enough for the resulting
   `total_agents` and `bptt_horizon` (otherwise Experience initialization fails).
3. Longer term: port PufferLib 4.0’s pinned-buffer + GPU-mirror ideas at the env boundary to make H2D/D2H predictable
   and overlap-friendly, and consider wiring the fused sampling/PPO-loss kernels into Metta’s PPO loss path so they can
   actually reduce `rollout_inference_time` / `train_time`.

#### Stable GPU Transfer Buffers (in-branch)

On `richard-40-puffer`, we implemented a first "4.0-style" invariant: **stable GPU transfer buffers** for vecenv
outputs, plus a dedicated H2D CUDA stream (copy on a side stream; `wait_stream` before inference). This reduces
per-epoch device allocations in the rollout hot path and is a prerequisite for deeper graph-capture work.

Latest microbench on `metta1`:

- Run id: `microbench-cogsguard-w16-sync_on-20260210-201350`
- Commit: `9fe6fe053a`
- Config: warmup_epochs=2, total_timesteps=10,000,000, vectorization=multiprocessing, num_workers=16, async_factor=2,
  forward_pass_minibatch_target_size=4096, zero_copy=True, sync_traj=True, update_epochs=1.
- Summary (warmup excluded; samples=3):
  - `sps_mean`: 68,743
  - `rollout_env_wait_time_mean`: 0.814s
  - `rollout_td_prep_time_mean`: 0.267s
  - `rollout_inference_time_mean`: 10.792s
  - `train_time_mean`: 17.769s

Interpretation:

- With enough workers, `_rollout.env_wait` is no longer the bottleneck on `metta1`; compute dominates.
- Stable GPU buffers are a hygiene improvement and likely help tail latency, but they are not sufficient (alone) to move
  SPS materially in this regime.

#### Failed Attempt: Reusing a Rollout TensorDict Buffer

We tried to reuse a persistent rollout `TensorDict` across timesteps to avoid per-step clones/allocations, but that
violated Cogsguard trainer invariants and caused training to fail with:

- `ValueError: agent_slot_ids must stay constant across timesteps within each sequence`

This was reverted. The likely root cause is that experience storage assumes per-timestep tensors are not mutated after
enqueue; reusing a single `TensorDict` object makes it too easy to overwrite `agent_slot_ids` (and/or other fields)
in-place across timesteps.

### MettaGrid Step Profiling (Monica Instrumentation)

MettaGrid now exposes per-phase nanosecond step timings behind `METTAGRID_PROFILING=1` (see
`packages/mettagrid/benchmarks/perf_optimization/`). The quickest way to identify the dominant C++ phase for a given
game config is:

```bash
uv run python packages/mettagrid/benchmarks/perf_optimization/scripts/profile_multi_config.py
```

This profiles three configs (Toy, Arena, CogsGuard) and prints per-phase mean microseconds and % of C++ time.

#### Results (metta1, inside docker)

Recorded on **2026-02-10** on `metta1` at repo commit `6731b74121`.

Baseline (original observations path; `METTAGRID_OBS_USE_OPTIMIZED` unset):

- Toy: `Agent SPS=753,567`, observations `15.09us` (89.9% of C++)
- Arena (combat=True): `Agent SPS=702,882`, observations `21.35us` (90.4% of C++)
- CogsGuard (machina_1): `Agent SPS=256,053`, observations `12.36us` (52.7% of C++), aoe `6.94us` (29.6%)

Optimized observations primary (`METTAGRID_OBS_USE_OPTIMIZED=1`):

- Toy: `Agent SPS=1,176,409`, observations `5.57us` (77.2% of C++)
- Arena (combat=True): `Agent SPS=1,099,574`, observations `8.83us` (81.0% of C++)
- CogsGuard (machina_1): `Agent SPS=314,041`, observations `6.70us` (37.7% of C++), aoe `5.81us` (32.7%)

Interpretation:

- In simpler configs (Toy/Arena), observations dominate step time; the optimized path is a large win.
- In CogsGuard, observations and AOE are both significant; after optimizing observations, AOE becomes the dominant phase
  (~33%).

#### Effect On Training Microbench (Cogsguard)

Even large MettaGrid C++ step wins translate to smaller end-to-end training SPS changes because policy inference and PPO
training dominate epoch wall time in our current stack.

On `metta1` at commit `6731b74121` (`num_workers=16`, `async_factor=2`, `sync_traj=True`, `total_timesteps=10M`,
warmup_epochs=2):

- `METTAGRID_OBS_USE_OPTIMIZED=0`: `sps_mean=66,400`
- `METTAGRID_OBS_USE_OPTIMIZED=1`: `sps_mean=68,339` (+2.9%)

MettaGrid perf benchmark (CPU):

- Command:
  `uv run python packages/mettagrid/perf_benchmark.py --agents 20 --map-size 40 --iterations 5000 --rounds 10 --warmup 20000`
- Results:
  - Env SPS: 41,622 ± 348
  - Agent SPS: 832,439 ± 6,952
- Stability: Excellent (CV < 5%).

### Phase 1: Remove obvious Python overhead in the rollout hot path

Targets:

- Avoid per-step `TensorDict.clone()` patterns if possible.
- Avoid per-step `.cpu().numpy()` allocations on actions (re-use staging buffers).
- Reduce per-step overhead in env id handling (slices vs index tensors).

Success criteria:

- Measured SPS improvement in microbench without behavior change.

### Phase 2: Adopt pinned staging buffers at the env boundary

Targets:

- Introduce pinned host buffers for observation and action staging to reduce transfer overhead and allow overlap.
- Keep buffer pointers stable across epochs to prepare for graph capture.

Success criteria:

- Reduced rollout time fraction and/or higher SPS on CUDA runs.

### Phase 3: Fused kernels for sampling and PPO loss (fast path)

Targets:

- Add optional fused CUDA kernels (sampling, PPO loss).
- Keep correctness strict: update every callsite, no backcompat.
- Restrict to the default PPO configuration first (single discrete action) and widen later.

Success criteria:

- Reduced kernel count in Nsight Systems.
- SPS gain measured in microbench.

### Phase 4: CUDA graph capture for training step (and optionally inference)

Targets:

- Stabilize tensor lifetimes, pointers, and stream usage so graphs capture reliably.
- Capture the training step graph for the "common case" config.

Success criteria:

- Graph capture works reliably in microbench with stable SPS and no correctness regressions.

## Non-Goals (for initial port)

- Replacing Metta’s trainer architecture with a monolithic C++ engine.
- Multi-GPU performance work (until single-GPU baseline is stable and measurable).
- Large refactors to the environment API.

## Open Questions

1. Should we treat "fast PPO path" as an alternate trainer (explicit) or as a set of optional kernels behind the
   existing trainer?
2. What hardware should be our primary benchmark target (A100, H100, 4090, etc.)?
3. Do we want a "kernel budget" target per epoch/step (as a metric in the microbench artifact)?
