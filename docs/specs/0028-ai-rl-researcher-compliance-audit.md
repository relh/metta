# AI RL Researcher Compliance Audit and Closeout

> **Status:** Implemented (post-audit closeout)  
> **Author:** Richard + Codex  
> **Date:** 2026-02-23  
> **Scope:** `packages/cogames-rl-researcher`

## Context

This document captures:

1. What the AI Competition Bot thread vision required.
2. How `cogames-rl-researcher` mapped to those requirements.
3. Which gaps were identified in the audit.
4. What code changes were made to close those gaps.

Primary source spec: `docs/specs/0025-ai-rl-researcher-bot-workflows.md`.

## Requirement Breakdown

### 1. Runnable startup and resume workflows (full loop)

Required:

- Startup and resume entrypoints that run real submission loop end-to-end.
- Baseline chain:
  1. login/auth check
  2. scrimmage/eval with JSON + replay capture
  3. dry-run upload validation
  4. upload
  5. submit
  6. leaderboard check
  7. diagnosis + next proposal

Implemented in:

- `startup.py` step catalog + orchestration
- `resume.py` missing-step completion + next-actions
- CLI scripts:
  - `run_ai_researcher_startup.py`
  - `run_ai_researcher_resume.py`

### 2. Reaper behavior and SLOs

Required:

- Detect stalls/idle/auth failures quickly.
- Retry/recovery policy.
- Escalate after repeated failed recoveries.
- SLOs: detect within 10m, recovery within 5m, escalate after 2 consecutive failed recoveries.

Implemented in:

- `startup.py` command execution + incident logging + SLO evaluation.
- Reaper constants set to:
  - detect: 600s
  - recovery: 300s
  - escalation threshold: 2

### 3. Actor/Critic loop and explicit decisioning

Required:

- Actor proposes next candidate and intended metric.
- Critic ranks bottlenecks and decides keep/revert/investigate.
- Tie-break behavior when rank is statistically indistinguishable.

Implemented in:

- `actor_critic.py` (metric deltas, significance, verdict logic, bottleneck ranking).
- Tie-break order encoded as:
  1. reliability
  2. friction
  3. submit coverage

### 4. Evaluation signals and metric priority

Required:

- Primary: rank/score.
- Secondary: reliability, friction, submit coverage.
- Durable diagnosis readout and artifacts.

Implemented in:

- `startup.py` models:
  - `FrictionIndex`
  - `ReliabilityIndex`
  - `SubmitCoverageIndex`
- `history_comparison.json`, `daily_report.md`, `audit_bundle.json`.

### 5. Experienced vs Neophyte profiles

Required:

- Experienced: broad tuning freedom.
- Neophyte: constrained to documented happy path + concrete friction logging.

Implemented baseline:

- Profile-aware gate budgets were already in place.

Closeout change:

- Added explicit neophyte happy-path guard in startup and resume.
- Violations now fail run with a concrete guard failure artifact.

### 6. Services: research, log mining, defect intake

Required:

- Single research command orchestration.
- Log mining over gastown/claude/codex failure traces.
- Crash defect intake and backlog.

Implemented in:

- `research_command.py`
- `log_mining.py`
- `defects.py`

### 7. Submit coverage across variants

Required:

- Increase valid submits across experiment families.
- Produce coverage artifacts and next tuning proposals.

Implemented in:

- `coverage.py`
- `coverage_tuning.py`

## Gaps Identified in Audit

1. Neophyte restrictions were budget-only; no hard happy-path enforcement.
2. Defect flow lacked an explicit fix validation loop from intake -> verify -> close.
3. `pickup` workflow was not exposed in `cogames-rl-researcher`.
4. Trend requirement (reliability/friction trend over repeated runs) was tracked but not gate-enforced.

## Closeout Changes Implemented

### A. Neophyte happy-path enforcement

Startup:

- Added `neophyte_happy_path_guard` failure when neophyte config disables upload/submit/leaderboard baseline steps.

Resume:

- Added neophyte guard against:
  - `force-*` overrides
  - `skip-missing-*` toggles
  - disabling leaderboard
  - enabling swarm plan

Outcome:

- Neophyte profile now enforces documented happy-path constraints directly.

### B. Defect intake to fix validation loop

Added to `defects.py`:

- `DefectFixPlan` + ranked `build_defect_fix_plan`.
- `DefectFixAttempt` + `validate_defect_fix`.
- CLI actions:
  - `fix-plan`
  - `validate-fix`

Behavior:

- `validate-fix` executes a candidate fix command and records logs/attempt metadata.
- Marking a defect fixed requires explicit opt-in (`--mark-fixed-on-success`) to avoid false-positive closures.
- Resume now imports defect fix plan actions into ranked next actions and writes `defect_fix_plan.json`.

### C. Pickup workflow in cogames-researcher package

Added:

- `pickup.py` with `PickupConfig`, `PickupResult`, `run_pickup`.
- script `run_ai_researcher_pickup.py`.
- pickup artifacts:
  - `pickup_result.json`
  - `pickup_diagnosis.md`
  - replay directory

Outcome:

- Diagnose/scrimmage/pickup axis is now runnable from this package.

### D. Trend gates

Added gate checks:

- `reliability_trend`
- `friction_trend`

Rule:

- If baseline exists, fail when reliability delta regresses or friction delta regresses.
- If no baseline, pass with `baseline=n/a`.

Escalation:

- Added explicit escalation action for trend regressions.

## Validation

Package tests:

- `uv run pytest packages/cogames-rl-researcher/tests -q`

Results after closeout should include:

- Existing startup/resume/actor-critic/log-mining/coverage/defect tests.
- New tests for:
  - neophyte guard behavior
  - trend gate regressions
  - defect fix planning/validation
  - pickup workflow artifacts

## Delivered Outcome

After closeout, `cogames-rl-researcher` now covers the sprint spec and thread vision more completely by:

- enforcing neophyte workflow discipline,
- connecting defect intake to validation and closure,
- exposing pickup as a first-class workflow,
- and converting trend expectations into explicit gate behavior.
