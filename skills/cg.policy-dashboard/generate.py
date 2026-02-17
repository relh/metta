#!/usr/bin/env python3
"""Generate tournament policy dashboard.

Usage:
    python generate.py [--policy NAME:VERSION] [--limit N] [--output PATH] [--season SEASON]
    python generate.py --local-results DIR [--policy-name NAME] [--limit N] [--output PATH]
    python generate.py --demo [--output PATH]
"""

from __future__ import annotations

import argparse
import ast
import json
import shutil
import statistics
import subprocess
import sys
import webbrowser
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn
from rich.prompt import Prompt
from rich.table import Table

from cogames.cli.login import CoGamesAuthenticator

console = Console()

# API Configuration
TOURNAMENT_API = "https://api.observatory.softmax-research.net"
LOGIN_SERVER = "https://softmax.com/api"
DEFAULT_SEASON = "beta-cvc"


@dataclass
class PolicyVersion:
    """Policy version info."""

    id: str
    name: str
    version: int
    rank: int | None = None
    score: float | None = None
    matches: int = 0


@dataclass
class EpisodeData:
    """Episode statistics."""

    episode_id: str
    job_id: str
    opponent_name: str
    opponent_version: int
    team_composition: str  # "6v2", "4v4", "2v6"
    reward: float
    status: str  # "completed", "failed"
    error_type: str | None = None
    steps: int = 0
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass
class DerivedMetrics:
    """Computed KPIs derived from episode metrics."""

    # Efficiency KPIs (0-1 scale)
    move_efficiency: float = 0.0  # move.success / (move.success + move.failed)
    action_success_rate: float = 0.0  # 1 - (action.failed / total_actions)
    vibe_change_rate: float = 0.0  # change_vibe.success / total_actions

    # Resource KPIs
    resource_retention: float = 0.0  # amount / gained (how well we keep resources)

    # Vulnerability KPIs
    freeze_vulnerability: float = 0.0  # frozen.ticks / steps (% time frozen)

    # Junction KPIs
    junction_control_rate: float = 0.0  # aligned.junction / total_junctions
    alignment_stability: float = 0.0  # held / gained (how long held)
    net_alignment_rate: float = 0.0  # (gained - lost) / gained

    # Reward KPIs
    avg_reward: float = 0.0  # mean episode reward

    # New KPIs
    noop_rate: float = 0.0  # action.noop.success / total_actions
    resource_efficiency_per_step: float = 0.0  # sum(resource.gained) / total_steps
    hearts_to_junction_rate: float = 0.0  # junction.aligned_by_agent / heart.lost
    reward_consistency: float = 0.0  # 1 - (std/mean) clamped 0-1
    reward_nonzero_pct: float = 0.0  # % episodes with reward > 0.1

    # Strategy profile scores (0-100)
    profile_aggressive: float = 0.0
    profile_defensive: float = 0.0
    profile_resource_hoarder: float = 0.0
    profile_junction_hunter: float = 0.0
    profile_mobile_scout: float = 0.0

    # Diagnostic flags
    diagnostics: list[str] = field(default_factory=list)


@dataclass
class DashboardData:
    """All data needed for dashboard."""

    policy: PolicyVersion
    episodes: list[EpisodeData]
    season: str
    generated_at: str
    derived: DerivedMetrics = field(default_factory=DerivedMetrics)


class TournamentAPI:
    """Client for tournament API."""

    def __init__(self, token: str):
        self.token = token
        self.client = httpx.Client(
            base_url=TOURNAMENT_API,
            headers={"X-Auth-Token": token},
            timeout=30.0,
        )

    def close(self):
        self.client.close()

    def get_leaderboard_policies(self, season: str) -> list[PolicyVersion]:
        """Get all policies from the season leaderboard."""
        leaderboard = self.client.get(f"/tournament/seasons/{season}/leaderboard").json()
        result = []
        for entry in leaderboard:
            p = entry["policy"]
            result.append(
                PolicyVersion(
                    id=p["id"],
                    name=p["name"],
                    version=p["version"],
                    rank=entry.get("rank"),
                    score=entry.get("score"),
                    matches=entry.get("matches", 0),
                )
            )
        return sorted(result, key=lambda x: (x.rank or 9999,))

    def get_my_policies(self, season: str) -> list[PolicyVersion]:
        """Get user's policies in a season with leaderboard info.

        This includes policies not yet on the leaderboard.
        """
        # Get leaderboard for ranks/scores
        leaderboard = self.client.get(f"/tournament/seasons/{season}/leaderboard").json()
        lb_map = {entry["policy"]["id"]: entry for entry in leaderboard}

        # Get user's policies (includes non-leaderboard ones)
        resp = self.client.get(
            f"/tournament/seasons/{season}/policies",
            params={"mine": "true"},
        )
        policies = resp.json()

        result = []
        for p in policies:
            policy_info = p["policy"]
            policy_id = policy_info["id"]
            lb_entry = lb_map.get(policy_id, {})
            result.append(
                PolicyVersion(
                    id=policy_id,
                    name=policy_info["name"],
                    version=policy_info["version"],
                    rank=lb_entry.get("rank"),
                    score=lb_entry.get("score"),
                    matches=lb_entry.get("matches", 0),
                )
            )
        return sorted(result, key=lambda x: (x.name, -x.version))

    def query_episodes(self, policy_version_id: str, limit: int) -> list[dict]:
        """Query episodes for a policy using the stats API."""
        resp = self.client.post(
            "/stats/episodes/query",
            json={
                "primary_policy_version_ids": [policy_version_id],
                "limit": limit,
            },
        )
        return resp.json().get("episodes", [])

    def get_policy_version(self, policy_version_id: str) -> dict | None:
        """Get policy version details by ID."""
        try:
            resp = self.client.get(f"/stats/policy-versions/{policy_version_id}")
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return None


def get_auth_token() -> str:
    """Get authentication token from cogames login."""
    auth = CoGamesAuthenticator()
    token = auth.load_token(LOGIN_SERVER)
    if not token:
        console.print("[red]Not logged in. Run 'cogames login' first.[/red]")
        sys.exit(1)
    return token


def select_policy_interactive(api: TournamentAPI, season: str) -> PolicyVersion:
    """Interactive policy selection from user's policies."""
    console.print(f"\n[bold]Fetching your policies in {season}...[/bold]")
    policies = api.get_my_policies(season)

    if not policies:
        console.print("[red]No policies found in this season.[/red]")
        sys.exit(1)

    table = Table(title="Your Policies")
    table.add_column("#", style="dim")
    table.add_column("Name")
    table.add_column("Version")
    table.add_column("Rank")
    table.add_column("Score")
    table.add_column("Matches")

    for i, p in enumerate(policies, 1):
        table.add_row(
            str(i),
            p.name,
            f"v{p.version}",
            str(p.rank) if p.rank else "-",
            f"{p.score:.3f}" if p.score else "-",
            str(p.matches),
        )

    console.print(table)
    choice = Prompt.ask(
        "\nSelect policy number",
        choices=[str(i) for i in range(1, len(policies) + 1)],
    )
    return policies[int(choice) - 1]


def parse_policy_arg(api: TournamentAPI, season: str, policy_arg: str) -> PolicyVersion:
    """Parse --policy argument and resolve to PolicyVersion."""
    if ":" in policy_arg:
        name, version_str = policy_arg.rsplit(":", 1)
        version = int(version_str.lstrip("v"))
    else:
        name = policy_arg
        version = None

    # First check user's own policies (includes non-leaderboard ones)
    my_policies = api.get_my_policies(season)
    # Then check all leaderboard policies (for other users' policies)
    leaderboard_policies = api.get_leaderboard_policies(season)

    # Combine: user's policies first (sorted by name, -version), then leaderboard
    seen_ids = {p.id for p in my_policies}
    all_policies = my_policies + [p for p in leaderboard_policies if p.id not in seen_ids]

    if version is not None:
        # Exact version requested
        for p in all_policies:
            if p.name == name and p.version == version:
                return p
    else:
        # No version specified - find the highest version for this policy name
        matching = [p for p in all_policies if p.name == name]
        if matching:
            return max(matching, key=lambda p: p.version)

    console.print(f"[red]Policy '{policy_arg}' not found in {season}.[/red]")
    sys.exit(1)


def parse_team_composition(assignments_str: str, policy_index: int) -> str:
    """Parse team composition from assignments string like '[0, 0, 0, 0, 1, 1, 1, 1]'."""
    try:
        assignments = ast.literal_eval(assignments_str)
        my_count = sum(1 for a in assignments if a == policy_index)
        opponent_count = len(assignments) - my_count
        return f"{my_count}v{opponent_count}"
    except Exception:
        return "?v?"


def aggregate_agent_metrics(
    agent_stats: list[dict], num_agents: int, policy_index: int, assignments: list[int]
) -> dict:
    """Aggregate metrics for agents belonging to our policy."""
    if not agent_stats:
        return {}

    # Find which agents belong to our policy based on assignments
    my_agent_indices = [i for i, a in enumerate(assignments) if a == policy_index]

    aggregated: dict[str, float] = {}
    for idx in my_agent_indices:
        if idx < len(agent_stats):
            agent = agent_stats[idx]
            for key, value in agent.items():
                if value is not None and isinstance(value, (int, float)):
                    aggregated[key] = aggregated.get(key, 0) + value

    return aggregated


def compute_derived_metrics(episodes: list[EpisodeData]) -> DerivedMetrics:
    """Compute policy-level KPIs from episode metrics."""
    if not episodes:
        return DerivedMetrics()

    # Aggregate all metrics across episodes
    totals: dict[str, float] = {}
    total_steps = 0
    completed_episodes = [e for e in episodes if e.status == "completed"]

    for ep in completed_episodes:
        total_steps += ep.steps
        for key, value in ep.metrics.items():
            if isinstance(value, (int, float)):
                totals[key] = totals.get(key, 0) + value

    n_episodes = len(completed_episodes) or 1

    # Helper to safely get metric
    def get(key: str, default: float = 0.0) -> float:
        return totals.get(key, default)

    # Helper for safe division
    def safe_div(a: float, b: float, default: float = 0.0) -> float:
        return a / b if b > 0 else default

    # === Efficiency KPIs ===
    move_success = get("action.move.success")
    move_failed = get("action.move.failed")
    move_efficiency = safe_div(move_success, move_success + move_failed)

    # Action success rate
    action_failed = get("action.failed")
    total_actions = sum(v for k, v in totals.items() if k.startswith("action.") and ".success" in k)
    total_actions += action_failed
    action_success_rate = safe_div(total_actions - action_failed, total_actions)

    # Vibe change rate (CogsGuard-specific action)
    vibe_change_success = get("action.change_vibe.success")
    vibe_change_rate = safe_div(vibe_change_success, total_actions)

    # === Resource KPIs ===
    # Sum all resource amounts and gained (real CogsGuard resources)
    resources = ["carbon", "heart", "oxygen", "silicon", "germanium"]
    total_amount = sum(get(f"{r}.amount") for r in resources)
    total_gained = sum(get(f"{r}.gained") for r in resources)
    resource_retention = safe_div(total_amount, total_gained)

    # === Vulnerability KPIs ===
    frozen_ticks = get("status.frozen.ticks")
    freeze_vulnerability = safe_div(frozen_ticks, total_steps) if total_steps > 0 else 0.0

    # === Junction KPIs ===
    junction_aligned = get("junction.aligned_by_agent")
    junction_scrambled = get("junction.scrambled_by_agent")
    junction_total = junction_aligned + junction_scrambled
    junction_control_rate = safe_div(junction_aligned, junction_total)

    # From collective stats (if available in agent metrics)
    aligned_gained = get("aligned.junction.gained", junction_aligned)
    aligned_lost = get("aligned.junction.lost")
    aligned_held = get("aligned.junction.held")
    alignment_stability = safe_div(aligned_held, aligned_gained) if aligned_gained > 0 else 0.0
    net_alignment_rate = safe_div(aligned_gained - aligned_lost, aligned_gained)

    # === Strategy Profile Scores (0-100) ===
    # Aggressive: high junction scrambling, high vibe changes
    profile_aggressive = min(100, (junction_scrambled / n_episodes) * 10 + (vibe_change_success / n_episodes) * 5)

    # Defensive: high noop, low movement
    noop_count = get("action.noop.success")
    move_rate = safe_div(move_success, move_success + noop_count)
    profile_defensive = min(100, (noop_count / n_episodes / 10) + (1 - move_rate) * 50)

    # Resource Hoarder: high deposits, high amounts
    profile_resource_hoarder = min(100, resource_retention * 50 + (total_amount / n_episodes / 10))

    # Junction Hunter: high junction activity
    profile_junction_hunter = min(100, (junction_aligned / n_episodes) * 3 + junction_control_rate * 50)

    # Mobile Scout: high move success, low noop
    noop_rate_profile = safe_div(noop_count, move_success + noop_count)
    profile_mobile_scout = min(100, move_efficiency * 50 + (1 - noop_rate_profile) * 50)

    # === New KPIs ===
    # Noop rate: noop / total_actions
    noop_rate = safe_div(noop_count, total_actions)

    # Resource efficiency per step: sum(resource.gained) / total_steps
    resource_efficiency_per_step = safe_div(total_gained, total_steps) if total_steps > 0 else 0.0

    # Hearts to junction rate: junction.aligned_by_agent / heart.lost
    heart_lost = get("heart.lost")
    hearts_to_junction_rate = safe_div(junction_aligned, heart_lost)

    # Reward consistency: 1 - (std/mean) clamped 0-1
    rewards = [e.reward for e in completed_episodes]
    if len(rewards) >= 2:
        mean_reward = statistics.mean(rewards)
        std_reward = statistics.stdev(rewards)
        if mean_reward > 0:
            reward_consistency = max(0.0, min(1.0, 1.0 - (std_reward / mean_reward)))
        else:
            reward_consistency = 0.0
    else:
        reward_consistency = 0.0

    # Avg reward
    avg_reward = safe_div(sum(rewards), len(rewards))

    # Reward nonzero pct: % episodes with reward > 0.1
    nonzero_count = sum(1 for r in rewards if r > 0.1)
    reward_nonzero_pct = safe_div(nonzero_count, len(rewards))

    # === Diagnostic Insights ===
    diagnostics: list[str] = []

    # High movement failures
    if move_efficiency < 0.7 and move_failed > n_episodes * 10:
        diagnostics.append("High movement failures - check pathfinding or obstacle handling")

    # Action timeouts
    action_timeout = get("action.timeout")
    if action_timeout > n_episodes * 5:
        timeout_per_ep = action_timeout / n_episodes
        diagnostics.append(f"Action timeouts detected ({timeout_per_ep:.1f}/ep) - policy may have latency issues")

    # Freeze vulnerability
    if freeze_vulnerability > 0.1:
        diagnostics.append(f"Spending {freeze_vulnerability * 100:.1f}% of time frozen - improve combat avoidance")

    # Low junction activity with heart activity
    heart_gained = get("heart.gained")
    if junction_aligned < n_episodes * 2 and heart_gained > n_episodes * 3:
        diagnostics.append("Hearts collected but low junction alignment - check aligner activation")

    # No vibe changes detected
    if vibe_change_success == 0 and n_episodes >= 5:
        diagnostics.append("No vibe changes detected - policy may not be using change_vibe action")

    # Resource loss
    total_lost = sum(get(f"{r}.lost") for r in resources)
    if total_lost > total_gained * 0.5:
        diagnostics.append("High resource loss - resources being lost faster than gained")

    # Early termination pattern
    avg_steps = total_steps / n_episodes if n_episodes > 0 else 0
    short_episodes = sum(1 for e in completed_episodes if e.steps < avg_steps * 0.5)
    if short_episodes > n_episodes * 0.2:
        diagnostics.append(f"{short_episodes} episodes terminated early - possible stability issues")

    # === Phase 3: New Diagnostics ===

    # High noop rate
    if noop_rate > 0.15 and noop_count > n_episodes * 100:
        diagnostics.append(f"High noop rate ({noop_rate * 100:.1f}%) - policy may be indecisive or stuck")

    # Matchup disparity
    by_opponent: dict[str, list[float]] = {}
    for e in completed_episodes:
        by_opponent.setdefault(e.opponent_name, []).append(e.reward)
    opponent_avgs = {opp: sum(rs) / len(rs) for opp, rs in by_opponent.items() if len(rs) >= 3}
    if opponent_avgs:
        best_avg = max(opponent_avgs.values())
        worst_avg = min(opponent_avgs.values())
        if best_avg > 2.0 and worst_avg < 0.5:
            best_opp = max(opponent_avgs, key=opponent_avgs.get)  # type: ignore[arg-type]
            worst_opp = min(opponent_avgs, key=opponent_avgs.get)  # type: ignore[arg-type]
            diagnostics.append(
                f"Matchup disparity - best avg {best_avg:.1f} vs {best_opp}, worst avg {worst_avg:.1f} vs {worst_opp}"
            )

    # Declining rewards (linear regression slope)
    if len(rewards) >= 10:
        n_r = len(rewards)
        x_mean = (n_r - 1) / 2.0
        y_mean = sum(rewards) / n_r
        numerator = sum((i - x_mean) * (rewards[i] - y_mean) for i in range(n_r))
        denominator = sum((i - x_mean) ** 2 for i in range(n_r))
        if denominator > 0:
            slope = numerator / denominator
            if slope < -0.05:
                diagnostics.append(f"Declining rewards (slope={slope:.3f}) - recent episodes scoring worse")

    # High freeze + low reward
    if len(completed_episodes) >= 5:
        avg_reward_all = sum(e.reward for e in completed_episodes) / n_episodes
        frozen_low_count = sum(
            1
            for e in completed_episodes
            if e.steps > 0
            and e.metrics.get("status.frozen.ticks", 0) / e.steps > 0.15
            and e.reward < avg_reward_all * 0.5
        )
        if frozen_low_count > n_episodes * 0.15:
            diagnostics.append(
                f"High freeze time and low reward in {frozen_low_count} episodes "
                f"({frozen_low_count / n_episodes * 100:.0f}%) - check combat avoidance"
            )

    # === Phase 4: Team comp red flag ===
    comp_rewards: dict[str, list[float]] = {}
    for e in completed_episodes:
        comp_rewards.setdefault(e.team_composition, []).append(e.reward)
    avg_6v2 = sum(comp_rewards.get("6v2", [0])) / max(len(comp_rewards.get("6v2", [0])), 1)
    avg_2v6 = sum(comp_rewards.get("2v6", [0])) / max(len(comp_rewards.get("2v6", [0])), 1)
    if avg_2v6 > 0 and avg_6v2 / avg_2v6 > 3.0 and len(comp_rewards.get("6v2", [])) >= 3:
        diagnostics.append(
            f"Over-reliance on agent count - 6v2 avg {avg_6v2:.1f} vs 2v6 avg {avg_2v6:.1f} "
            f"(ratio {avg_6v2 / avg_2v6:.1f}x)"
        )

    # === Phase 5: Zero-count detection ===
    # CogsGuard actions: move, noop, change_vibe
    capability_metrics = [
        "junction.aligned_by_agent",
        "junction.scrambled_by_agent",
        "action.change_vibe.success",
    ]
    zero_capabilities = []
    for metric in capability_metrics:
        if all(e.metrics.get(metric, 0) == 0 for e in completed_episodes):
            zero_capabilities.append(metric)
    if zero_capabilities:
        names = ", ".join(zero_capabilities)
        diagnostics.append(f"Unused capabilities (always zero): {names}")

    return DerivedMetrics(
        move_efficiency=move_efficiency,
        action_success_rate=action_success_rate,
        vibe_change_rate=vibe_change_rate,
        resource_retention=resource_retention,
        freeze_vulnerability=freeze_vulnerability,
        junction_control_rate=junction_control_rate,
        alignment_stability=alignment_stability,
        net_alignment_rate=net_alignment_rate,
        avg_reward=avg_reward,
        noop_rate=noop_rate,
        resource_efficiency_per_step=resource_efficiency_per_step,
        hearts_to_junction_rate=hearts_to_junction_rate,
        reward_consistency=reward_consistency,
        reward_nonzero_pct=reward_nonzero_pct,
        profile_aggressive=profile_aggressive,
        profile_defensive=profile_defensive,
        profile_resource_hoarder=profile_resource_hoarder,
        profile_junction_hunter=profile_junction_hunter,
        profile_mobile_scout=profile_mobile_scout,
        diagnostics=diagnostics,
    )


# === Phase 4: Team Composition Analysis ===


@dataclass
class TeamCompStats:
    """Per-composition KPI breakdown."""

    composition: str
    count: int
    avg_reward: float
    avg_move_efficiency: float
    avg_junction_aligned: float
    avg_resource_gained: float


def compute_team_comp_analysis(episodes: list[EpisodeData]) -> list[TeamCompStats]:
    """Compute per-composition KPI breakdown."""
    by_comp: dict[str, list[EpisodeData]] = {}
    for e in episodes:
        if e.status == "completed":
            by_comp.setdefault(e.team_composition, []).append(e)

    result = []
    for comp, eps in sorted(by_comp.items()):
        n = len(eps)
        avg_reward = sum(e.reward for e in eps) / n

        total_move_success = sum(e.metrics.get("action.move.success", 0) for e in eps)
        total_move_failed = sum(e.metrics.get("action.move.failed", 0) for e in eps)
        total_move = total_move_success + total_move_failed
        move_eff = total_move_success / total_move if total_move > 0 else 0

        avg_junction = sum(e.metrics.get("junction.aligned_by_agent", 0) for e in eps) / n

        resources = ["carbon", "heart", "oxygen", "silicon", "germanium"]
        avg_resource = sum(sum(e.metrics.get(f"{r}.gained", 0) for r in resources) for e in eps) / n

        result.append(
            TeamCompStats(
                composition=comp,
                count=n,
                avg_reward=round(avg_reward, 4),
                avg_move_efficiency=round(move_eff, 4),
                avg_junction_aligned=round(avg_junction, 4),
                avg_resource_gained=round(avg_resource, 4),
            )
        )

    return result


def result_to_episode_data(
    result_dict: dict,
    episode_id: str,
    assignments: list[int],
    policy_index: int = 0,
    opponent_name: str = "local",
    opponent_version: int = 0,
    job_id: str = "",
    status: str = "completed",
    error_type: str | None = None,
) -> EpisodeData:
    """Convert a PureSingleEpisodeResult dict into EpisodeData.

    Works for both tournament API attributes and local JSON result files.
    """
    # Team composition from assignments
    my_count = sum(1 for a in assignments if a == policy_index)
    opponent_count = len(assignments) - my_count
    team_comp = f"{my_count}v{opponent_count}" if assignments else "?v?"

    # Extract metrics from stats.agent
    stats = result_dict.get("stats", {})
    agent_stats = stats.get("agent", [])
    metrics = aggregate_agent_metrics(agent_stats, len(assignments), policy_index, assignments)

    # Extract collective stats with namespace prefix
    collective_stats = stats.get("collective", {})
    if isinstance(collective_stats, dict):
        for key, value in collective_stats.items():
            if value is not None and isinstance(value, (int, float)):
                metrics[f"collective.{key}"] = value

    # Extract game stats with namespace prefix
    game_stats = stats.get("game", {})
    if isinstance(game_stats, dict):
        for key, value in game_stats.items():
            if value is not None and isinstance(value, (int, float)):
                metrics[f"game.{key}"] = value

    # Reward: average over our agents
    rewards = result_dict.get("rewards", [])
    if rewards and assignments:
        my_agent_indices = [i for i, a in enumerate(assignments) if a == policy_index]
        my_rewards = [rewards[i] for i in my_agent_indices if i < len(rewards)]
        reward = sum(my_rewards) / len(my_rewards) if my_rewards else 0.0
    else:
        reward = 0.0

    steps = result_dict.get("steps", 0)

    return EpisodeData(
        episode_id=episode_id,
        job_id=job_id,
        opponent_name=opponent_name,
        opponent_version=opponent_version,
        team_composition=team_comp,
        reward=reward,
        status=status,
        error_type=error_type,
        steps=steps,
        metrics=metrics,
    )


def fetch_dashboard_data(
    api: TournamentAPI,
    policy: PolicyVersion,
    season: str,
    limit: int,
) -> DashboardData:
    """Fetch all data needed for dashboard."""
    episodes_data: list[EpisodeData] = []

    # Cache for opponent policy info
    opponent_cache: dict[str, dict] = {}

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        # Fetch episodes using query API
        task = progress.add_task("Fetching episodes...", total=None)
        raw_episodes = api.query_episodes(policy.id, limit)
        progress.update(task, completed=True, total=1)

        if not raw_episodes:
            console.print("[yellow]No episodes found for this policy.[/yellow]")
            return DashboardData(
                policy=policy,
                episodes=[],
                season=season,
                generated_at=datetime.now().isoformat(),
            )

        # Process each episode
        task = progress.add_task("Processing episodes...", total=len(raw_episodes))
        for ep in raw_episodes:
            episode_id = ep.get("id", "")
            job_id = ep.get("job_id") or ep.get("tags", {}).get("job_id", "")

            # Get reward from avg_rewards (pre-computed by tournament API)
            avg_rewards = ep.get("avg_rewards", {})
            my_reward = avg_rewards.get(policy.id, 0.0) or 0.0

            # Find opponent (the other policy in avg_rewards)
            opponent_id = None
            for pv_id in avg_rewards:
                if pv_id != policy.id:
                    opponent_id = pv_id
                    break

            # Look up opponent name (with caching)
            opponent_name = "unknown"
            opponent_version = 0
            if opponent_id:
                if opponent_id not in opponent_cache:
                    opp_info = api.get_policy_version(opponent_id)
                    if opp_info:
                        opponent_cache[opponent_id] = opp_info
                if opponent_id in opponent_cache:
                    opp = opponent_cache[opponent_id]
                    opponent_name = opp.get("name", "unknown")
                    opponent_version = opp.get("version", 0)

            # Parse team composition and policy index from tags
            tags = ep.get("tags", {})
            assignments_str = tags.get("assignments", "[]")
            try:
                assignments = ast.literal_eval(assignments_str)
            except Exception:
                assignments = []

            policy_index = 0
            policy_version_ids_str = tags.get("policy_version_ids", "")
            if policy_version_ids_str and assignments:
                try:
                    policy_version_ids_list = ast.literal_eval(policy_version_ids_str)
                    if policy.id in policy_version_ids_list:
                        policy_index = policy_version_ids_list.index(policy.id)
                except Exception:
                    pass

            # Convert using shared helper (attributes holds the result dict)
            attributes = ep.get("attributes", {})
            episode = result_to_episode_data(
                result_dict=attributes,
                episode_id=episode_id,
                assignments=assignments,
                policy_index=policy_index,
                opponent_name=opponent_name,
                opponent_version=opponent_version,
                job_id=job_id,
            )
            # Override reward with the API's pre-computed avg_rewards
            episode.reward = my_reward

            episodes_data.append(episode)
            progress.advance(task)

    derived = compute_derived_metrics(episodes_data)

    return DashboardData(
        policy=policy,
        episodes=episodes_data,
        season=season,
        generated_at=datetime.now().isoformat(),
        derived=derived,
    )


def load_local_results(results_dir: Path, policy_name: str, limit: int) -> DashboardData:
    """Load episode results from local JSON files.

    Each JSON file should be a PureSingleEpisodeResult dict with at least
    'rewards', 'stats', and optionally 'steps' keys.
    """
    json_files = sorted(results_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)

    if not json_files:
        console.print(f"[yellow]No JSON files found in {results_dir}[/yellow]")
        return DashboardData(
            policy=PolicyVersion(id="local", name=policy_name, version=0),
            episodes=[],
            season="local",
            generated_at=datetime.now().isoformat(),
        )

    if len(json_files) > limit:
        json_files = json_files[:limit]

    episodes: list[EpisodeData] = []
    skipped = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Loading local results...", total=len(json_files))
        for json_file in json_files:
            try:
                with open(json_file) as f:
                    result = json.load(f)

                # Validate expected shape
                if not isinstance(result, dict) or "rewards" not in result or "stats" not in result:
                    console.print(f"[dim yellow]Skipping {json_file.name}: missing rewards/stats keys[/dim yellow]")
                    skipped += 1
                    progress.advance(task)
                    continue

                # Read optional metadata for opponents, team composition, and status
                rewards = result.get("rewards", [])
                num_agents = len(rewards) if rewards else 1

                # Support custom assignments for team compositions (e.g., [0,0,1,1] for 2v2)
                # Default: all agents belong to policy 0
                assignments = result.get("_assignments", [0] * num_agents)

                # Optional opponent info
                opponent_name = result.get("_opponent_name", "none")
                opponent_version = result.get("_opponent_version", 0)

                # Optional status and error info
                status = result.get("_status", "completed")
                error_type = result.get("_error_type")

                episode = result_to_episode_data(
                    result_dict=result,
                    episode_id=json_file.stem,
                    assignments=assignments,
                    policy_index=0,
                    opponent_name=opponent_name,
                    opponent_version=opponent_version,
                    status=status,
                    error_type=error_type,
                )
                episodes.append(episode)
            except (json.JSONDecodeError, OSError) as e:
                console.print(f"[dim yellow]Skipping {json_file.name}: {e}[/dim yellow]")
                skipped += 1
            progress.advance(task)

    if skipped:
        console.print(f"[yellow]Skipped {skipped} file(s)[/yellow]")

    derived = compute_derived_metrics(episodes)

    return DashboardData(
        policy=PolicyVersion(id="local", name=policy_name, version=0),
        episodes=episodes,
        season="local",
        generated_at=datetime.now().isoformat(),
        derived=derived,
    )


def load_demo_data() -> dict:
    """Load static demo data from demo_dashboard.json.

    Returns the pre-computed data dict directly (no DashboardData round-trip needed).
    """
    demo_path = Path(__file__).parent / "demo_dashboard.json"
    with open(demo_path) as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(description="Generate tournament policy dashboard")
    parser.add_argument("--policy", help="Policy to analyze (name:version or name)")
    parser.add_argument("--limit", type=int, default=100, help="Max episodes to fetch")
    parser.add_argument("--output", help="Output HTML file path")
    parser.add_argument("--season", default=DEFAULT_SEASON, help="Tournament season")
    parser.add_argument("--local-results", help="Directory of episode result JSON files (local mode)")
    parser.add_argument("--policy-name", help="Policy name for local mode (default: directory name)")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Generate dashboard with sample data to demonstrate features",
    )
    parser.add_argument("--claude", action="store_true", help="Include Claude AI analysis (adds 10-30s)")
    parser.add_argument("--claude-model", default="sonnet", help="Model for analysis (default: sonnet)")
    args = parser.parse_args()

    console.print("[bold blue]CoGames Policy Dashboard Generator[/bold blue]\n")

    if args.demo:
        # Demo mode - load static demo data
        console.print("[bold magenta]Demo mode:[/bold magenta] Loading demo data...\n")
        demo_dict = load_demo_data()
        policy = demo_dict["policy"]
        console.print(f"[green]Loaded {len(demo_dict['episodes'])} demo episodes[/green]")
        console.print(f"  Policy: {policy['name']}:v{policy['version']}")

        # Generate dashboard
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = args.output or f"cg_dashboard_demo_{timestamp}.html"
        output_path = Path(output_path)

        console.print("\n[bold]Generating dashboard...[/bold]")
        generate_dashboard_from_dict(demo_dict, output_path)

        console.print(f"\n[bold green]Dashboard saved to:[/bold green] {output_path}")
        console.print("[dim]Opening in browser...[/dim]")
        webbrowser.open(f"file://{output_path.absolute()}")

    elif args.local_results:
        # Local mode - no auth needed
        results_dir = Path(args.local_results)
        if not results_dir.is_dir():
            console.print(f"[red]Not a directory: {results_dir}[/red]")
            sys.exit(1)

        policy_name = args.policy_name or results_dir.name
        console.print(f"[green]Local mode:[/green] {results_dir}")
        console.print(f"  Policy name: {policy_name}")

        data = load_local_results(results_dir, policy_name, args.limit)
        console.print(f"\n[green]Loaded {len(data.episodes)} episodes[/green]")

        claude_analysis = None
        if args.claude:
            claude_analysis = run_claude_analysis(data, args.claude_model)

        # Generate dashboard
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = args.output or f"cg_dashboard_{policy_name}_local_{timestamp}.html"
        output_path = Path(output_path)

        console.print("\n[bold]Generating dashboard...[/bold]")
        generate_dashboard(data, output_path, claude_analysis=claude_analysis)

        console.print(f"\n[bold green]Dashboard saved to:[/bold green] {output_path}")
        console.print("[dim]Opening in browser...[/dim]")
        webbrowser.open(f"file://{output_path.absolute()}")
    else:
        # Tournament mode (existing behavior)
        token = get_auth_token()
        api = TournamentAPI(token)

        try:
            # Select policy
            if args.policy:
                policy = parse_policy_arg(api, args.season, args.policy)
            else:
                policy = select_policy_interactive(api, args.season)

            console.print(f"\n[green]Selected:[/green] {policy.name}:v{policy.version}")
            if policy.rank:
                console.print(f"  Rank: #{policy.rank}, Score: {policy.score:.3f}, Matches: {policy.matches}")

            # Fetch data
            console.print(f"\n[bold]Fetching episode data (limit: {args.limit})...[/bold]")
            data = fetch_dashboard_data(api, policy, args.season, args.limit)

            console.print(f"\n[green]Fetched {len(data.episodes)} episodes[/green]")

            claude_analysis = None
            if args.claude:
                claude_analysis = run_claude_analysis(data, args.claude_model)

            # Generate dashboard
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = args.output or f"cg_dashboard_{policy.name}_v{policy.version}_{timestamp}.html"
            output_path = Path(output_path)

            console.print("\n[bold]Generating dashboard...[/bold]")
            generate_dashboard(data, output_path, claude_analysis=claude_analysis)

            console.print(f"\n[bold green]Dashboard saved to:[/bold green] {output_path}")
            console.print("[dim]Opening in browser...[/dim]")
            webbrowser.open(f"file://{output_path.absolute()}")

        finally:
            api.close()


def generate_dashboard(data: DashboardData, output_path: Path, claude_analysis: str | None = None) -> None:
    """Generate HTML dashboard from DashboardData."""
    data_dict = data_to_dict(data)
    if claude_analysis:
        data_dict["claude_analysis"] = claude_analysis
    generate_dashboard_from_dict(data_dict, output_path)


def generate_dashboard_from_dict(data_dict: dict, output_path: Path) -> None:
    """Generate HTML dashboard from a pre-built data dict."""
    template_path = Path(__file__).parent / "template.html"
    if not template_path.exists():
        console.print("[red]Template not found.[/red]")
        sys.exit(1)
    with open(template_path) as f:
        template = f.read()
    html = template.replace("{{DASHBOARD_DATA}}", json.dumps(data_dict, indent=2))
    with open(output_path, "w") as f:
        f.write(html)


def data_to_dict(data: DashboardData) -> dict:
    """Convert DashboardData to JSON-serializable dict."""
    return {
        "policy": {
            "id": data.policy.id,
            "name": data.policy.name,
            "version": data.policy.version,
            "rank": data.policy.rank,
            "score": data.policy.score,
            "matches": data.policy.matches,
        },
        "episodes": [
            {
                "episode_id": e.episode_id,
                "job_id": e.job_id,
                "opponent_name": e.opponent_name,
                "opponent_version": e.opponent_version,
                "team_composition": e.team_composition,
                "reward": e.reward,
                "status": e.status,
                "error_type": e.error_type,
                "steps": e.steps,
                "metrics": e.metrics,
            }
            for e in data.episodes
        ],
        "season": data.season,
        "generated_at": data.generated_at,
        "derived": {
            "strategy_profile": {
                "aggressive": data.derived.profile_aggressive,
                "defensive": data.derived.profile_defensive,
                "resource_hoarder": data.derived.profile_resource_hoarder,
                "junction_hunter": data.derived.profile_junction_hunter,
                "mobile_scout": data.derived.profile_mobile_scout,
            },
            "diagnostics": data.derived.diagnostics,
            "team_comp": [
                {
                    "composition": tc.composition,
                    "count": tc.count,
                    "avg_reward": tc.avg_reward,
                    "avg_move_efficiency": tc.avg_move_efficiency,
                    "avg_junction_aligned": tc.avg_junction_aligned,
                    "avg_resource_gained": tc.avg_resource_gained,
                }
                for tc in compute_team_comp_analysis(data.episodes)
            ],
            "opponent_metrics": _compute_opponent_metrics(data.episodes),
        },
    }


_CORRELATION_METRICS = [
    "action.move.success",
    "action.move.failed",
    "action.noop.success",
    "junction.aligned_by_agent",
    "junction.scrambled_by_agent",
    "status.frozen.ticks",
    "heart.gained",
    "carbon.gained",
    "action.change_vibe.success",
]


def _build_snapshot(ep: EpisodeData) -> dict[str, Any]:
    """Build a compact snapshot of an episode."""
    m = ep.metrics
    return {
        "id": ep.episode_id[:8],
        "opp": ep.opponent_name,
        "comp": ep.team_composition,
        "r": round(ep.reward, 2),
        "steps": ep.steps,
        "mv_s": round(m.get("action.move.success", 0)),
        "mv_f": round(m.get("action.move.failed", 0)),
        "noop": round(m.get("action.noop.success", 0)),
        "frz": round(m.get("status.frozen.ticks", 0)),
        "j_aln": round(m.get("junction.aligned_by_agent", 0)),
    }


def _compute_episode_logs(completed: list[EpisodeData]) -> dict[str, Any]:
    """Compute episode-level stats for Claude analysis."""
    if not completed:
        return {}

    # Reward-metric correlations
    n = len(completed)
    rewards = [e.reward for e in completed]
    correlations: dict[str, float] = {}
    if n >= 5:
        mean_r = sum(rewards) / n
        for metric in _CORRELATION_METRICS:
            vals = [e.metrics.get(metric, 0.0) for e in completed]
            mean_v = sum(vals) / n
            cov = sum((rewards[i] - mean_r) * (vals[i] - mean_v) for i in range(n))
            var_r = sum((rewards[i] - mean_r) ** 2 for i in range(n))
            var_v = sum((vals[i] - mean_v) ** 2 for i in range(n))
            denom = (var_r * var_v) ** 0.5
            if denom > 0:
                correlations[metric] = round(cov / denom, 4)

    # Top vs bottom
    sorted_eps = sorted(completed, key=lambda e: e.reward)
    bottom_n = max(1, n // 5)
    top_n = max(1, n // 5)
    bottom = sorted_eps[:bottom_n]
    top = sorted_eps[-top_n:]

    def avg_metrics(eps: list[EpisodeData]) -> dict[str, float]:
        if not eps:
            return {}
        agg: dict[str, float] = {}
        for e in eps:
            for k, v in e.metrics.items():
                if isinstance(v, (int, float)):
                    agg[k] = agg.get(k, 0) + v
        count = len(eps)
        return {k: round(v / count, 2) for k, v in agg.items()}

    top_vs_bottom = {
        "top_20_avg_reward": round(sum(e.reward for e in top) / len(top), 4),
        "bottom_20_avg_reward": round(sum(e.reward for e in bottom) / len(bottom), 4),
        "top_20_metrics": avg_metrics(top),
        "bottom_20_metrics": avg_metrics(bottom),
    }

    # Episode snapshots
    seen_ids: set[str] = set()
    snapshots: list[dict] = []

    def add_episodes(eps: list[EpisodeData], label: str, max_count: int):
        for e in eps:
            if e.episode_id not in seen_ids and len(snapshots) < 16:
                seen_ids.add(e.episode_id)
                snap = _build_snapshot(e)
                snap["bucket"] = label
                snapshots.append(snap)
                if sum(1 for s in snapshots if s["bucket"] == label) >= max_count:
                    break

    add_episodes(sorted_eps[-5:][::-1], "top", 5)
    add_episodes(sorted_eps[:5], "bottom", 5)

    by_opp: dict[str, list[EpisodeData]] = {}
    for e in completed:
        by_opp.setdefault(e.opponent_name, []).append(e)
    opp_avgs = {opp: sum(e.reward for e in eps) / len(eps) for opp, eps in by_opp.items() if len(eps) >= 2}
    if opp_avgs:
        worst_opp = min(opp_avgs, key=opp_avgs.get)  # type: ignore[arg-type]
        worst_opp_eps = sorted(by_opp[worst_opp], key=lambda e: e.reward)
        add_episodes(worst_opp_eps[:3], "worst_matchup", 3)

    by_freeze = sorted(completed, key=lambda e: e.metrics.get("status.frozen.ticks", 0), reverse=True)
    add_episodes(by_freeze[:3], "outlier", 3)

    return {
        "reward_correlations": correlations,
        "top_vs_bottom": top_vs_bottom,
        "episode_snapshots": snapshots,
    }


def build_analysis_summary(data: DashboardData) -> dict:
    """Build compact summary of derived metrics for Claude analysis.

    Excludes raw episode data and per-episode metrics to stay under 20KB.
    """
    completed = [e for e in data.episodes if e.status == "completed"]
    rewards = [e.reward for e in completed]

    # Per-opponent summary
    by_opponent: dict[str, list[EpisodeData]] = {}
    for e in completed:
        by_opponent.setdefault(e.opponent_name, []).append(e)

    opponent_summary = {}
    for opp, eps in by_opponent.items():
        opp_rewards = [e.reward for e in eps]
        # Compute opponent's strategy profile from avg metrics
        avg_m: dict[str, float] = {}
        for e in eps:
            for k, v in e.metrics.items():
                if isinstance(v, (int, float)):
                    avg_m[k] = avg_m.get(k, 0) + v
        n = len(eps)
        avg_m = {k: v / n for k, v in avg_m.items()}

        move_s = avg_m.get("action.move.success", 0)
        move_f = avg_m.get("action.move.failed", 0)
        noop = avg_m.get("action.noop.success", 0)
        vibe = avg_m.get("action.change_vibe.success", 0)
        j_aligned = avg_m.get("junction.aligned_by_agent", 0)
        j_scrambled = avg_m.get("junction.scrambled_by_agent", 0)
        j_total = j_aligned + j_scrambled
        move_rate = move_s / (move_s + noop) if (move_s + noop) > 0 else 0
        noop_rate_p = noop / (move_s + noop) if (move_s + noop) > 0 else 0
        move_eff = move_s / (move_s + move_f) if (move_s + move_f) > 0 else 0
        j_control = j_aligned / j_total if j_total > 0 else 0

        opp_entry: dict[str, Any] = {
            "count": n,
            "avg_reward": round(sum(opp_rewards) / n, 4),
            "strategy_profile": {
                "aggressive": round(min(100, j_scrambled * 10 + vibe * 5), 2),
                "defensive": round(min(100, noop / 10 + (1 - move_rate) * 50), 2),
                "junction_hunter": round(min(100, j_aligned * 3 + j_control * 50), 2),
                "mobile_scout": round(min(100, move_eff * 50 + (1 - noop_rate_p) * 50), 2),
            },
        }
        if n >= 2:
            opp_entry["reward_std"] = round(statistics.stdev(opp_rewards), 4)
        if n >= 4:
            mid = n // 2
            first_half_avg = sum(opp_rewards[:mid]) / mid
            second_half_avg = sum(opp_rewards[mid:]) / (n - mid)
            opp_entry["temporal"] = {
                "first_half_avg": round(first_half_avg, 4),
                "second_half_avg": round(second_half_avg, 4),
            }
        opponent_summary[opp] = opp_entry

    # Team comp stats
    team_comp_summary = {}
    for e in completed:
        team_comp_summary.setdefault(e.team_composition, []).append(e.reward)
    team_comp = {
        comp: {"count": len(rs), "avg_reward": round(sum(rs) / len(rs), 4)} for comp, rs in team_comp_summary.items()
    }

    # Reward distribution stats
    reward_stats = {}
    if rewards:
        reward_stats = {
            "mean": round(statistics.mean(rewards), 4),
            "median": round(statistics.median(rewards), 4),
            "min": round(min(rewards), 4),
            "max": round(max(rewards), 4),
            "p25": round(sorted(rewards)[len(rewards) // 4], 4),
            "p75": round(sorted(rewards)[3 * len(rewards) // 4], 4),
        }
        if len(rewards) >= 2:
            reward_stats["std"] = round(statistics.stdev(rewards), 4)

    # Episode logs
    episode_logs = _compute_episode_logs(completed)

    d = data.derived
    result: dict[str, Any] = {
        "policy": {
            "name": data.policy.name,
            "version": data.policy.version,
            "rank": data.policy.rank,
            "score": data.policy.score,
            "matches": data.policy.matches,
        },
        "episode_count": len(data.episodes),
        "completed_count": len(completed),
        "season": data.season,
        "kpis": {
            "avg_reward": round(d.avg_reward, 4),
            "move_efficiency": round(d.move_efficiency, 4),
            "action_success_rate": round(d.action_success_rate, 4),
            "vibe_change_rate": round(d.vibe_change_rate, 4),
            "resource_retention": round(d.resource_retention, 4),
            "freeze_vulnerability": round(d.freeze_vulnerability, 4),
            "junction_control_rate": round(d.junction_control_rate, 4),
            "alignment_stability": round(d.alignment_stability, 4),
            "net_alignment_rate": round(d.net_alignment_rate, 4),
            "noop_rate": round(d.noop_rate, 4),
            "resource_efficiency_per_step": round(d.resource_efficiency_per_step, 4),
            "hearts_to_junction_rate": round(d.hearts_to_junction_rate, 4),
            "reward_consistency": round(d.reward_consistency, 4),
            "reward_nonzero_pct": round(d.reward_nonzero_pct, 4),
        },
        "strategy_profile": {
            "aggressive": round(d.profile_aggressive, 2),
            "defensive": round(d.profile_defensive, 2),
            "resource_hoarder": round(d.profile_resource_hoarder, 2),
            "junction_hunter": round(d.profile_junction_hunter, 2),
            "mobile_scout": round(d.profile_mobile_scout, 2),
        },
        "diagnostics": d.diagnostics,
        "team_comp": team_comp,
        "opponents": opponent_summary,
        "reward_distribution": reward_stats,
    }
    if episode_logs:
        result["episode_logs"] = episode_logs
    return result


def _build_analysis_prompt(summary: dict) -> str:
    """Build the Claude analysis prompt with embedded guide and summary data."""
    guide_path = Path(__file__).parent / "analysis-guide.md"
    guide_text = guide_path.read_text()

    summary_json = json.dumps(summary, indent=2)

    sections = [
        "You are a CoGames tournament policy analyst.",
        "Analyze the following policy performance data and provide strategic advice.",
        "",
        "## Reference Guide",
        "",
        guide_text,
        "",
        "## Policy Performance Summary",
        "",
        f"```json\n{summary_json}\n```",
        "",
        "## Instructions",
        "",
        "Produce a markdown analysis with exactly these"
        " 4 sections. Do NOT repeat diagnostic messages"
        " verbatim — synthesize them into root causes"
        " and actionable advice.",
        "",
        "### Root Cause Analysis",
        "Connect multiple diagnostics and metrics to"
        " identify underlying causes. Look for patterns"
        " across KPIs, matchups, and team compositions"
        " that point to the same root issue."
        " Ground in specific episodes from episode_snapshots."
        " If replay_summaries exist, identify when in the"
        " game problems emerge (early vs late)."
        " Cite top_vs_bottom metric gaps.",
        "",
        "### Top 3 Training Priorities",
        "Rank by expected ROI. For each priority, specify"
        " concrete changes: reward shaping adjustments,"
        " curriculum modifications, hyperparameter changes,"
        " or architectural improvements."
        " Use reward_correlations to justify which metrics"
        " yield highest ROI. If reward_shape is frontloaded,"
        " suggest late-game incentives.",
        "",
        "### Opponent Adaptation",
        "For low-performing matchups, analyze the"
        " opponent's strategy profile and suggest"
        " counter-strategies. If no matchup data exists,"
        " skip this section."
        " Use per-opponent temporal trends to note if"
        " opponents are adapting over time.",
        "",
        "### Policy Narrative",
        "A plain-language description (2-3 sentences) of"
        ' what this policy "feels like" — its personality,'
        " strengths, and blind spots. Write this for"
        " someone who hasn't seen the data."
        " Reference replay temporal patterns to describe"
        " the policy's game rhythm.",
    ]
    return "\n".join(sections)


def _fetch_replay_summaries(summary: dict) -> list[dict]:
    """Fetch and summarize replays for selected episodes (sync, for CLI)."""
    from metta.app_backend.replay.summarizer import (  # noqa: PLC0415
        parse_replay,
        select_replay_episodes,
        summarize_replay,
    )

    episode_logs = summary.get("episode_logs")
    if not episode_logs:
        return []
    snapshots = episode_logs.get("episode_snapshots", [])
    episodes = []
    for snap in snapshots:
        replay_url = snap.get("replay_url")
        if replay_url:
            episodes.append(
                {
                    "reward": snap.get("r", 0),
                    "replay_url": replay_url,
                    "episode_id": snap.get("id", ""),
                }
            )
    selected = select_replay_episodes(episodes, max_n=3)
    if not selected:
        return []

    try:
        from mettagrid.util.file import read as file_read  # noqa: PLC0415
    except ImportError:
        console.print("[dim]mettagrid not available — skipping replay fetch[/dim]")
        return []

    summaries = []
    for ep in selected:
        try:
            data = file_read(ep["replay_url"])
            replay = parse_replay(data)
            num_agents = replay.get("num_agents", 0)
            agent_indices = list(range(num_agents // 2)) if num_agents > 0 else []
            result = summarize_replay(
                replay,
                agent_indices=agent_indices,
                episode_idx=ep.get("index", 0),
                reward=ep.get("reward", 0),
                reason=ep.get("reason", "unknown"),
            )
            if result:
                summaries.append(result.model_dump())
        except Exception as e:
            console.print(f"[dim]Failed to process replay: {e}[/dim]")
    return summaries


def run_claude_analysis(data: DashboardData, model: str) -> str | None:
    """Run Claude analysis on policy data. Returns markdown string or None."""
    if not shutil.which("claude"):
        console.print(
            "[yellow]Claude CLI not found — skipping AI analysis. Install from https://claude.ai/code[/yellow]"
        )
        return None

    summary = build_analysis_summary(data)

    # Fetch replay summaries
    replay_summaries = _fetch_replay_summaries(summary)
    if replay_summaries:
        summary["replay_summaries"] = replay_summaries
        console.print(f"[green]Added {len(replay_summaries)} replay summaries[/green]")

    prompt = _build_analysis_prompt(summary)

    console.print(f"[bold]Running Claude analysis ({model})...[/bold]")
    result = subprocess.run(
        ["claude", "-p", "--model", model, "--output-format", "json", prompt],
        capture_output=True,
        text=True,
        timeout=300,
    )

    if result.returncode != 0:
        console.print(f"[yellow]Claude analysis failed (exit {result.returncode}) — skipping[/yellow]")
        if result.stderr:
            console.print(f"[dim]{result.stderr.strip()}[/dim]")
        return None

    parsed = json.loads(result.stdout)
    return parsed["result"]


def _compute_opponent_metrics(episodes: list[EpisodeData]) -> dict[str, Any]:
    """Pre-compute per-opponent metric aggregation."""
    by_opponent: dict[str, list[EpisodeData]] = {}
    for e in episodes:
        if e.status == "completed":
            by_opponent.setdefault(e.opponent_name, []).append(e)

    result = {}
    for opp, eps in by_opponent.items():
        n = len(eps)
        total_reward = sum(e.reward for e in eps)
        avg_reward = total_reward / n
        summed_metrics: dict[str, float] = {}
        for e in eps:
            for k, v in e.metrics.items():
                if isinstance(v, (int, float)):
                    summed_metrics[k] = summed_metrics.get(k, 0) + v

        avg_metrics = {k: v / n for k, v in summed_metrics.items()}

        # Compute strategy profile scores (same formulas as target policy)
        m = avg_metrics
        move_s = m.get("action.move.success", 0)
        move_f = m.get("action.move.failed", 0)
        noop = m.get("action.noop.success", 0)
        vibe = m.get("action.change_vibe.success", 0)
        j_aligned = m.get("junction.aligned_by_agent", 0)
        j_scrambled = m.get("junction.scrambled_by_agent", 0)
        j_total = j_aligned + j_scrambled
        resources = ["carbon", "heart", "oxygen", "silicon", "germanium"]
        total_amount = sum(m.get(f"{r}.amount", 0) for r in resources)
        total_gained = sum(m.get(f"{r}.gained", 0) for r in resources)
        resource_retention = total_amount / total_gained if total_gained > 0 else 0
        move_eff = move_s / (move_s + move_f) if (move_s + move_f) > 0 else 0
        j_control = j_aligned / j_total if j_total > 0 else 0
        move_rate = move_s / (move_s + noop) if (move_s + noop) > 0 else 0
        noop_rate_p = noop / (move_s + noop) if (move_s + noop) > 0 else 0

        result[opp] = {
            "count": n,
            "total_reward": round(total_reward, 4),
            "avg_reward": round(avg_reward, 4),
            "avg_metrics": {k: round(v, 4) for k, v in avg_metrics.items()},
            "strategy_profile": {
                "aggressive": round(min(100, j_scrambled * 10 + vibe * 5), 2),
                "defensive": round(min(100, noop / 10 + (1 - move_rate) * 50), 2),
                "resource_hoarder": round(min(100, resource_retention * 50 + total_amount / 10), 2),
                "junction_hunter": round(min(100, j_aligned * 3 + j_control * 50), 2),
                "mobile_scout": round(min(100, move_eff * 50 + (1 - noop_rate_p) * 50), 2),
            },
        }

    return result


if __name__ == "__main__":
    main()
