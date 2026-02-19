#!/usr/bin/env -S uv run

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from typing import Any

import wandb

from metta.common.util.constants import METTA_WANDB_ENTITY, METTA_WANDB_PROJECT


@dataclass(frozen=True)
class Field:
    key: str
    label: str


def _flat_get(config: dict[str, Any], dotted: str) -> Any:
    cur: Any = config
    for part in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        if part not in cur:
            return None
        cur = cur[part]
    return cur


def _pick_best_run(
    entity: str,
    project: str,
    sweep_name: str,
    limit: int = 200,
) -> tuple[str, float | None, str, dict[str, Any]]:
    api = wandb.Api(timeout=120)
    runs = api.runs(
        f"{entity}/{project}",
        filters={"group": sweep_name},
        per_page=limit,
        order="-created_at",
    )

    best: tuple[float, str, Any, dict[str, Any]] | None = None
    for r in runs:
        summary = dict(r.summary or {})
        if "sweep/score" not in summary:
            continue
        score = summary["sweep/score"]
        if score is None:
            continue
        score_f = float(score)
        if best is None or score_f > best[0]:
            cfg = dict(r.config or {})
            tool_cfg = cfg.get("TrainTool", {})
            if not isinstance(tool_cfg, dict):
                tool_cfg = {}
            best = (score_f, r.name, r.id, tool_cfg)

    if best is None:
        raise RuntimeError(f"No evaluated runs found for group={sweep_name!r} in {entity}/{project}")

    score, run_name, run_id, cfg = best
    return run_name, score, run_id, cfg


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect the current best CogSGuard sweep run by aligned junction metric."
    )
    parser.add_argument("sweep_name", help="W&B group / sweep name, e.g. relh.cogsguard.0129")
    parser.add_argument("--project", default=METTA_WANDB_PROJECT)
    parser.add_argument("--entity", default=METTA_WANDB_ENTITY)
    parser.add_argument("--top", type=int, default=200, help="Max runs to inspect.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON output")
    args = parser.parse_args()

    run_name, score, run_id, cfg = _pick_best_run(args.entity, args.project, args.sweep_name, limit=args.top)

    keys = [
        Field("trainer.optimizer.learning_rate", "learning_rate"),
        Field("trainer.optimizer.momentum", "momentum"),
        Field("trainer.optimizer.weight_decay", "weight_decay"),
        Field("trainer.optimizer.eps", "eps"),
        Field("trainer.optimizer.warmup_steps", "warmup_steps"),
        Field("trainer.sampling.prio_alpha", "prio_alpha"),
        Field("trainer.sampling.prio_beta0", "prio_beta0"),
        Field("trainer.advantage.gamma", "gamma"),
        Field("trainer.advantage.gae_lambda", "gae_lambda"),
        Field("trainer.losses.ppo_actor.clip_coef", "clip_coef"),
        Field("trainer.losses.ppo_actor.ent_coef", "ent_coef"),
        Field("trainer.losses.ppo_critic.vf_coef", "vf_coef"),
    ]

    suggestion = {key.label: _flat_get(cfg, key.key) for key in keys}
    payload = {
        "run_name": run_name,
        "run_id": run_id,
        "sweep_name": args.sweep_name,
        "score": score,
        "suggestion": suggestion,
        "project": args.project,
        "entity": args.entity,
    }

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    print(f"Best run: {run_name}")
    print(f"Group:   {args.sweep_name}")
    print(f"Score:   {score}")
    print("Suggested overrides:")
    for key in keys:
        print(f"  {key.label}: {_flat_get(cfg, key.key)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
