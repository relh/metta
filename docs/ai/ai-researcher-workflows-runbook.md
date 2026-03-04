# AI Researcher Workflows Runbook

This runbook covers what is already implemented in `metta` for the AI researcher loop and how to run it end-to-end.

## Prompt Meta-Layer

If you want an AI coding agent to run the workflow from a single prompt ("run the neophyte workflow"), use:

- `packages/cogames-rl-researcher/prompts/run-neophyte-workflow.md`
- `packages/cogames-rl-researcher/prompts/run-experienced-workflow.md`

These prompts orchestrate the existing scripts as tools, including tutorial readthrough, policy creation, training,
startup/submit, and reporting.

One-line agent launch:

```bash
./packages/cogames-rl-researcher/scripts/run_ai_researcher_agent_workflow.py --agent codex --profile neophyte
./packages/cogames-rl-researcher/scripts/run_ai_researcher_agent_workflow.py --agent claude --profile experienced
```

## What Exists Today

Implementation package:

- `packages/cogames-rl-researcher`

Primary runnable workflows:

- `startup`: full baseline submission loop
- `resume`: continue from prior artifacts and generate ranked next actions
- `research`: single command orchestration for train + startup + resume

Supporting services:

- `log mining`: mine failed `cogames` attempts from gastown/claude/codex logs
- `defect intake`: submit crash defects, maintain backlog, and validate fixes
- `pickup`: diagnose/scrimmage shadow workflow
- `actor/critic`: analyze run deltas and propose bottleneck-driven actions
- `coverage pack` + `coverage tuning`: expand and tune submit coverage across variants

## Baseline Loop Covered by Startup/Resume

The implemented loop follows:

1. login/auth check
2. scrimmage/eval with JSON output + replay capture
3. dry-run upload validation
4. upload
5. submit to season
6. leaderboard check
7. diagnosis + next experiment proposal

## Prerequisites

From repo root:

```bash
cd /Users/relh/Code/workspace/metta
```

Authenticate once before non-interactive runs:

```bash
cogames login
```

Optional: run tests for this package:

```bash
uv run pytest packages/cogames-rl-researcher/tests -q
```

## Startup Workflow (From Scratch)

```bash
./packages/cogames-rl-researcher/scripts/run_ai_researcher_startup.py \
  --policy metta://policy/role_py \
  --policy-name my-policy \
  --season beta-cvc
```

Notes:

- add `--allow-interactive-login` if local browser-based auth recovery is desired
- use `--researcher-profile neophyte` for stricter happy-path/gate behavior
- gates are enforced by default; use `--no-enforce-gates` to avoid non-zero exit on gate failure

### Startup via Cogent Branch Jobs (Neophyte Competitor Bot)

The old `--neophyte-competitor-bot` runner flag is retired. Use branch-submitted jobs (`.agent/jobs/*.md`) on a
`cogent/*` branch:

```bash
BRANCH="cogent/ai-researcher-neophyte-$(date +%Y%m%d-%H%M%S)"
git checkout -b "$BRANCH"
mkdir -p .agent/jobs

cat > .agent/jobs/ai-researcher-neophyte.md <<'EOF'
---
schedule: once
agent: codex
timeout: 180
---
Run the canonical neophyte researcher workflow end-to-end using
`packages/cogames-rl-researcher/prompts/run-neophyte-workflow.md`.
EOF

git add -f .agent/jobs/ai-researcher-neophyte.md
git commit -m "[cogent] launch neophyte researcher workflow"
git push -u origin HEAD
```

### Startup via Cogent Branch Jobs (Experienced Competitor Bot)

The old `--experienced-competitor-bot` runner flag is retired. Use branch-submitted jobs (`.agent/jobs/*.md`) on a
`cogent/*` branch:

```bash
BRANCH="cogent/ai-researcher-experienced-$(date +%Y%m%d-%H%M%S)"
git checkout -b "$BRANCH"
mkdir -p .agent/jobs

cat > .agent/jobs/ai-researcher-experienced.md <<'EOF'
---
schedule: once
agent: codex
timeout: 240
---
Run the canonical experienced researcher workflow end-to-end using
`packages/cogames-rl-researcher/prompts/run-experienced-workflow.md`.
EOF

git add -f .agent/jobs/ai-researcher-experienced.md
git commit -m "[cogent] launch experienced researcher workflow"
git push -u origin HEAD
```

Monitor completion from git history:

```bash
git fetch origin <cogent-branch> --quiet
git log --oneline -n 5 origin/<cogent-branch>
git ls-tree --name-only -r origin/<cogent-branch> -- .agent/jobs/
```

Success signal: the one-shot job file is removed and a cleanup commit appears:
`[cogent] cleanup: completed one-shot job <filename>`.

## Resume Workflow (Continue Existing Run)

Use the `run_dir` printed by startup:

```bash
./packages/cogames-rl-researcher/scripts/run_ai_researcher_resume.py \
  --source ./artifacts/ai_researcher/<startup_run_dir>
```

Optional enhancements:

```bash
# include explicit log-mining context
./packages/cogames-rl-researcher/scripts/run_ai_researcher_resume.py \
  --source ./artifacts/ai_researcher/<startup_run_dir> \
  --log-mining-report ./artifacts/ai_researcher/log_mining_report.json

# emit optional swarm plan
./packages/cogames-rl-researcher/scripts/run_ai_researcher_resume.py \
  --source ./artifacts/ai_researcher/<startup_run_dir> \
  --emit-swarm-plan \
  --swarm-workers 4
```

## One-Command Research Loop

```bash
./packages/cogames-rl-researcher/scripts/run_ai_researcher_research.py \
  --policy metta://policy/role_py \
  --policy-name my-policy \
  --train-command "uv run ./tools/run.py train arena run=my_exp trainer.total_timesteps=100000" \
  --season beta-cvc
```

If you only want submission/diagnosis orchestration:

```bash
./packages/cogames-rl-researcher/scripts/run_ai_researcher_research.py \
  --policy metta://policy/role_py \
  --policy-name my-policy \
  --skip-train \
  --season beta-cvc
```

## Optional Services

Log mining service:

```bash
./packages/cogames-rl-researcher/scripts/run_ai_researcher_log_mining_service.py \
  --log-root ./artifacts \
  --log-root ./logs \
  --output ./artifacts/ai_researcher/log_mining_report.json \
  --iterations 1
```

Continuous mode:

```bash
./packages/cogames-rl-researcher/scripts/run_ai_researcher_log_mining_service.py --watch
```

Crash defect intake:

```bash
./packages/cogames-rl-researcher/scripts/run_ai_researcher_defect_intake.py \
  --store-dir ./artifacts/ai_researcher/defects \
  submit \
  --reporter codex \
  --command "cogames upload --name my-policy --policy metta://policy/role_py --season beta-cvc" \
  --observed-error "authentication failed: token expired"
```

Regenerate backlog and fix plan:

```bash
./packages/cogames-rl-researcher/scripts/run_ai_researcher_defect_intake.py \
  --store-dir ./artifacts/ai_researcher/defects \
  backlog

./packages/cogames-rl-researcher/scripts/run_ai_researcher_defect_intake.py \
  --store-dir ./artifacts/ai_researcher/defects \
  fix-plan
```

## Key Output Artifacts

Each run writes to `./artifacts/ai_researcher/<run_id>/`.

Most important files:

- `audit_bundle.json`
- `daily_report.md`
- `docs_digest.json` and `docs_digest.md`
- `gates_evaluation.json`
- `escalation_plan.json`
- `history_comparison.json`
- `ranked_next_actions.json` (resume)
- `actor_critic_report.json` (resume/analysis)
- `fix_pack_plan.json` (if proposals generated)
- `replays/`

## Validation Notes (2026-02-24)

An initial spot-check pass was run first, followed by the comprehensive full-entrypoint sweep below. The comprehensive
section is the canonical validation summary for this runbook.

## Comprehensive Sweep (2026-02-24)

This follow-up validation executed a broader matrix across all package entrypoints and expected-failure paths.

Execution root:

- `/tmp/ai_researcher_comprehensive_20260224_074025`

Harness:

- fake local `cogames` binary: `/tmp/fake_cogames_ai_researcher.py`
- no production upload/submit endpoints used

### Commands Executed

Total scripted command runs: `23`

- expected-pass commands: `19`
- expected-fail commands (guardrails/negative tests): `4`

All commands matched expected outcomes.

### Profile Matrix

Experienced:

- startup: success, gates pass
- resume: success, gates pass
- resume with swarm plan: success, gates pass
- research (`--skip-train`): success

Neophyte:

- startup: success, gates pass
- resume: success, gates pass
- research (`--skip-train`): success

Shared successful-run metrics (all matrix runs):

- full loop completion: `100%`
- failed invocations: `0`
- reaper escalations: `0`
- attempt-to-submit ratio: `1.0`

### Guardrail and Negative Paths

Expected failures validated:

- neophyte startup with `--no-submit` failed with `neophyte_happy_path_guard`
  - message: `run_submit must remain enabled for neophyte profile`
- neophyte resume with `--force-scrimmage --emit-swarm-plan` failed with `neophyte_happy_path_guard`
  - message: `force-* resume overrides are not allowed for neophyte profile`
  - message: `emit_swarm_plan is not allowed for neophyte profile`
- resume source pointed at `<research_run_dir>` failed with clear CLI parser error (no stack trace)
- defect fix validation with `--fix-command false` failed as expected (`return_code=1`)

### Supporting Workflows

Additional workflows were exercised successfully:

- pickup (`run_ai_researcher_pickup.py`)
- log mining service (`run_ai_researcher_log_mining_service.py`)
- defect intake lifecycle (`submit`, `backlog`, `fix-plan`, `set-status`, `validate-fix`)
- standalone actor/critic report generation
- standalone swarm plan generation
- submit coverage pack
- coverage tuning plan

Key artifact outputs from sweep:

- `log_mining_report.json`: `total_failures=3` (gastown=1, claude=1, codex=1)
- defect backlog after success/failure validation: `total_defects=1`, `open_defects=0` (`fixed=1`)
- coverage pack: `attempted_variants=3`, `successful_submits=3`, `valid_submit_coverage_ratio=1.0`,
  `experiment_family_breadth=3`, `breadth_ratio=1.0`
- coverage tuning plan: `focus_category=setup/auth`, `proposals=4`
- actor/critic standalone: `verdict=revert`, `bottlenecks=2`, `fix_pack_proposals=3`
- swarm standalone: `workers=4`, `tasks=2`, `verdict=revert`

### Test Suite

Post-sweep package tests:

- `uv run pytest packages/cogames-rl-researcher/tests -q`
- result: `44 passed, 1 skipped`
