#!/usr/bin/env python3
"""compare_agents.py — Parse cogames eval JSON output and generate a comparison table.

Usage:
    python scripts/compare_agents.py RESULTS_DIR [--format {table,csv,json}]

RESULTS_DIR should contain per-agent JSON files produced by benchmark_agents.sh.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from pathlib import Path

# Metrics to extract and display.
# Each entry: (display_name, json_path_type, json_key)
#   json_path_type: "agent" = policy_summaries[0].avg_agent_metrics
#                   "game"  = avg_game_stats
METRICS = [
    ("reward", "agent_reward", None),
    ("heart.gained", "agent", "heart.gained"),
    ("heart.lost", "agent", "heart.lost"),
    ("aligned.junction.held", "game", "aligned.junction.held"),
    ("aligned.junction.gained", "game", "aligned.junction.gained"),
    ("action_timeouts", "timeouts", None),
]


def extract_metrics(data: dict) -> dict[str, float | None]:
    """Extract key metrics from a single cogames scrimmage JSON result."""
    result: dict[str, float | None] = {}

    missions = data.get("missions", [])
    if not missions:
        return {m[0]: None for m in METRICS}

    mission = missions[0]
    summary = mission.get("mission_summary", mission)
    game_stats = summary.get("avg_game_stats", {})
    policy_summaries = summary.get("policy_summaries", [])
    policy = policy_summaries[0] if policy_summaries else {}
    agent_metrics = policy.get("avg_agent_metrics", {})

    # Per-episode rewards for win-rate approximation
    per_ep_rewards = policy.get("per_episode_per_policy_avg_rewards", {})

    for display_name, path_type, key in METRICS:
        if path_type == "agent":
            result[display_name] = agent_metrics.get(key)
        elif path_type == "game":
            result[display_name] = game_stats.get(key)
        elif path_type == "agent_reward":
            # Average reward across episodes
            if per_ep_rewards:
                vals = [v for v in per_ep_rewards.values() if v is not None]
                result[display_name] = sum(vals) / len(vals) if vals else None
            else:
                result[display_name] = agent_metrics.get("reward")
        elif path_type == "timeouts":
            result[display_name] = policy.get("action_timeouts")

    return result


def load_results(results_dir: Path) -> dict[str, dict[str, float | None]]:
    """Load all agent JSON results from a directory."""
    agents: dict[str, dict[str, float | None]] = {}
    for path in sorted(results_dir.glob("*.json")):
        agent_name = path.stem
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            print(f"Warning: skipping {path.name}: {exc}", file=sys.stderr)
            continue
        agents[agent_name] = extract_metrics(data)
    return agents


def format_val(v: float | None) -> str:
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:.2f}"
    return str(v)


def print_table(agents: dict[str, dict[str, float | None]]) -> None:
    """Print a human-readable comparison table."""
    if not agents:
        print("No results found.")
        return

    metric_names = [m[0] for m in METRICS]
    col_widths = [max(len("agent"), max(len(a) for a in agents))]
    for m in metric_names:
        w = max(len(m), max(len(format_val(agents[a].get(m))) for a in agents))
        col_widths.append(w)

    header = "  ".join(
        ["agent".ljust(col_widths[0])] + [m.rjust(col_widths[i + 1]) for i, m in enumerate(metric_names)]
    )
    sep = "-" * len(header)

    print(sep)
    print(header)
    print(sep)

    # Sort agents by reward descending (None last)
    def sort_key(name: str) -> float:
        v = agents[name].get("reward")
        return v if v is not None else float("-inf")

    for agent in sorted(agents, key=sort_key, reverse=True):
        vals = agents[agent]
        row = "  ".join(
            [agent.ljust(col_widths[0])]
            + [format_val(vals.get(m)).rjust(col_widths[i + 1]) for i, m in enumerate(metric_names)]
        )
        print(row)
    print(sep)


def print_csv(agents: dict[str, dict[str, float | None]]) -> None:
    """Print CSV output."""
    metric_names = [m[0] for m in METRICS]
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["agent"] + metric_names)
    for agent in sorted(agents):
        writer.writerow([agent] + [format_val(agents[agent].get(m)) for m in metric_names])
    print(buf.getvalue(), end="")


def print_json_output(agents: dict[str, dict[str, float | None]]) -> None:
    """Print JSON output."""
    print(json.dumps(agents, indent=2, default=str))


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare cogames eval results.")
    parser.add_argument("results_dir", type=Path, help="Directory with agent JSON results")
    parser.add_argument(
        "--format",
        choices=["table", "csv", "json"],
        default="table",
        help="Output format (default: table)",
    )
    args = parser.parse_args()

    if not args.results_dir.is_dir():
        print(f"Error: {args.results_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    agents = load_results(args.results_dir)

    if args.format == "table":
        print_table(agents)
    elif args.format == "csv":
        print_csv(agents)
    elif args.format == "json":
        print_json_output(agents)


if __name__ == "__main__":
    main()
