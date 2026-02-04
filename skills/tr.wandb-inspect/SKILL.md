---
name: tr.wandb-inspect
description:
  Use when you need to read Weights & Biases runs, compare configs, or rank runs by metrics (for example
  aligned.junction.held) to choose candidate runs to emulate.
---

# W&B Run Inspection

## Overview

Inspect W&B runs for configs and metrics, then shortlist candidates by a guiding metric (default:
`env_collective/cogs/aligned.junction.held`).

**Announce at start:** "Inspecting W&B runs for configs and metrics. I’ll confirm access, then rank candidates."

## Step 1: Confirm Access

Check API access via `WANDB_API_KEY` or `~/.netrc`.

```bash
python - <<'PY'
import wandb
api = wandb.Api()
print(api.viewer())
PY
```

If this fails, ask the user to authenticate with `wandb login` or provide a key.

## Step 2: Gather Filters

Collect:

- `entity` and `project` (default: `metta-research/metta` if appropriate)
- run name or regex
- time window or limit
- metric to rank (default: `env_collective/cogs/aligned.junction.held`)

## Step 3: Fetch Runs + Extract Configs

```bash
python - <<'PY'
import wandb

entity = "metta-research"
project = "metta"
name_regex = "cogsguard"
metric = "env_collective/cogs/aligned.junction.held"

api = wandb.Api()
runs = api.runs(f"{entity}/{project}", filters={"display_name": {"$regex": name_regex}}, order="-created_at", per_page=50)

rows = []
for r in runs:
    cfg = r.config.get("TrainTool") or {}
    trainer = cfg.get("trainer", {})
    training_env = cfg.get("training_env", {})
    losses = trainer.get("losses", {})
    ssc = losses.get("sliced_scripted_cloner", {})
    sup = losses.get("supervisor", {})
    mode = "supervisor" if sup.get("enabled") else "sliced_cloner" if ssc.get("enabled") else "none"
    t_prop = sup.get("teacher_led_proportion") if sup.get("enabled") else ssc.get("teacher_led_proportion")
    s_prop = None if sup.get("enabled") else ssc.get("student_led_proportion")

    score = r.summary.get(metric)
    rows.append((score, r.display_name, mode, t_prop, s_prop, training_env.get("supervisor_policy_uri")))

rows.sort(key=lambda x: (x[0] is None, -(x[0] or 0)))
for score, name, mode, t_prop, s_prop, policy_uri in rows[:10]:
    print(f"{name} | {score} | mode={mode} t={t_prop} s={s_prop} policy={policy_uri}")
PY
```

If the metric is missing in `summary`, pull the last value from history:

```bash
python - <<'PY'
import wandb

entity = "metta-research"
project = "metta"
run_id = "<run_id>"
metric = "env_collective/cogs/aligned.junction.held"

api = wandb.Api()
run = api.run(f"{entity}/{project}/{run_id}")
last = None
for row in run.scan_history(keys=[metric], page_size=1000):
    if metric in row:
        last = row[metric]
print("last", metric, last)
PY
```

## Step 4: Summarize Candidates

- Report top runs with score, teacher mode/proportions, and `supervisor_policy_uri`.
- Call out missing metrics or obvious config gaps.
- If asked, suggest a short list of 3–5 runs to emulate and why.

## Quick Reference

| Task              | Command                                         |
| ----------------- | ----------------------------------------------- |
| Verify auth       | `python - <<'PY' ... api.viewer() ... PY`       |
| List top runs     | `python - <<'PY' ... runs() ... summary ... PY` |
| Last metric value | `python - <<'PY' ... scan_history() ... PY`     |

## Integration

**Uses:** none **Called by:** none **Pairs with:** `tr.checkpoint-find`, `do.mettabox-ops`, `n.debug-jobs`
