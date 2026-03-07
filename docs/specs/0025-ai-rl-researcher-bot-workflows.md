# AI RL Researcher Bot Workflows

> **Status:** Implemented (final branch version) **Author:** Richard + Codex **Created:** 2026-02-12

## Summary

Define and ship two runnable AI researcher workflows, `startup` and `resume`, that execute the real submission loop
end-to-end for CoGames/CogsGuard while producing durable diagnosis artifacts. The workflows compare current behavior
against an explicit optimal researcher baseline and prioritize leaderboard gains without regressing reliability or
usability.

## Problem

Researchers can run individual CLI steps today, but the end-to-end loop is not yet systematized as a resilient,
artifact-backed researcher workflow. This creates downtime, inconsistent submit coverage across variants, and slow
root-cause diagnosis when rank/regression changes occur.

## Solution

Implement a reaper-supervised actor/critic researcher loop with two entrypoints:

- `startup`: Claude-centric from-scratch flow with explicit setup/auth requirements.
- `resume`: Claude-centric continuation flow from existing context with ranked next actions.
- `swarm` (optional mode): multi-agent worker fan-out coordinated by Claude, used when broader experiment search or
  faster triage is beneficial.

Implementation home for this system is a dedicated meta-agent package: `cogames-rl-researcher`.

Additional sprint services in the same package:

- `research` command: single orchestration entrypoint that can run training, startup, and resume in sequence.
- `log mining` service: mines gastown/claude/codex `cogames` command failures into durable diagnosis artifacts.
- `defect intake` service: accepts crash reports from any researcher and maintains a ranked backlog.

Both entrypoints run the same optimal baseline submission loop:

1. login/auth check
2. scrimmage/eval with `--format json` and `--save-replay-dir`
3. dry-run upload validation
4. upload
5. submit to season
6. leaderboard check
7. regression diagnosis + next experiment proposal

## Goals

- [ ] Startup and resume workflows complete the full submission loop without undocumented manual fixes.
- [ ] Single-agent Claude flow is the default path and requires no swarm setup.
- [ ] Reaper catches downtime before humans do and attempts automated recovery.
- [ ] Submit coverage increases across experiment variants over repeated runs.
- [ ] Swarm mode remains optional and can be enabled without changing artifact/report contracts.
- [ ] Actor/critic loop records rationale and outcomes for each change.
- [ ] Daily report + audit bundle are reproducible and shareable.
- [ ] Experienced and Neophyte profiles are both supported and evaluable.
- [ ] Log-mining artifacts capture failed `cogames` attempts from gastown/claude/codex traces.
- [ ] Crash defect intake/backlog flow is available to all researchers.

## Capability Profiles

### Experienced

- Can modify code and defaults.
- Can run profiling.
- Can tune train/eval/submission loops quickly.
- Optimizes for performance and leaderboard gains.

### Neophyte

- Restricted to documented happy-path workflows.
- Must log every friction point as a concrete fix candidate.
- Optimizes for usability quality and workflow robustness.

## Optimal Researcher Baseline (Comparison Target)

Comparison target is process quality, reliability, and outcomes, not model identity.

Required baseline chain:

1. login/auth check
2. scrimmage/eval (`--format json`, `--save-replay-dir`)
3. upload validation (`--dry-run` or equivalent validator)
4. upload
5. submit to target season
6. leaderboard check
7. diagnosis and next proposal

## Reaper + Actor/Critic Architecture

### Reaper Responsibilities

- Detect stalled progress, repeated command failures, auth expiry, and long idle windows.
- Trigger retry/recovery policy and keep the run moving.
- Escalate when automated recovery repeatedly fails.
- Log incidents directly into daily report + audit bundle.

### Reaper SLOs

- Detect idle/stall within 10 minutes.
- Attempt automated recovery within 5 minutes.
- Escalate after 2 consecutive failed recoveries.

### Recovery Example

- Scrimmage fails due to expired auth.
- Reaper refreshes auth, reruns scrimmage, and logs incident details.

### Actor Responsibilities

- Propose the next experiment/submission candidate.
- State explicit hypothesis and intended metric impact.

### Critic Responsibilities

- Consume artifacts (JSON evals, replays, logs, optional profiler traces).
- Produce ranked bottleneck list and concrete next fixes.
- Recommend keep/revert based on measured deltas.

### Actor/Critic Cycle Example

- Actor tests higher aligner-priority variant.
- Critic compares rank and timeout deltas with replay evidence.
- Critic recommends keep or revert and records rationale.

## Evaluation Signals

### Metric Priority

1. Leaderboard rank/score.
2. Reliability index.
3. Friction index.
4. Submit coverage index.

### Tie-Break Rule

When rank is statistically indistinguishable, prefer:

1. Better reliability.
2. Lower friction.
3. Broader submit coverage.

### Secondary Metrics

- **Friction index:** failed invocations, confusing errors, rerun count, time-to-first-successful scrimmage,
  time-to-first-successful upload+submit.
- **Reliability index:** downtime minutes, stalled-run count, timeout/crash incidents, percent of runs completing full
  loop.
- **Submit coverage index:** distinct valid submissions, breadth across experiment families, proportion of attempts
  reaching submit.

### Diagnosis Readout Example

"Rank flat, timeout 1.1% -> 5.4%, reruns 2 -> 9; likely batching slowdown; next action revert batching and rerun eval
pack."

### Friction Taxonomy (Required)

- setup/auth
- CLI usability
- data integrity
- runtime/performance
- submission workflow

Each friction item must include:

- reproduction command
- observed error
- likely owner
- proposed fix

## 3-Week Plan

1. Ship startup workflow from scratch with explicit setup/auth requirements.
2. Ship resume workflow from existing context with ranked next actions.
3. Implement reaper detection/recovery/escalation behavior for the single-agent Claude path.
4. Implement actor/critic analysis over durable artifacts.
5. Add optional swarm execution mode that shares the same loop contract and artifacts.
6. Add `research` command orchestration plus log-mining/defect-intake services for thread-vision diagnosis loops.

## Acceptance Criteria

- Startup and resume complete the full submission loop without undocumented manual fixes.
- Downtime and friction trend down over repeated daily runs.
- Submit coverage rises over time with reasoned experiment logs.
- Artifact bundles explain each major gain or regression.

## Non-Goals

- Fully autonomous production operation without human review/safety checks.
- Zero-failure operation across every environment and command path.

## Risks and Mitigations

### Risk

Optimizing only for rank can hide fragility and produce brittle workflows.

### Mitigation

- Reliability and friction are required quality signals, not optional dashboards.
- No win is declared without artifact-backed diagnosis.

## Later Expansion

- Add a broader pantheon of AI researchers (optimizer, debugger, profiler, replay analyst, data auditor).
- Add multiple risk postures (safe, fast, experimental).
- Expand orchestration policies and instrumentation depth over time.

## Open Questions

1. What are the canonical CLI entrypoint names and UX for `startup` and `resume`?
2. What artifact bundle schema should be considered v1 stable?
3. Should reaper state be persisted locally only, or shared centrally for team visibility?
4. For daily baseline evaluation, default season is `beta-cvc` (canonical version; currently `beta-cvc:v3`).
5. What is the minimum swarm interface (worker protocol, quotas, timeout policy) for v1 optional mode?
