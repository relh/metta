---
name: tr.perf-eval
description:
  Use when benchmarking training SPS/perf for branch vs main on a mettabox or SkyPilot sandbox, and when results must be
  safe to publish in PR titles/descriptions.
---

# Perf Eval

## Overview

Run a reproducible branch-vs-main performance comparison for CogsGuard-style training, then update PR metadata only if
results pass validity checks.

**Announce at start:** "Running perf eval with strict parity checks first, then baseline, branch run, and publish."

## The Process

```dot
digraph perf_eval {
  rankdir=TB;
  node [shape=box];

  preflight [label="Step 1: Preflight"];
  freshness [label="Step 2: Branch Freshness"];
  baseline [label="Step 3: Baseline on main"];
  branch [label="Step 4: Branch run"];
  extract [label="Step 5: Extract + compare"];
  sanity [label="Step 6: Sanity gate"];
  publish [label="Step 7: Update PR"];

  preflight -> freshness -> baseline -> branch -> extract -> sanity -> publish;
  sanity -> freshness [label="invalid result"];
}
```

## Step 1: Preflight (no noise)

- One active benchmark per mettabox. If machine is busy, stop and choose another host.

```bash
./devops/mettabox/cli.py runs metta1
./devops/mettabox/cli.py audit metta1
```

- Use canonical command shape only:
  - `uv run ./tools/run.py recipes.experiment.cogsguard.train ...`
  - Avoid alias drift (`train cogsguard`, `cogsguard.train`) for publishable benchmarks.

## Step 2: Branch freshness against current main

```bash
MAIN_SHA=$(gh api repos/Metta-AI/metta/commits/main --jq .sha)
TOKEN=$(gh auth token)
./devops/mettabox/cli.py exec metta1 -- bash -lc \
  "cd /workspace/metta && git fetch https://x-access-token:${TOKEN}@github.com/Metta-AI/metta.git \
  +refs/heads/main:refs/remotes/origin/main +refs/heads/<branch>:refs/remotes/origin/<branch>"
./devops/mettabox/cli.py exec metta1 -- bash -lc \
  "cd /workspace/metta && test \"\$(git rev-parse origin/main)\" = \"$MAIN_SHA\""
```

- Treat this as a hard gate, not a best effort check.
- If `origin/main != MAIN_SHA`, stop and refetch until they match.

- Reject benchmarking stale branches. Prefer merge-tested refs (`origin/<branch>` merged/rebased on latest
  `origin/main`).

```bash
./devops/mettabox/cli.py exec metta1 -- bash -lc \
  "cd /workspace/metta && test \"\$(git merge-base origin/<branch> origin/main)\" = \"\$(git rev-parse origin/main)\""
```

### Freshness Invariant (hard requirement)

All publishable numbers must satisfy:

- `MAIN_SHA` is captured from GitHub immediately before the benchmark set.
- Baseline runs at `origin/main == MAIN_SHA`.
- Branch run uses a branch with `merge-base(branch, main) == MAIN_SHA`.
- Re-check `MAIN_SHA` between baseline and branch run. If it changed, abort and restart the set with the new `MAIN_SHA`.

## Step 3: Baseline run (same machine)

```bash
./devops/mettabox/cli.py exec metta1 -- bash -lc "cd /workspace/metta && git checkout --detach origin/main"
./devops/mettabox/cli.py run metta1 -- recipes.experiment.cogsguard.train \
  run=<baseline_run> trainer.total_timesteps=6291456
while ./devops/mettabox/cli.py runs metta1 | rg -q "<baseline_run>"; do sleep 30; done
```

Then immediately re-check main freshness before launching the branch:

```bash
MAIN_SHA_LATEST=$(gh api repos/Metta-AI/metta/commits/main --jq .sha)
test "$MAIN_SHA_LATEST" = "$MAIN_SHA" || { echo "main moved; restart benchmark set"; exit 1; }
```

## Step 4: Branch run (same args)

```bash
./devops/mettabox/cli.py exec metta1 -- bash -lc "cd /workspace/metta && git checkout --detach origin/<branch>"
./devops/mettabox/cli.py run metta1 -- recipes.experiment.cogsguard.train \
  run=<pr_run> trainer.total_timesteps=6291456
```

## Step 5: Extract SPS + config parity

- First choice: parse epoch lines from `train_dir/<run>/logs/script.log`.
- Fallback: `checkpoints/trainer_state.pt` stopwatch checkpoints.
- Verify parity in both `config.json` files:
  - `training_env.num_workers`, `training_env.vectorization`, `training_env.async_factor`
  - `trainer.batch_size`, `trainer.minibatch_size`, `trainer.total_timesteps`

## Step 6: Sanity gate before publish

- Do not publish if any condition fails:
  - branch behind current main
  - `MAIN_SHA` drifted between baseline and branch run
  - config mismatch
  - concurrent workload on same machine during run
  - suspicious magnitude for non-perf PR (for example huge negative swings)

When invalid: mark result as non-comparable and rerun after fixing freshness/parity.

## Known Failure Patterns (Recent Incidents)

- Large negative deltas on non-perf PRs usually indicated stale branch freshness or mismatched runtime config.
- Mettabox `origin/main` can be stale if HTTPS fetch auth is missing; use authenticated fetch before every benchmark
  set.
- Concurrent sessions on the same box produced contaminated SPS; treat machine exclusivity as mandatory.
- Some runs lacked rich epoch logging in `script.log`; `trainer_state.pt` checkpoint timing was the reliable fallback.
- Command-shape drift caused confusion; keep one canonical training entrypoint for publishable comparisons.

## Step 7: Publish to PR

- Include at top of PR body:
  - command, machine, baseline run/commit, branch run/commit
  - epoch 1/2/3 ksps and deltas
  - epoch 2+3 average delta
- Update title with short epoch-3 delta only after sanity passes.

## SkyPilot Sandbox Variant

- Launch with explicit git ref and same benchmark args:

```bash
./devops/skypilot/launch.py recipes.experiment.cogsguard.train \
  --gpus 8 --git-ref <ref> -- run=<run_id> trainer.total_timesteps=6291456
```

- Use `./devops/skypilot/sandbox.py` + `uv run sky logs` for status; keep baseline and branch on same sandbox.
- For `uv run sky exec` workflows, set `CUDA_VISIBLE_DEVICES` explicitly (for example `0,1,2,3`) before running training
  so GPU visibility is deterministic.
- If sandbox jobs fail early, check launcher/controller logs for environment issues (for example missing `CUDA_HOME`).

## Quick Reference

| Task             | Command                                                    |
| ---------------- | ---------------------------------------------------------- |
| Host busy check  | `./devops/mettabox/cli.py runs <host>`                     |
| Fetch fresh refs | `gh auth token` + authenticated `git fetch` on host        |
| Baseline run     | `... run <host> -- recipes.experiment.cogsguard.train ...` |
| Branch run       | same command, branch checkout changed                      |
| Show progress    | `./devops/mettabox/cli.py progress <host> <run_id>`        |

## Integration

**Uses:** `do.mettabox-ops`  
**Pairs with:** `tr.wandb-inspect`, `n.debug-jobs`, `n.monitor-infra`
