# Perf Benchmarking

> **Status:** In Review **Author:** Monica **Created:** 2026-02-18

## Workload phases

Performance changes can affect three distinct phases, each with different bottlenecks and measurement approaches:

- **Env-only** — C++ grid simulation without policy inference. Measures environment step throughput.
- **Training** — Full training loop (env step + policy inference + gradient update). Measures SPS.
- **Tournament** — Episode execution with trained policies (env step + inference, no training). Measures episode
  throughput.

## Summary

The training team built a rigorous perf methodology for training SPS work — strict parity benchmarking, reversed-order
replication, hypothesis tracking, profile-first investigation — documented across 13 files in `docs/perf/` and validated
across 20+ PRs in the wave2 optimization effort. This spec documents that methodology extended as the standard for all
perf work across all three workload phases, with a unified scorecard for cross-phase visibility
([`docs/perf/scorecard.md`](../perf/scorecard.md)) and a `/tr.perf-scorecard` skill to keep it current.

## What exists today

### Training methodology — the model for this spec

The training team built a rigorous perf methodology over the wave2 optimization effort, documented across 13 files in
`docs/perf/`. This methodology is what we're replicating for all phases:

| Practice                    | What it does                                                                                                      | Where it's documented                   |
| --------------------------- | ----------------------------------------------------------------------------------------------------------------- | --------------------------------------- |
| Strict parity benchmarking  | Branch freshness gates, machine exclusivity, config parity, warmup exclusion (e2-10)                              | `tr.perf-eval` skill                    |
| Reversed-order replication  | Rerun B→A after A→B to control for temporal effects; can flip observed sign                                       | `sps_audit_2026-02-15.md`               |
| Hypothesis matrix           | 30 hypotheses tracked from proposed → tested → confirmed/rejected with evidence                                   | `sps_hypothesis_matrix_2026-02-16.md`   |
| Macro interventions backlog | 15 interventions (M01-M15) with status tracking and strict parity results                                         | `sps_macro_interventions_2026-02-16.md` |
| Profile-first investigation | 11 profiling docs with reusable scripts (`tests/perf/profile_*.py`); eliminated non-bottlenecks before optimizing | `docs/perf/*.md`                        |
| Historical audit            | 24 closed wave2 PRs audited per-topology, revealing single/multi-GPU divergence pattern                           | `sps_audit_2026-02-15.md`               |
| Multi-topology testing      | Single-GPU (metta4, 1x4090) and multi-GPU DDP (4xL4 SkyPilot sandboxes)                                           | All `sps_*` docs                        |

### Env-only tooling

`packages/mettagrid/benchmarks/perf_optimization/` — standardized benchmark script (`test_perf.sh`), sweep configs, and
reference data. Used for #6895 and #7332. No formal protocol around when to run or how to report.

### Tournament

No protocol or tooling. Bottleneck now characterized (see Three-phase benchmark coverage below).

### Gap

The training methodology is mature, rigorous, and proven — but manual and training-scoped. Env-only has scripts but no
equivalent protocol. Tournament has nothing. The gaps are: extending the training methodology to all phases, and
automating the tracking that's currently done by hand.

## Problem

1. **Methodology is training-scoped** — The practices listed above exist only for training SPS. Env-only and tournament
   phases lack equivalent rigor. Cross-phase changes (e.g., C++ obs optimizations that affect both env-only and
   training) have no standard way to report impact across phases.

2. **No automation** — Benchmark scripts produce human-readable output but no machine-readable data. The hypothesis
   matrix, macro interventions backlog, and historical audit are maintained by hand in markdown files. Populating a
   scorecard requires manual transcription from PR descriptions and `docs/perf/` updates.

3. **N=1 measurements dominate** — Run-to-run variance is ~3.5-5% (see Statistical Grounding below). At N=1, effects
   under ~7-10% are indistinguishable from noise. Most merged training PRs report effects of +0.5% to +3.8%, well below
   the detection threshold. The reversed-order replication technique (already used in the training audit) demonstrated
   that run order can flip sign/magnitude at these effect sizes.

## Extensions

### 1. Three-phase benchmark coverage

Extend the training team's methodology (parity protocol, reversed-order replication, warmup exclusion, multi-topology
testing) to env-only and tournament phases:

| Phase      | Current state                                    | Extension                                               |
| ---------- | ------------------------------------------------ | ------------------------------------------------------- |
| Env-only   | Standardized script and configs (`test_perf.sh`) | Canonical multi-config benchmark, scorecard integration |
| Training   | `tr.perf-eval` (rigorous)                        | Add N>=3 recommendation, scorecard integration          |
| Tournament | No protocol                                      | Bottleneck characterized; GPU benchmark pending         |

The env-only benchmark (`packages/mettagrid/benchmarks/perf/perf_benchmark.py`) supports three canonical configs via
`--config`: `toy` (20 agents, move+noop, 40x40), `arena` (24 agents, combat), and `cogsguard` (8 agents, machina_1). Toy
is a fast sanity check; Arena and CogsGuard reflect production workloads where obs content and action complexity differ
significantly. Running all three configs catches optimizations that help one workload but regress another.

**Tournament phase detail:** Operational data from beta-cvc episodes (8 agents, 10K steps) shows inference is 87-98% of
step time (2.3ms/agent/step total, of which C++ env step is 0.029ms). All tournament agents across all seasons are
player-submitted neural policies, so GPU inference speedup applies to 100% of the inference workload. Prior to transport
batching (#7477), the WebSocket transport made one round-trip per agent per step (8 sequential calls for a 4v4 game).
Batching reduces this to one call per policy per step (2 calls), cutting communication overhead from 0.4-2.4ms to
0.1-0.6ms. Without batching, GPU at batch=1 is underwhelming for small models (~1-3x inference speedup, kernel launch
overhead dominates). Batching is the prerequisite for meaningful GPU speedup: batch=4 enables 5-20x inference speedup,
projecting episode time from 186s to 13-60s. A GPU inference benchmark (#7388) will measure actual speedup. See
`packages/cogames/experiments/ranking_correlation/gpu-tournaments.md` for the full analysis.

### 2. Unified scorecard

[`docs/perf/scorecard.md`](../perf/scorecard.md) — a single table extending the `sps_macro_interventions` results format
across all phases and all perf PRs, seeded with all wave2 data.

Status values: `significant`, `noise`, `regression`, `not run`, `divergence`.

`divergence`: single-GPU and multi-GPU effects have opposite signs (regardless of individual significance). The wave2
data shows this is a reliable signal — 5 PRs showing the same directional split is collectively significant even when
individual measurements are near the noise floor.

### 3. Experiment tracking via benchmark output

Benchmark scripts output scorecard-ready data and prompt the developer to record it:

1. Benchmark runs and prints human-readable results (as today)
2. Script prints a formatted scorecard row ready to paste
3. Script prints a reminder: `Update perf scorecard → /tr.perf-scorecard <results.json>`

The `/tr.perf-scorecard` skill (`skills/tr.perf-scorecard/`, usable by both Claude Code and Codex) reads the JSON
results file and appends to the scorecard. The developer chooses when to run it — no forced workflow change.

### 4. Statistical grounding

Observed run-to-run variance across wave2 PRs suggests sigma in the range of 3.5-5%:

- #6895 10-epoch: per-epoch deltas -5% to +14% (~19pp range)
- #6892 10-epoch: per-epoch deltas -6.3% to +13.5% (~20pp range)
- #7226 DDP: two "identical" sandbox machines measured -4.85% and -7.34% (2.5pp spread)

These ranges are approximate and conflate multiple variance sources (epoch-to-epoch, run-to-run, machine-to-machine). A
sigma of 3-5% is consistent with expected sources of non-determinism in GPU training: CUDA non-deterministic kernels,
memory allocator state, thermal throttling, and background OS activity.

The 95% CI for the mean of N independent runs is approximately +/-2sigma/sqrt(N). Because the true sigma is uncertain,
both ends of the estimated range are shown:

| N   | 95% CI (sigma=3.5%) | 95% CI (sigma=5%) | Detectable effect range |
| --- | ------------------- | ----------------- | ----------------------- |
| 1   | +/-7.0%             | +/-10.0%          | ~7-10%                  |
| 3   | +/-4.0%             | +/-5.8%           | ~4-6%                   |
| 5   | +/-3.1%             | +/-4.5%           | ~3-4.5%                 |
| 10  | +/-2.2%             | +/-3.2%           | ~2-3%                   |

Most merged training PRs report effects of +0.5% to +3.8% — below the N=1 detection threshold at either sigma estimate.
This doesn't mean the effects aren't real, but the data can't distinguish them from noise.

**Reversed-order replication:** The training audit (`sps_audit_2026-02-15.md`) demonstrated that running branch-first
then main can produce different deltas than main-first then branch — H17+H18 showed +5.66% on rs1 but -0.65% on rs3 in
reversed order, compared to +2.30% on metta4 and -2.54% on rs1 in original order. This technique should be standard for
any claim near the noise floor.

**Recommendation:** N>=3 for perf-claiming PRs (brings CI to +/-4-6%, enough to detect meaningful effects). Reversed-
order replication for any claim under ~5%. A dedicated variance baseline study — running main N=10 on a single machine
with identical parameters — would establish sigma directly and narrow the detection thresholds above.

### Single/multi-GPU tension

A consistent pattern across wave2: CPU-side speedups that help single-GPU training often regress multi-GPU DDP. Of 11
wave2 code PRs, 5 showed this divergence. The mechanism: DDP overlaps gradient allreduce with backward computation;
faster upstream stages can shift allreduce from hidden-behind-compute to the critical path.

`tr.perf-eval` already supports both topologies. The extension is making both configs expected for perf-claiming PRs
(with justification if omitted) and flagging `divergence` in the scorecard when effects have opposite signs.

## Goals

- [x] Env-only benchmark protocol — canonical multi-config benchmark (toy, arena, cogsguard) in
      `packages/mettagrid/benchmarks/perf/`
- [x] Scorecard format adopted, building on `sps_macro_interventions` pattern —
      [`docs/perf/scorecard.md`](../perf/scorecard.md)
- [x] `/tr.perf-scorecard` skill for both Claude Code and Codex — `skills/tr.perf-scorecard/`
- [ ] Benchmark scripts print scorecard rows + reminder
- [ ] N>=3 adopted as team norm for perf-claiming PRs

## Non-Goals

- Replacing `tr.perf-eval` or the existing training methodology (it's mature — we're extending it cross-phase)
- Fixing the DDP allreduce/backward overlap architecture
- Automated CI benchmark enforcement (future work — the scorecard establishes baselines that CI gates can compare
  against)
- Replacing the hypothesis matrix or macro interventions backlog (they work — we're adding automation on top)

---

## Appendix: Historical scorecard

The living scorecard is at [`docs/perf/scorecard.md`](../perf/scorecard.md), seeded with all wave2 data. It surfaces the
patterns discussed in this spec: most training claims are noise at N=1, DDP data is missing for most PRs, and 5 of 11
wave2 code PRs showed single/multi-GPU divergence.

## Open Questions

1. Should the variance baseline (N=10 main runs) be prioritized before adopting N>=3?
2. **Where is the research loop bottleneck — training or evaluation?** Operational data now confirms tournament episodes
   are inference-dominated (87-98% of step time). With transport batching (#7477) as a prerequisite, GPU inference could
   drop a beta-cvc season (405 episodes) from ~24 hours to 6-9 hours — with cost at or below CPU parity at >=5x
   inference speedup. Whether evaluation throughput is the binding constraint on research iteration — vs. training
   throughput or policy quality signal — is still an open team question.
