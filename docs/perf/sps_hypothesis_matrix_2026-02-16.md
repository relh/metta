# SPS Hypothesis Matrix (2026-02-16)

This document is the deep-dive backlog for SPS work after auditing:

- existing perf docs in `docs/perf/*`
- end-to-end trainer hot paths
- trajectory isolation and experience sampling internals
- historical relh closed perf/wave2 branches already captured in `docs/perf/sps_audit_2026-02-15.md`

## Fresh Instrumentation Findings From This Pass

1. `scripts/cogsguard_microbench.py` could crash before run start because `TrainTool.apply_defaults_and_mutations()` was
   not called before `invoke()`.
   - Fixed in `scripts/cogsguard_microbench.py:256`.
2. Microbenching non-default vecenv geometries could fail due replay geometry mismatch
   (`trainer.batch_size // bptt_horizon != total_parallel_agents`).
   - Added automatic trainer batch/minibatch alignment in `scripts/cogsguard_microbench.py:181`.
3. Some `(num_workers, async_factor)` combinations are invalid for vecenv `batch_size` divisibility and currently fail
   at runtime.
   - Root interaction: `metta/rl/training/batch.py:6` and `packages/pufferlib-core/src/pufferlib/vector.py:730`.
   - This should become explicit preflight validation in microbench tooling.

## Bottleneck Recap (Current Evidence)

From prior end-to-end runs in `docs/perf/sps_audit_2026-02-15.md`:

- `_rollout.inference` + `_train` dominate total time.
- `_rollout.env_wait` is usually smaller than inference/train.
- Prior sync-path tweaks were noisy or topology-divergent across single 4090 vs 4-GPU host.

From code-path audit:

- Rollout does clone/split/stitch/writeback orchestration around policy forward (`metta/rl/training/core.py:453`,
  `metta/rl/training/core.py:546`, `metta/rl/training/core.py:554`).
- Trajectory isolation adds per-slice clones and per-policy cat/split (`metta/rl/training/trajectory_isolation.py:291`,
  `metta/rl/training/trajectory_isolation.py:649`, `metta/rl/training/trajectory_isolation.py:664`).
- Training loop does per-policy cat->forward->split every minibatch (`metta/rl/training/core.py:732`,
  `metta/rl/training/core.py:736`).
- Minibatch sampling clones sampled rows (`metta/rl/training/experience.py:429`).

## Hypotheses (30)

| ID  | Hypothesis                                                                 | Evidence                                                                                                                                                     | Status                          | Expected SPS Impact |
| --- | -------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------- | ------------------- |
| H01 | Reduce `_rollout.env_wait` via worker budget changes                       | Prior A/B: lower wait but higher inference share, net worse steady SPS (`docs/perf/sps_audit_2026-02-15.md`)                                                 | Rejected as primary             | Low/negative        |
| H02 | Disable `sync_traj` for throughput                                         | Runtime invariant break (`Ghost progression detected`) in replay contract                                                                                    | Rejected unless redesign        | High risk           |
| H03 | Distributed sync cadence tweaks can yield robust gains                     | Recent branch runs (`f87ff50694`, etc.) regressed/mixed across hosts                                                                                         | Rejected as robust path         | Low/negative        |
| H04 | Single-GPU-only sync behavior can win generally                            | Mixed: small single gain, multi regression (`d146614379`)                                                                                                    | Mixed                           | Low                 |
| H05 | Async-ready worker scheduling is universal win                             | Historical wave2 shows topology divergence                                                                                                                   | Mixed                           | Medium but unstable |
| H06 | Blocking worker notification is universal win                              | Historical wave2 mixed sign by host                                                                                                                          | Mixed                           | Medium but unstable |
| H07 | Double-buffered shm is universal win                                       | Historical wave2 mixed sign by host                                                                                                                          | Mixed                           | Medium but unstable |
| H08 | Gumbel-max action sampling materially improves SPS                         | Historical result negative both topologies                                                                                                                   | Rejected                        | Low/negative        |
| H09 | Pinned CPU action staging materially improves SPS                          | Historical result negative/flat                                                                                                                              | Rejected                        | Low                 |
| H10 | Fused tokenizer+shim observation path helps end-to-end SPS                 | Historical result negative                                                                                                                                   | Rejected for current setup      | Low/negative        |
| H11 | Batched step API in mettagrid improves training SPS                        | Historical result negative                                                                                                                                   | Rejected                        | Low/negative        |
| H12 | Mixed precision + checkpointing helps throughput robustly                  | Historical result regressed multi-GPU materially                                                                                                             | Rejected for default train path | Negative risk       |
| H13 | Minibatch clone elision has large upside                                   | Already merged; measured gain was small                                                                                                                      | Confirmed small                 | Low (+0-1%)         |
| H14 | Logging/W&B overhead is dominant                                           | `_process_stats` much smaller than rollout+train in current timing splits                                                                                    | Rejected as top priority        | Low                 |
| H15 | CPU->GPU transfer optimization is top driver                               | Existing profiles place transfer as small share in default PPO-only path                                                                                     | Rejected as top priority        | Low                 |
| H16 | Action send path sync is top driver                                        | `_rollout.send` tiny fraction in measured runs                                                                                                               | Rejected as top priority        | Low                 |
| H17 | Rollout per-slice clone-per-policy is a major avoidable cost               | Implemented via shallow clone + metadata reuse (`3fe0bce8be`), mixed topology outcome in parity run                                                          | Tested, mixed                   | Medium              |
| H18 | Rollout policy stitch/split (`torch.cat` + `split`) is excessive           | Implemented single-slice fast path + reduced stitch churn (`3fe0bce8be`), mixed topology outcome                                                             | Tested, mixed                   | Medium              |
| H19 | Rollout writeback path does extra pad/clone work                           | `_pad_slice_td_like` writeback path (`trajectory_isolation.py:679`)                                                                                          | Promising                       | Medium              |
| H20 | Training per-minibatch cat->forward->split loop is major overhead          | Single-slice fast path added in train loop (`31e63970a3`), short rs1 A/B nearly flat                                                                         | Tested, near-neutral            | Low/Medium          |
| H21 | Recomputing slice row indices (`torch.isin`) is avoidable overhead         | Slot-mask lookup + per-slice cache added (`974c8852bf`), short A/B mixed by host                                                                             | Tested, mixed                   | Medium              |
| H22 | Experience minibatch clone is still significant under larger models/slices | Subset-clone attempt (`148aa4d174` + `ab1840b5d8`) regressed short 4xL4 A/B                                                                                  | Tested, negative                | Low/negative        |
| H23 | Forced CUDA syncs inside training minibatch loop are throttling throughput | Sync fence removed/guarded (`d675deae29` path); strict 10-epoch parity on 4xL4 remained mixed by host (`rs1 -3.03%`, `rs3 +3.96%`)                           | Tested, mixed                   | Medium              |
| H24 | Rollout store path does redundant key filtering every step                 | Prefiltered store path triggered missing-key failure (`teacher_actions`) in rollout and was removed from active path                                         | Tested, blocked by invariants   | Medium              |
| H25 | Rollout writeback still pads/clones more than needed                       | Implemented cached direct-writeback fast path with pad fallback (`4918dd43aa`); 10-epoch pinned-SHA follow-up still mixed (`rs1 -5.56%`, `rs3 +4.02%` e2-10) | Tested, mixed                   | Medium              |
| H26 | Slice loss dispatch does repeated gate/key work per minibatch              | Per-loss gate checks + output-key collection in inner loop (`core.py:754-758`)                                                                               | New, untested                   | Low/Medium          |
| H27 | Advantage recompute path should be grouped by unique cfg                   | Per-slice `compute_advantage` call + scatter each update epoch (`core.py:664-687`)                                                                           | New, untested                   | Low/Medium          |
| H28 | Multi-slice train assembly still creates excess TensorDict metadata churn  | New `TensorDict` wrappers/metadata per slice minibatch (`experience.py:430-434`, `core.py:713-740`)                                                          | Benchmarked, positive           | Medium              |
| H29 | Training policy forward can run with selective mixed precision only        | Prior negative result bundled AMP + checkpointing (`#6900`); AMP-only path remains unisolated                                                                | New, untested                   | Medium              |
| H30 | Rollout/train phase decoupling could overlap compute and env progression   | Current trainer is phase-serial (rollout then train); no actor-learner queue                                                                                 | New, untested (macro)           | High (high effort)  |

## Highest-Likelihood Meaningful Change (Updated 2026-02-16 Late)

### Candidate: H23 + H24 (remove forced train-loop sync fences, then remove redundant rollout store filtering)

Why this is now top priority:

1. It is topology-agnostic and does not rely on async scheduling behavior.
2. It sits directly in hot loops that run every epoch:
   - with `batch_size=2,097,152` and `minibatch_size=16,384`, there are `128` minibatches/epoch
   - current single-GPU path can execute `128` explicit `torch.cuda.synchronize()` calls/epoch
   - with distributed world size > 1, sync still triggers periodically (`16` times/epoch at current cadence)
   - rollout currently does duplicate key filtering on every store call (about `512` calls/epoch at 4096-step recv
     groups)
3. Upstream `pufferl` training loop does not fence each optimizer step with explicit synchronize, suggesting this is a
   plausible avoidable stall in our loop.

Concrete implementation direction:

1. Add a guarded toggle for train-loop sync barriers (default off for CUDA perf runs, on for debugging if needed).
2. Benchmark strict parity on `metta4`, `relh-sandbox-1`, and `relh-sandbox-3` for 10 epochs (e2-10 deltas).
3. Remove duplicate store-key filtering by honoring pre-filtered rollout TDs and enforcing key invariants with tests.
4. Re-benchmark; if gain is still <3-5%, move to H25/H28 (writeback and train assembly churn).

## What Could Still Deliver 2x-Class Gains

Single micro-optimizations are unlikely to deliver 2x now. A 2x path probably needs a macro simplification stack:

1. Remove TensorDict orchestration churn in rollout+train (H17-H22 cluster).
2. Reduce observation encoder compute or token budget in ways that survive both topologies (not yet robustly achieved).
3. Consider tighter integration with fused pufferlib kernels for more of PPO math and action path (beyond current
   partial usage).

## Next Experiments (Ordered)

1. H25: simplify rollout writeback to avoid `_pad_slice_td_like` clone/pad work when output rows are shape-compatible.
2. H28: benchmarked positive via M01 (policy-centric minibatch assembly); keep iterating on further TensorDict churn.
3. H19: revisit rollout writeback path to remove extra clone-heavy transformations while preserving slice ownership.
4. H26: hoist per-loss gate/output-key selection out of inner minibatch loop where policy/loss structure is static.
5. H29: isolate AMP-only training/rollout forward (no checkpointing) behind explicit config gate and parity benchmark.
6. H30 (macro): design actor/learner decoupling sketch with replay invariants preserved, then evaluate feasibility.

## Measurement Protocol Reminder

Use strict branch-vs-main parity from `skills/tr.perf-eval/SKILL.md`:

- same machine
- same command shape
- same config
- fresh main SHA guard
- compare e2-10, not just epoch-1

## H17+H18 Parity Result (2026-02-16)

Code landed in `3fe0bce8be`:

- rollout prep uses `base_td.clone(recurse=False)` instead of deep clone
- reused sequence metadata helper in trajectory prep
- removed one temporary env-index tensor allocation
- single-slice fast path avoids unnecessary `cat/split`

10-epoch parity runs:

| Topology                 | Main run                                  | Branch run                           |             e1-10 mean SPS |    Delta |
| ------------------------ | ----------------------------------------- | ------------------------------------ | -------------------------: | -------: |
| `metta4` (1x4090)        | `perf_sps_main_h17h18_m4_10ep_20260216`   | `perf_sps_h17h18_m4_10ep_20260216`   | `156,497.9` -> `160,091.8` | `+2.30%` |
| `relh-sandbox-1` (4 GPU) | `perf_sps_main_h17h18_rs1_10epB_20260216` | `perf_sps_h17h18_rs1_10epB_20260216` | `204,916.5` -> `199,709.2` | `-2.54%` |

Conclusion: this H17+H18 implementation is not a robust cross-topology win, so it should not be the default path yet.

Reversed-order replication (branch-first, then main) on `relh-sandbox-1` and `relh-sandbox-3` reinforced that this
variant is still unstable:

- `rs1` e2-10: `+5.66%` branch vs main
- `rs3` e2-10: `-0.65%` branch vs main

Net: H17+H18 remains promising but not yet robustly reproducible across hosts/order.

Follow-on short A/Bs (3 epochs each, 4x L4) for H20/H21:

- H21-only delta (`353c4fe018` -> `974c8852bf`):
  - rs1 e2-3: `-2.25%`
  - rs3 e2-3: `+3.03%`
  - average hosts e2-3: `+0.34%` (mixed / near-noise)
- H20 incremental delta (`974c8852bf` -> `31e63970a3`):
  - rs1 e2-3: `-0.03%` (flat)

H22 follow-on (subset clone only required keys, then bug-fix for required keys):

- baseline commit: `82594830e6`
- candidate commits: `148aa4d174`, `ab1840b5d8`
- short 3-epoch results:
  - rs1 e2-3: `-0.87%`
  - rs3 e2-3: `-2.26%`
- average hosts e2-3: `-1.57%`
- outcome: reverted.

## H23 + H24 Implementation Outcome (2026-02-16 Night)

Code shipped:

- H23 sync-fence guard and default-off path: `d675deae29`
- H24 prefiltered store fast path implementation/fixes: `b2a29925f2`, `a03eb17935`

Observed behavior:

1. H24 in active rollout path failed fast with missing-key invariants (`teacher_actions` KeyError), confirming replay
   key-contract coupling is tighter than assumed for a simple prefiltered write path.
2. H24 was removed from the active rollout path for benchmark safety (`d675deae29` keeps H23 active only).
3. H23 strict 10-epoch parity (reversed order: branch first, then main) on 4xL4 hosts remained mixed:
   - `relh-sandbox-1`: branch e2-10 `54.51 ksps` vs main `56.22 ksps` => `-3.03%`
   - `relh-sandbox-3`: branch e2-10 `58.37 ksps` vs main `56.15 ksps` => `+3.96%`

Runs:

- branch rs1: `perf_sps_h23only_rs1_revorder_a_20260216`
- main rs1: `perf_sps_main_rs1_revorder_b_20260216`
- branch rs3: `perf_sps_h23only_rs3_revorder_a_20260216`
- main rs3: `perf_sps_main_rs3_revorder_b_20260216`

Conclusion: H23 is not a publishable cross-host win yet, and H24 needs invariant-safe redesign before reattempt.
