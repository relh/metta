---
name: tr.wandb-analyze
description:
  Use when you need to analyze W&B runs in the default metta project from a W&B filter, a sweep/group name (or sweep
  script), or a list of run ids/names.
---

# W&B Run Analysis (metta)

## Overview

Fetch a set of runs from the default `metta` W&B project, then produce a compact, rankable summary (top-k table + quick
aggregate stats) for a small set of metrics you care about.

**Announce at start:** "Analyzing W&B runs in the default metta project. I’ll confirm access, fetch the run set, then
summarize + rank by your target metric."

## Step 1: Confirm access

```bash
python - <<'PY'
import wandb
api = wandb.Api(timeout=60)
print(api.viewer())
PY
```

## Step 2: Choose run selection mode

- **W&B filter**: provide a `filters` dict (optionally as JSON) for `api.runs(...)`
- **Sweep/group**: provide `group=<name>` (W&B “group”)
- **Sweep script**: `rg "group\\s*=" path/to/sweep.py` and copy the group name into `group=...`
- **Explicit run list**: provide run ids (or W&B `name`s)

## Step 3: Fetch + summarize

Edit the variables, then run:

```bash
python - <<'PY'
from __future__ import annotations

import json
import math
from typing import Any, Iterable

import wandb

from metta.common.util.constants import METTA_WANDB_ENTITY, METTA_WANDB_PROJECT

entity = METTA_WANDB_ENTITY
project = METTA_WANDB_PROJECT

# One of: filters_json | group | run_ids | run_names
filters_json: str | None = None  # e.g. '{"display_name":{"$regex":"subho.*\\\\.clips.*"}}'
group: str | None = None         # e.g. "subho.clips.t50b.v5.sweep1"
run_ids: list[str] | None = None # e.g. ["abc123", "def456"]
run_names: list[str] | None = None  # e.g. ["my-run-name-1", "my-run-name-2"]

metrics = [
    "sweep/score",
    # Common CogSGuard metrics (often already in run.summary)
    "env_game/cogs/aligned.junction.held",
    "env_game/clips/aligned.junction.held",
    # Older/alternate namespace seen in some dashboards
    "env_collective/cogs/aligned.junction.held",
    "metric/agent_step",
    "monitor/cost/accrued_total",
]
rank_metric = "env_game/cogs/aligned.junction.held"
limit = 200


def _to_f(x: Any) -> float | None:
    try:
        if x is None:
            return None
        v = float(x)
        if math.isnan(v):
            return None
        return v
    except Exception:
        return None


def _mean(xs: list[float]) -> float | None:
    return None if not xs else sum(xs) / len(xs)


def _std(xs: list[float]) -> float | None:
    if len(xs) < 2:
        return None
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


api = wandb.Api(timeout=120)
path = f"{entity}/{project}"

filters: dict[str, Any] = {}
if filters_json:
    filters.update(json.loads(filters_json))
if group:
    filters["group"] = group

rows: list[dict[str, Any]] = []

if run_ids:
    runs: Iterable[Any] = (api.run(f"{path}/{rid}") for rid in run_ids)
elif run_names:
    runs = api.runs(path, filters={"name": {"$in": run_names}}, order="-created_at", per_page=limit)
else:
    runs = api.runs(path, filters=filters, order="-created_at", per_page=limit)

for r in runs:
    summary = dict(r.summary or {})
    row = {
        "id": r.id,
        "name": getattr(r, "name", None),
        "display_name": getattr(r, "display_name", None),
        "state": getattr(r, "state", None),
    }
    for m in metrics:
        row[m] = summary.get(m)
    rows.append(row)

rows.sort(key=lambda d: (_to_f(d.get(rank_metric)) is None, -(_to_f(d.get(rank_metric)) or 0.0)))

vals = [_to_f(r.get(rank_metric)) for r in rows]
vals_f = [v for v in vals if v is not None]

print(f"{path} | runs={len(rows)} | rank_metric={rank_metric}")
print(f"{rank_metric}: mean={_mean(vals_f)} std={_std(vals_f)} n={len(vals_f)} missing={len(rows)-len(vals_f)}")
print()
print("| rank | display_name | id | state | " + " | ".join(metrics) + " |")
print("| ---: | --- | --- | --- | " + " | ".join(["---"] * len(metrics)) + " |")
for i, r in enumerate(rows[:25], start=1):
    disp = r.get("display_name") or r.get("name") or ""
    print(
        "| "
        + " | ".join(
            [
                str(i),
                str(disp).replace("|", "\\|"),
                str(r.get("id") or ""),
                str(r.get("state") or ""),
                *[str(r.get(m, "")) for m in metrics],
            ]
        )
        + " |"
    )
PY
```

## Step 4: Drill down configs (optional)

Use `tr.wandb-inspect` once you have a shortlist and want to compare configs or pull last metric values from history.

## Quick Reference

| Goal               | What to pass                                        |
| ------------------ | --------------------------------------------------- |
| Analyze by regex   | `filters_json='{"display_name":{"$regex":"..."} }'` |
| Analyze a sweep    | `group="<group-name>"`                              |
| Analyze known runs | `run_ids=["...","..."]`                             |
| Rank by a metric   | set `rank_metric="..."`                             |

## Integration

**Uses:** `tr.wandb-inspect` **Called by:** none **Pairs with:** `tr.checkpoint-find`, `n.debug-jobs`
