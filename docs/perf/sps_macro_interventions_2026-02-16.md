# SPS Macro Interventions Backlog (2026-02-16)

This document tracks **macro** SPS interventions that are large enough to plausibly move end-to-end training throughput
by 1.2x-2x+ (or at least shift the dominant bottleneck), and are intended to be benchmarked with strict parity.

Status legend:

- `proposed`: idea only
- `in-progress`: being implemented
- `implemented`: landed behind a flag
- `benchmarked`: has parity numbers recorded
- `rejected`: measured negative or too risky

## M01-M15

1. **M01: Policy-centric minibatch assembly (H28)** (`benchmarked`)
   - Goal: eliminate per-slice `sampled_mb` cloning + per-policy `cat/split` by sampling indices per slice, cloning once
     per policy, then slicing via offsets.
   - Touches: `metta/rl/training/core.py`, `metta/rl/training/experience.py`, `metta/rl/trainer_config.py`.
   - Strict parity results (10 epochs):
     - Main SHA: `d697b05de6`
     - Branch SHA: `9e1a25e3c4`
     - Metric:
       - 4xL4 sandboxes: e2-10 mean `ksps` from epoch logs
       - `metta4` (1x4090): stopwatch `trainer_state.pt` average SPS (no epoch `ksps` log lines)

     | Topology                | Baseline run                           | Branch run                               |                 e2-10 / avg SPS delta |
     | ----------------------- | -------------------------------------- | ---------------------------------------- | ------------------------------------: |
     | `relh-sandbox-1` (4xL4) | `perf_sps_m01_main_rs1_10epB_20260216` | `perf_sps_m01_branch_rs1_10epB_20260216` | `+12.07%` (53.05 -> 59.46 ksps e2-10) |
     | `relh-sandbox-3` (4xL4) | `perf_sps_m01_main_rs3_10epB_20260216` | `perf_sps_m01_branch_rs3_10epB_20260216` |  `+8.88%` (52.03 -> 56.66 ksps e2-10) |
     | `metta4` (1x4090)       | `perf_sps_m01_main_m4_10epB_20260216`  | `perf_sps_m01_branch_m4_10epB_20260216`  |  `+1.35%` (154.45 -> 156.53 ksps avg) |

2. **M02: Rollout/train actor-learner decoupling** (`proposed`)
   - Goal: overlap environment stepping + policy inference with gradient updates via an explicit queue (ring buffer).
   - Touches: rollout loop, replay semantics, backpressure, checkpointing.
   - Risk: correctness invariants (row ownership / ghost progression).

3. **M03: Replace TensorDict-heavy hot paths with structure-of-arrays minibatch views** (`proposed`)
   - Goal: convert training data plumbing to plain tensors (dict-of-tensors) and keep TensorDict only at boundaries.
   - Touches: all losses (expected large refactor).

4. **M04: Preallocate and reuse stitched workspaces (rollout + train)** (`proposed`)
   - Goal: avoid repeated `torch.cat` allocations by writing into a preallocated contiguous buffer per policy and using
     offsets for views.
   - Touches: `trajectory_isolation.py`, `core.py`.

5. **M05: Fused PPO loss kernels / vectorized per-policy loss evaluation** (`proposed`)
   - Goal: reduce Python overhead by fusing commonly used loss computations across minibatches/slices.
   - Touches: PPO losses, loss dispatch, stats.

6. **M06: Torch compile the policy forward + loss step with stable shapes** (`proposed`)
   - Goal: use `torch.compile` effectively by stabilizing shapes (M01 helps), reducing dynamo breaks from TensorDict
     churn.
   - Touches: compile gates, policy forward wrappers, loss wrappers.

7. **M07: Eliminate per-minibatch per-slice gate bookkeeping (hoist/static)** (`proposed`)
   - Goal: precompute which losses are active for each slice + which policy output keys are needed and reuse for the
     entire epoch.
   - Touches: `core.py` inner loops, loss APIs.

8. **M08: Advantage compute deduplication across slices** (`proposed`)
   - Goal: group slices by identical advantage config and compute in larger batches (fewer kernel launches / Python
     overhead).
   - Touches: advantage compute loop in `core.py`.

9. **M09: Experience store path becomes “columnar” and in-place** (`proposed`)
   - Goal: write into replay buffer columns directly with precomputed index maps; avoid TensorDict select/copy logic.
   - Touches: `experience.py`, rollout writeback, required store keys invariants.

10. **M10: Reduce rollout slice TensorDict churn** (`proposed`)

- Goal: reduce/avoid per-step `TensorDict({}, ...)` allocations when preparing per-slice/per-policy views.
- Touches: `trajectory_isolation.py`, rollout prep.

11. **M11: Multi-slice training “single forward, multi-head” unification** (`proposed`)

- Goal: if multiple policies share architecture, batch them together (policy-id embedding) to reduce separate forward
  calls.
- Touches: model architecture + policy registry; high scope.

12. **M12: Make W&B and stats collection fully asynchronous/off hot path** (`proposed`)

- Goal: isolate logging/stat aggregation to a background thread/process with bounded queues.
- Touches: progress logging, stats, wandb integration.

13. **M13: Replace Python control loops in rollout with TorchScript/compiled loop** (`proposed`)

- Goal: shrink Python overhead per step by moving the tightest loop into compiled code.
- Touches: rollout orchestration; high risk.

14. **M14: Change vecenv transport to avoid pickling / reduce memcpy (SHM ring)** (`proposed`)

- Goal: closer to pufferlib-style high SPS by minimizing IPC overhead for obs/actions.
- Touches: vecenv backend; high scope.

15. **M15: Evaluate turning off trajectory isolation when single-slice** (`proposed`)

- Goal: bypass the entire slicing apparatus in the common case (single slice) while preserving multi-slice behavior.
- Touches: trajectory isolator callsites; requires careful invariants and tests.
