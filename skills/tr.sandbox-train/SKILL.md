---
name: tr.sandbox-train
description:
  Use when launching or repairing a Metta training run on a SkyPilot sandbox, especially when dirty /workspace state,
  missing Python envs, list-override quoting, or misleading SkyPilot job status make ad-hoc launches unreliable.
---

# Sandbox Train

## Overview

Launch training on a `relh-sandbox-*` machine in a repeatable way: pick a clean sandbox, stage the exact git ref in
`/workspace/metta`, dry-run the real `devops/run.sh` shape, then launch detached and verify the inner trainer logs.

**Announce at start:** "I’m using tr.sandbox-train: I’ll pick a clean sandbox, stage the branch, dry-run the exact
launch shape, then verify the real run from logs."

## The Process

1. Pick an idle sandbox and inspect the workspace:

```bash
for s in relh-sandbox-{1..7}; do
  echo "== $s =="
  uv run sky queue "$s" --all-users --skip-finished || true
done

CLUSTER=relh-sandbox-6
uv run sky exec "$CLUSTER" --gpus L4:4 -- env -C /workspace/metta git status --short --branch
```

Prefer a box with no active jobs. If `/workspace/metta` is dirty, only reset it after explicit user approval.

2. Stage the exact branch and bootstrap the environment:

```bash
BRANCH=$(git branch --show-current)
uv run sky exec "$CLUSTER" --gpus L4:4 -- env -C /workspace/metta git fetch origin "$BRANCH"
uv run sky exec "$CLUSTER" --gpus L4:4 -- env -C /workspace/metta git checkout -B "$BRANCH" "origin/$BRANCH"
uv run sky exec "$CLUSTER" --gpus L4:4 -- \
  env -C /workspace/metta PATH=/home/ubuntu/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
  uv sync --locked
```

If you have approval to wipe sandbox-local changes, use `git checkout -f`, `git reset --hard`, and `git clean -fd`
before the branch checkout.

3. Dry-run the exact distributed launch shape first:

```bash
MASTER_PORT=12465
uv run sky exec "$CLUSTER" --gpus L4:4 -- \
  env -C /workspace/metta NUM_GPUS=4 MASTER_PORT="$MASTER_PORT" \
  ./devops/run.sh recipes.experiment.cogsguard_marlbro.train \
  --dry-run \
  run=sandbox_probe \
  system.device=cuda \
  trainer.total_timesteps=256 \
  routed_adapter.enabled=true \
  routed_adapter.rank=8 \
  routed_adapter.trunk_lr_mult=0.5 \
  variants.0=milestones \
  variants.1=no_objective
```

Use indexed overrides like `variants.0=... variants.1=...`; quoted JSON lists can be mangled by `sky exec`.

4. Launch detached with an explicit `MASTER_PORT`:

```bash
RUN=relh.marlbro.shared.milestones_noobj.$(date +%Y%m%d%H%M)
MASTER_PORT=12466
uv run sky exec "$CLUSTER" -d --gpus L4:4 -- \
  env -C /workspace/metta NUM_GPUS=4 MASTER_PORT="$MASTER_PORT" \
  ./devops/run.sh recipes.experiment.cogsguard_marlbro.train \
  run="$RUN" \
  system.device=cuda \
  trainer.total_timesteps=3000000000 \
  routed_adapter.enabled=true \
  routed_adapter.rank=8 \
  routed_adapter.trunk_lr_mult=0.5 \
  variants.0=milestones \
  variants.1=no_objective
```

5. Verify the inner trainer, not just the outer SkyPilot job:

```bash
uv run sky queue "$CLUSTER" --all-users --skip-finished
uv run sky logs "$CLUSTER" <job_id>
```

Do not trust SkyPilot `SUCCEEDED` alone. The wrapper can exit cleanly even when inner training failed. Keep reading
until you see real startup signals such as distributed ranks bound to `cuda:0..N`, policy creation / DDP wrapping,
rank-0 config save, W&B init, or early training progress.

## Quick Reference

| Task                | Command                                                                                                              |
| ------------------- | -------------------------------------------------------------------------------------------------------------------- |
| Pick sandbox        | `uv run sky queue relh-sandbox-X --all-users --skip-finished`                                                        |
| Check workspace     | `uv run sky exec <cluster> --gpus L4:4 -- env -C /workspace/metta git status --short --branch`                       |
| Bootstrap env       | `env -C /workspace/metta PATH=/home/ubuntu/.local/bin:... uv sync --locked`                                          |
| Safe list overrides | `variants.0=... variants.1=...`                                                                                      |
| Launch              | `uv run sky exec <cluster> -d --gpus L4:4 -- env -C /workspace/metta NUM_GPUS=4 MASTER_PORT=... ./devops/run.sh ...` |
| Verify              | `uv run sky logs <cluster> <job_id>`                                                                                 |

## Integration

**Uses:** `do.mettabox-ops` for host/sandbox inspection, `relh.tr.run-recipe` for local recipe probes **Pairs with:**
`tr.checkpoint-find`, `cg.submit`, `cf.bop-it` **Called by:** `tr.perf-eval` when the benchmark target is a SkyPilot
sandbox
