from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from metta.cogworks.curriculum.learning_progress_algorithm import LearningProgressConfig
from metta.cogworks.curriculum.prioritized_regret_algorithm import PrioritizedRegretConfig
from metta.cogworks.curriculum.regret_learning_progress_algorithm import RegretLearningProgressConfig
from metta.cogworks.curriculum.synthetic_task_graph.dynamics import DynamicsConfig
from metta.cogworks.curriculum.synthetic_task_graph.graph import generate_random_task_graph
from metta.cogworks.curriculum.synthetic_task_graph.simulator import (
    CurriculumAlgorithmSampler,
    GreedyOracleSampler,
    RandomSampler,
    run_simulation,
)


def _build_sampler(name: str, num_tasks: int):
    task_ids = list(range(num_tasks))
    if name == "random":
        return RandomSampler()
    if name == "oracle":
        raise ValueError("oracle is handled separately as the baseline")
    if name == "learning_progress":
        algorithm = LearningProgressConfig().create(num_tasks)
        return CurriculumAlgorithmSampler(algorithm=algorithm, task_ids=task_ids)
    if name == "prioritized_regret":
        algorithm = PrioritizedRegretConfig(optimal_value=1.0).create(num_tasks)
        return CurriculumAlgorithmSampler(algorithm=algorithm, task_ids=task_ids)
    if name == "regret_learning_progress":
        algorithm = RegretLearningProgressConfig(optimal_value=1.0).create(num_tasks)
        return CurriculumAlgorithmSampler(algorithm=algorithm, task_ids=task_ids)

    raise ValueError(f"unknown sampler: {name}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="synthetic_task_graph")
    parser.add_argument("--num-tasks", type=int, default=64)
    parser.add_argument("--max-prereqs", type=int, default=3)
    parser.add_argument("--prereq-prob", type=float, default=0.15)
    parser.add_argument("--steps", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--samplers",
        nargs="+",
        default=["random", "learning_progress", "prioritized_regret", "regret_learning_progress"],
        choices=["random", "learning_progress", "prioritized_regret", "regret_learning_progress"],
    )
    parser.add_argument("--dump-json", type=Path, default=None)
    args = parser.parse_args(argv)

    rng = random.Random(args.seed)
    graph = generate_random_task_graph(
        num_tasks=args.num_tasks,
        max_prereqs=args.max_prereqs,
        prereq_prob=args.prereq_prob,
        rng=rng,
    )
    config = DynamicsConfig()

    oracle = GreedyOracleSampler(config)
    oracle_result = run_simulation(graph=graph, sampler=oracle, config=config, steps=args.steps, seed=args.seed)

    rows: list[dict] = []
    for name in args.samplers:
        sampler = _build_sampler(name, graph.num_tasks)
        result = run_simulation(graph=graph, sampler=sampler, config=config, steps=args.steps, seed=args.seed)
        rows.append(
            {
                "sampler": name,
                "cumulative_score": result.cumulative_score,
                "regret_vs_oracle": oracle_result.cumulative_score - result.cumulative_score,
                "mean_competence": result.mean_competence,
            }
        )

    print(f"oracle cumulative_score={oracle_result.cumulative_score:.2f} mean_comp={oracle_result.mean_competence:.3f}")
    for row in rows:
        print(
            f"{row['sampler']}: cumulative_score={row['cumulative_score']:.2f} "
            f"regret={row['regret_vs_oracle']:.2f} mean_comp={row['mean_competence']:.3f}"
        )

    if args.dump_json is not None:
        payload = {
            "graph": {"num_tasks": graph.num_tasks, "difficulties": graph.difficulties, "prereqs": graph.prereqs},
            "dynamics": config.__dict__,
            "oracle": {
                "cumulative_score": oracle_result.cumulative_score,
                "mean_competence": oracle_result.mean_competence,
            },
            "results": rows,
        }
        args.dump_json.parent.mkdir(parents=True, exist_ok=True)
        args.dump_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
