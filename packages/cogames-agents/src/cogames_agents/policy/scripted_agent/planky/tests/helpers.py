"""Shared helpers for Planky capability tests."""

from __future__ import annotations

import io
import re
import sys
from dataclasses import dataclass, field
from typing import Optional

from metta_alo.rollout import run_single_episode

from cogames.cli.mission import get_mission
from mettagrid.util.uri_resolvers.schemes import policy_spec_from_uri


@dataclass
class PlayTrace:
    """Parsed trace output from a Planky episode."""

    lines: list[str] = field(default_factory=list)
    goal_activations: list[str] = field(default_factory=list)
    role_changes: list[str] = field(default_factory=list)
    idle_steps: int = 0

    def had_goal(self, name: str) -> bool:
        return any(name in line for line in self.goal_activations)

    def summary(self, max_lines: int = 50) -> str:
        parts = []
        if self.role_changes:
            parts.append("Role changes: " + ", ".join(self.role_changes))
        if self.goal_activations:
            parts.append(f"Goal activations ({len(self.goal_activations)} total):")
            show = (
                self.goal_activations[:10]
                + (["..."] if len(self.goal_activations) > 20 else [])
                + self.goal_activations[-10:]
                if len(self.goal_activations) > 20
                else self.goal_activations
            )
            for line in show:
                parts.append(f"  {line}")
        if self.idle_steps > 0:
            parts.append(f"Max idle steps: {self.idle_steps}")
        return "\n".join(parts)


def _parse_trace(output: str) -> PlayTrace:
    """Parse [planky] trace lines from captured stdout."""
    trace = PlayTrace()
    for line in output.splitlines():
        if "[planky]" not in line:
            continue
        trace.lines.append(line)

        if "\u2192" in line:
            trace.goal_activations.append(line.strip())

        if "role:" in line:
            trace.role_changes.append(line.strip())

        idle_match = re.search(r"IDLE=(\d+)", line)
        if idle_match:
            trace.idle_steps = max(trace.idle_steps, int(idle_match.group(1)))

    return trace


@dataclass
class EpisodeResult:
    """Combined stats + trace from a Planky episode."""

    rewards: list[float]
    steps: int
    agent_stats: dict[str, float]  # Aggregated across all agents
    cogs_stats: dict[str, float]
    clips_stats: dict[str, float]
    trace: PlayTrace

    @property
    def total_reward(self) -> float:
        return sum(self.rewards)

    def gear_gained(self, gear: str) -> int:
        return int(self.agent_stats.get(f"{gear}.gained", 0))

    def resource_deposited(self, resource: str) -> int:
        return int(self.cogs_stats.get(f"collective.{resource}.deposited", 0))

    def total_deposited(self) -> int:
        return sum(self.resource_deposited(r) for r in ["carbon", "oxygen", "germanium", "silicon"])

    def junctions_aligned(self) -> int:
        return int(self.cogs_stats.get("junction.gained", 0))

    def hearts_gained(self) -> int:
        return int(self.agent_stats.get("heart.gained", 0))


def run_planky_episode(
    policy_uri: str,
    mission: str = "cogsguard_machina_1.basic",
    steps: Optional[int] = None,
    seed: int = 42,
) -> EpisodeResult:
    """Run a single Planky episode and return structured results + trace."""
    _name, env_cfg, _mission_obj = get_mission(mission_arg=mission)

    if steps is not None:
        env_cfg.game.max_steps = steps

    policy_spec = policy_spec_from_uri(policy_uri, device="cpu")
    num_agents = env_cfg.game.num_agents

    # Capture stdout for trace output
    captured = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = captured
    try:
        results, _replay = run_single_episode(
            policy_specs=[policy_spec],
            assignments=[0] * num_agents,
            env=env_cfg,
            seed=seed,
            render_mode=None,
            device="cpu",
        )
    finally:
        sys.stdout = old_stdout

    output = captured.getvalue()
    trace = _parse_trace(output)

    # Aggregate agent stats
    agent_stats: dict[str, float] = {}
    for agent in results.stats.get("agent", []):
        for key, value in agent.items():
            agent_stats[key] = agent_stats.get(key, 0) + value

    collective = results.stats.get("collective", {})
    cogs_stats = collective.get("cogs", {})
    clips_stats = collective.get("clips", {})

    return EpisodeResult(
        rewards=list(results.rewards),
        steps=results.steps,
        agent_stats=agent_stats,
        cogs_stats=cogs_stats,
        clips_stats=clips_stats,
        trace=trace,
    )
