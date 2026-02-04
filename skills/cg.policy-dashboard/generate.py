#!/usr/bin/env python3
"""Generate tournament policy dashboard.

Usage:
    python generate.py [--policy NAME:VERSION] [--limit N] [--output PATH] [--season SEASON]
"""

from __future__ import annotations

import argparse
import ast
import json
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
class DashboardData:
    """All data needed for dashboard."""

    policy: PolicyVersion
    episodes: list[EpisodeData]
    season: str
    generated_at: str


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

    def get_my_policies(self, season: str) -> list[PolicyVersion]:
        """Get user's policies in a season with leaderboard info."""
        # Get leaderboard for ranks/scores
        leaderboard = self.client.get(f"/tournament/seasons/{season}/leaderboard").json()
        lb_map = {entry["policy"]["id"]: entry for entry in leaderboard}

        # Get user's policies
        resp = self.client.get(
            f"/tournament/seasons/{season}/policies",
            params={"mine": "true"},
        )
        policies = resp.json()

        result = []
        for p in policies:
            # API returns SeasonPolicyEntry with nested policy field
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
            resp = self.client.get(f"/stats/policies/versions/{policy_version_id}")
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
    """Interactive policy selection."""
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

    policies = api.get_my_policies(season)
    for p in policies:
        if p.name == name and (version is None or p.version == version):
            return p

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

            # Get reward from avg_rewards
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

            # Parse team composition from tags
            tags = ep.get("tags", {})
            assignments_str = tags.get("assignments", "[]")
            try:
                assignments = ast.literal_eval(assignments_str)
            except Exception:
                assignments = []

            # Determine which policy index is ours
            # The assignments array uses indices into the original policy_version_ids list
            # which was ordered when the episode was recorded. We check for a
            # policy_version_ids tag first; if not present, we assume the primary/queried
            # policy was index 0 (first in the list when the job was created).
            policy_index = 0  # Default: primary policy is typically first
            policy_version_ids_str = tags.get("policy_version_ids", "")
            if policy_version_ids_str and assignments:
                try:
                    policy_version_ids_list = ast.literal_eval(policy_version_ids_str)
                    if policy.id in policy_version_ids_list:
                        policy_index = policy_version_ids_list.index(policy.id)
                except Exception:
                    pass  # Fall back to default assumption

            team_comp = parse_team_composition(assignments_str, policy_index)

            # Extract metrics from attributes.stats
            attributes = ep.get("attributes", {})
            stats = attributes.get("stats", {})
            agent_stats = stats.get("agent", [])

            # Aggregate agent metrics for our policy's agents (collective stats)
            metrics = aggregate_agent_metrics(agent_stats, len(assignments), policy_index, assignments)

            # Status - episodes in query result are completed (they have stats)
            status = "completed"

            episodes_data.append(
                EpisodeData(
                    episode_id=episode_id,
                    job_id=job_id,
                    opponent_name=opponent_name,
                    opponent_version=opponent_version,
                    team_composition=team_comp,
                    reward=my_reward,
                    status=status,
                    error_type=None,
                    steps=0,  # Not available in this API
                    metrics=metrics,
                )
            )
            progress.advance(task)

    return DashboardData(
        policy=policy,
        episodes=episodes_data,
        season=season,
        generated_at=datetime.now().isoformat(),
    )


def main():
    parser = argparse.ArgumentParser(description="Generate tournament policy dashboard")
    parser.add_argument("--policy", help="Policy to analyze (name:version or name)")
    parser.add_argument("--limit", type=int, default=100, help="Max episodes to fetch")
    parser.add_argument("--output", help="Output HTML file path")
    parser.add_argument("--season", default=DEFAULT_SEASON, help="Tournament season")
    args = parser.parse_args()

    console.print("[bold blue]CoGames Policy Dashboard Generator[/bold blue]\n")

    # Authenticate
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

        # Generate dashboard
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = args.output or f"cg_dashboard_{policy.name}_v{policy.version}_{timestamp}.html"
        output_path = Path(output_path)

        console.print("\n[bold]Generating dashboard...[/bold]")
        generate_dashboard(data, output_path)

        console.print(f"\n[bold green]Dashboard saved to:[/bold green] {output_path}")
        console.print("[dim]Opening in browser...[/dim]")
        webbrowser.open(f"file://{output_path.absolute()}")

    finally:
        api.close()


def generate_dashboard(data: DashboardData, output_path: Path) -> None:
    """Generate HTML dashboard from data."""
    # Load template and inject data
    template_path = Path(__file__).parent / "template.html"
    if not template_path.exists():
        console.print("[red]Template not found. Creating minimal dashboard.[/red]")
        html = create_minimal_dashboard(data)
    else:
        with open(template_path) as f:
            template = f.read()
        html = template.replace("{{DASHBOARD_DATA}}", json.dumps(data_to_dict(data), indent=2))

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
    }


def create_minimal_dashboard(data: DashboardData) -> str:
    """Create minimal dashboard if template missing."""
    return f"""<!DOCTYPE html>
<html><head><title>Dashboard - {data.policy.name}:v{data.policy.version}</title></head>
<body>
<h1>{data.policy.name}:v{data.policy.version}</h1>
<p>Episodes: {len(data.episodes)}</p>
<pre>{json.dumps(data_to_dict(data), indent=2)}</pre>
</body></html>
"""


if __name__ == "__main__":
    main()
