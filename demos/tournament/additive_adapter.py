"""Additive scoring adapter for the generic tournament framework.

This module provides a simple simulation where:
- Each policy has a fixed non-negative integer score
- Team scores are the sum of their policy scores
- Multiple environments can have different score assignments
"""

import argparse
import random
import sys
from dataclasses import dataclass

import matplotlib.pyplot as plt
import numpy as np
from tournament import (
    AdvantageExaggeration,
    EnvBalancing,
    InitialTeamMode,
    PolicyAggregation,
    ScaleInvariance,
    TeamCreationMode,
    TournamentConfig,
    print_generation_summary,
    print_policy_rankings,
    print_team_scores,
    run_multi_generation_tournament,
    run_tournament,
)


@dataclass(frozen=True)
class Policy:
    """A policy with a name and score."""

    name: str
    score: int

    def __str__(self) -> str:
        return f"{self.name}({self.score})"

    def __hash__(self) -> int:
        return hash((self.name, self.score))


@dataclass(frozen=True)
class AdditiveTeam:
    """A team of policies. Team score is sum of policy scores."""

    policies: tuple[Policy, ...]

    @property
    def members(self) -> tuple[Policy, ...]:
        """Return the policies in this team."""
        return self.policies

    def __str__(self) -> str:
        return " + ".join(str(p) for p in self.policies)

    def __hash__(self) -> int:
        return hash(self.policies)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, AdditiveTeam):
            return False
        return self.policies == other.policies


@dataclass(frozen=True)
class AdditiveEnv:
    """Environment that scores teams as sum of policy scores."""

    name: str

    def score(self, team: AdditiveTeam) -> float:
        """Return sum of policy scores."""
        return sum(p.score for p in team.policies)

    def __str__(self) -> str:
        return self.name


def create_policies(
    n: int,
    max_score: int = 10,
    rng: random.Random | None = None,
) -> list[Policy]:
    """Create n policies with random integer scores.

    Args:
        n: Number of policies to create.
        max_score: Maximum score for any policy (inclusive).
        rng: Random number generator.

    Returns:
        List of policies with scores from 0 to max_score.
    """
    if rng is None:
        rng = random.Random()

    policies = []
    for i in range(n):
        score = rng.randint(0, max_score)
        policies.append(Policy(name=f"P{i:02d}", score=score))
    return policies


def create_policies_from_scores(scores: list[int]) -> list[Policy]:
    """Create policies with specific scores.

    Args:
        scores: List of integer scores for each policy.

    Returns:
        List of policies with the given scores.
    """
    policies = []
    for i, score in enumerate(scores):
        policies.append(Policy(name=f"P{i:02d}", score=score))
    return policies


def create_teams(
    policies: list[Policy],
    team_size: int,
    n_teams: int,
    rng: random.Random | None = None,
) -> list[AdditiveTeam]:
    """Create n_teams by sampling from policies."""
    if rng is None:
        rng = random.Random()

    teams = []
    for _ in range(n_teams):
        members = tuple(rng.sample(policies, team_size))
        teams.append(AdditiveTeam(policies=members))
    return teams


def main():
    """Run the additive scoring tournament simulation."""
    # Capture command line for plot annotation
    cmd_line = " ".join(sys.argv)

    parser = argparse.ArgumentParser(
        description="Additive Scoring Tournament Simulation",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--policies", "-p", type=int, default=20, help="Number of policies to create")
    parser.add_argument("--teams", "-t", type=int, default=100, help="Number of teams to create")
    parser.add_argument("--team-size", "-s", type=int, default=3, help="Number of policies per team")
    parser.add_argument(
        "--max-score",
        type=int,
        default=10,
        help="Maximum score for any policy (0 to max-score)",
    )
    parser.add_argument(
        "--scores",
        type=str,
        default=None,
        help="Comma-separated list of specific policy scores (e.g., '0,10,11'). Overrides --policies and --max-score.",
    )
    # Stage 1: Scale invariance
    parser.add_argument(
        "--scale",
        type=str,
        default="divide_by_max",
        choices=["divide_by_max", "rank"],
        help="Stage 1: Scale invariance method (default: divide_by_max)",
    )
    # Stage 2: Advantage exaggeration
    parser.add_argument(
        "--power",
        type=float,
        default=None,
        help="Stage 2: Raise scores to this power (e.g., 2.0 for squared)",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=None,
        help="Stage 2: Exponential temperature (score -> exp(score/temp))",
    )
    # Stage 3: Environment balancing
    parser.add_argument(
        "--balance",
        type=str,
        default="max_1",
        choices=["max_1", "total_1"],
        help="Stage 3: Environment balancing (default: max_1)",
    )
    parser.add_argument(
        "--policy-agg",
        "-a",
        type=str,
        default="sum",
        choices=["sum", "mean", "median", "max", "p75"],
        help="Policy score aggregation method",
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    parser.add_argument(
        "--generations",
        "-g",
        type=int,
        default=1,
        help="Number of generations (default: 1, single generation)",
    )
    parser.add_argument(
        "--team-creation",
        type=str,
        default="sample",
        choices=["sample", "sample_replace", "evolve"],
        help="Team creation mode: sample (no replacement), sample_replace (with replacement), or evolve",
    )
    parser.add_argument(
        "--allow-dup-teams",
        action="store_true",
        help="Allow duplicate teams (default: True, use --no-dup-teams to disable)",
        default=True,
    )
    parser.add_argument(
        "--no-dup-teams",
        action="store_false",
        dest="allow_dup_teams",
        help="Disallow duplicate teams",
    )
    parser.add_argument(
        "--initial-teams",
        type=str,
        default="random",
        choices=["random", "clones"],
        help="Initial team creation: random (sample policies) or clones (each team is N copies of one policy)",
    )
    parser.add_argument(
        "--mutations",
        type=int,
        default=1,
        help="Number of policies to swap per team in evolve mode (default: 1)",
    )
    parser.add_argument(
        "--team-decay",
        type=float,
        default=1.0,
        help="Multiplier for number of teams each generation (default: 1.0, no decay)",
    )
    parser.add_argument(
        "--min-weight",
        type=float,
        default=0.01,
        help="Minimum weight per policy (default: 0.01)",
    )
    parser.add_argument(
        "--plot-weights",
        type=int,
        default=0,
        help="Plot weight history for top N policies (default: 0, no plot)",
    )
    parser.add_argument(
        "--plot-file",
        type=str,
        default=None,
        help="Save plot to file instead of displaying (e.g., weights.png)",
    )
    parser.add_argument(
        "--top-teams",
        type=int,
        default=20,
        help="Number of top teams to display (default: 20)",
    )
    parser.add_argument(
        "--top-policies",
        type=int,
        default=20,
        help="Number of top policies to display (default: 20)",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed policy info")

    args = parser.parse_args()

    # Map string args to enums
    scale_map = {
        "divide_by_max": ScaleInvariance.DIVIDE_BY_MAX,
        "rank": ScaleInvariance.RANK,
    }
    balance_map = {
        "max_1": EnvBalancing.MAX_1,
        "total_1": EnvBalancing.TOTAL_1,
    }
    agg_map = {
        "sum": PolicyAggregation.SUM,
        "mean": PolicyAggregation.MEAN,
        "median": PolicyAggregation.MEDIAN,
        "max": PolicyAggregation.MAX,
        "p75": PolicyAggregation.PERCENTILE_75,
    }
    team_creation_map = {
        "sample": TeamCreationMode.SAMPLE,
        "sample_replace": TeamCreationMode.SAMPLE_WITH_REPLACEMENT,
        "evolve": TeamCreationMode.EVOLVE,
    }
    initial_team_map = {
        "random": InitialTeamMode.RANDOM,
        "clones": InitialTeamMode.CLONES,
    }

    rng = random.Random(args.seed)

    # Create policies and environment
    if args.scores:
        # Parse comma-separated scores
        score_list = [int(s.strip()) for s in args.scores.split(",")]
        policies = create_policies_from_scores(score_list)
    else:
        policies = create_policies(args.policies, max_score=args.max_score, rng=rng)
    envs = [AdditiveEnv(name="Sum")]

    # Build advantage exaggeration if specified
    advantage_exaggeration = None
    if args.power is not None:
        advantage_exaggeration = AdvantageExaggeration(power=args.power)
    elif args.temperature is not None:
        advantage_exaggeration = AdvantageExaggeration(temperature=args.temperature)

    # Tournament config using three-stage normalization
    config = TournamentConfig(
        scale_invariance=scale_map[args.scale],
        advantage_exaggeration=advantage_exaggeration,
        env_balancing=balance_map[args.balance],
        policy_aggregation=agg_map[args.policy_agg],
    )

    print("Additive Scoring Tournament")
    print("=" * 60)
    print(f"Policies: {len(policies)}, Teams: {args.teams} (size {args.team_size})")
    if args.scores:
        print(f"Scores: {args.scores}")
    else:
        print(f"Max score: {args.max_score}")
    # Print normalization stages
    norm_str = f"Scale: {args.scale}"
    if args.power is not None:
        norm_str += f", Power: {args.power}"
    elif args.temperature is not None:
        norm_str += f", Temp: {args.temperature}"
    norm_str += f", Balance: {args.balance}"
    print(f"{norm_str}, Aggregation: {args.policy_agg}")
    print(f"Seed: {args.seed}")

    if args.verbose:
        print("\nPolicies (sorted by true score):")
        for p in sorted(policies, key=lambda x: x.score, reverse=True):
            print(f"  {p}")

    if args.generations > 1:
        print(f"Generations: {args.generations}")
        print()

        # Multi-generation tournament
        np_rng = np.random.default_rng(args.seed)

        def team_factory(members: tuple[Policy, ...]) -> AdditiveTeam:
            return AdditiveTeam(policies=members)

        multi_result = run_multi_generation_tournament(
            policies=policies,
            envs=envs,
            config=config,
            team_factory=team_factory,
            team_size=args.team_size,
            n_teams=args.teams,
            n_generations=args.generations,
            min_weight=args.min_weight,
            team_creation_mode=team_creation_map[args.team_creation],
            initial_team_mode=initial_team_map[args.initial_teams],
            n_mutations=args.mutations,
            team_decay=args.team_decay,
            allow_duplicate_teams=args.allow_dup_teams,
            rng=np_rng,
        )

        if args.verbose:
            print_generation_summary(multi_result, top_n=args.top_policies)

        # Show final generation results
        result = multi_result.final_result
        final_weights = multi_result.final_weights
        print(f"\nFinal Generation ({args.generations})")
        print("-" * 40)
    else:
        print()
        # Single generation
        teams = create_teams(policies, team_size=args.team_size, n_teams=args.teams, rng=rng)
        result = run_tournament(teams, envs, config)
        final_weights = None

    print_team_scores(result, "Team Scores", max_display=args.top_teams)
    print_policy_rankings(result, "Policy Rankings", max_display=args.top_policies, weights=final_weights)

    # Show correlation with true scores
    if args.verbose:
        print("\nTrue vs Estimated Rankings:")
        true_ranking = sorted(policies, key=lambda p: p.score, reverse=True)
        estimated_ranking = sorted(policies, key=lambda p: result.policy_scores.get(p, 0), reverse=True)
        print("  True ranking:", " ".join(p.name for p in true_ranking[:10]))
        print("  Estimated:   ", " ".join(p.name for p in estimated_ranking[:10]))

    # Plot weight history if requested
    if args.plot_weights > 0 and args.generations > 1:
        # Get top N policies by final weight
        sorted_by_weight = sorted(
            multi_result.final_weights.items(),
            key=lambda x: x[1],
            reverse=True,
        )
        top_policies = [p for p, _ in sorted_by_weight[: args.plot_weights]]

        # Build weight history for each policy
        generations = list(range(1, args.generations + 1))

        plt.figure(figsize=(10, 6))
        for policy in top_policies:
            weights_over_time = multi_result.weight_history(policy)
            plt.plot(generations, weights_over_time, label=str(policy), marker="o", markersize=3)

        plt.xlabel("Generation")
        plt.ylabel("Weight")
        plt.title(f"Policy Weight Evolution (Top {args.plot_weights} by Final Weight)")
        plt.legend(loc="upper left", fontsize="small")
        plt.grid(True, alpha=0.3)

        # Add command line as footer annotation
        plt.figtext(
            0.5,
            0.01,
            cmd_line,
            ha="center",
            fontsize=7,
            style="italic",
            wrap=True,
        )
        plt.subplots_adjust(bottom=0.12)

        if args.plot_file:
            plt.savefig(args.plot_file, dpi=150, bbox_inches="tight")
            print(f"\nPlot saved to {args.plot_file}")
        else:
            plt.show()


if __name__ == "__main__":
    main()
