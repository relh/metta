"""CogsGuard-style adapter for the generic tournament framework.

Policies have skills (mining, scrambling, aligning) scored 0-9.
Environments have requirements for each skill (1-4).
Teams score based on how well they meet the requirements.

Each policy can only contribute ONE skill to the team (assignment problem).
"""

import argparse
import itertools
import random
import sys
from dataclasses import dataclass
from enum import IntEnum

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


class Skill(IntEnum):
    MINING = 0
    SCRAMBLING = 1
    ALIGNING = 2


@dataclass(frozen=True)
class Policy:
    """A policy with skills in mining, scrambling, and aligning."""

    name: str
    mining: int
    scrambling: int
    aligning: int

    def get_skill(self, skill: Skill) -> int:
        """Get the value for a specific skill."""
        if skill == Skill.MINING:
            return self.mining
        elif skill == Skill.SCRAMBLING:
            return self.scrambling
        else:
            return self.aligning

    def __str__(self) -> str:
        return f"{self.name}(m={self.mining},s={self.scrambling},a={self.aligning})"

    def __hash__(self) -> int:
        return hash((self.name, self.mining, self.scrambling, self.aligning))


# Type alias for an assignment: maps each policy index to a Skill
Assignment = tuple[Skill, ...]


def compute_assignment_score(
    policies: tuple[Policy, ...],
    assignment: Assignment,
    mining_req: int,
    scrambling_req: int,
    aligning_req: int,
) -> float:
    """Compute the score for a specific assignment of policies to skills."""
    mining_sum = 0
    scrambling_sum = 0
    aligning_sum = 0

    for policy, skill in zip(policies, assignment, strict=True):
        if skill == Skill.MINING:
            mining_sum += policy.mining
        elif skill == Skill.SCRAMBLING:
            scrambling_sum += policy.scrambling
        else:
            aligning_sum += policy.aligning

    mining_ratio = mining_sum / mining_req
    scrambling_ratio = scrambling_sum / scrambling_req
    aligning_ratio = aligning_sum / aligning_req

    return min(mining_ratio, scrambling_ratio, aligning_ratio)


def find_optimal_assignment(
    policies: tuple[Policy, ...],
    mining_req: int,
    scrambling_req: int,
    aligning_req: int,
) -> tuple[Assignment, float]:
    """Find the optimal assignment of policies to skills.

    For small teams, enumerates all 3^n assignments.
    Returns (best_assignment, best_score).
    """
    best_assignment: Assignment | None = None
    best_score = -1.0

    # Enumerate all possible assignments
    for assignment in itertools.product(Skill, repeat=len(policies)):
        score = compute_assignment_score(policies, assignment, mining_req, scrambling_req, aligning_req)
        if score > best_score:
            best_score = score
            best_assignment = assignment

    assert best_assignment is not None
    return best_assignment, best_score


@dataclass(frozen=True)
class CogsTeam:
    """A team of policies with skill assignments."""

    policies: tuple[Policy, ...]

    @property
    def members(self) -> tuple[Policy, ...]:
        return self.policies

    def get_totals_for_assignment(self, assignment: Assignment) -> tuple[int, int, int]:
        """Get (mining, scrambling, aligning) totals for a given assignment."""
        mining = sum(p.mining for p, s in zip(self.policies, assignment, strict=True) if s == Skill.MINING)
        scrambling = sum(p.scrambling for p, s in zip(self.policies, assignment, strict=True) if s == Skill.SCRAMBLING)
        aligning = sum(p.aligning for p, s in zip(self.policies, assignment, strict=True) if s == Skill.ALIGNING)
        return mining, scrambling, aligning

    def __str__(self) -> str:
        names = "+".join(p.name for p in self.policies)
        return f"[{names}]"

    def __hash__(self) -> int:
        return hash(self.policies)


@dataclass(frozen=True)
class CogsEnv:
    """An environment with skill requirements."""

    name: str
    mining_req: int
    scrambling_req: int
    aligning_req: int

    def score(self, team: CogsTeam) -> float:
        """Score a team using optimal skill assignment.

        Finds the best way to assign each policy to a skill,
        then returns min(skill_sum / requirement) across all skills.
        """
        _, score = find_optimal_assignment(
            team.policies,
            self.mining_req,
            self.scrambling_req,
            self.aligning_req,
        )
        return score

    def score_with_assignment(self, team: CogsTeam) -> tuple[float, Assignment, tuple[int, int, int]]:
        """Score a team and return the optimal assignment details.

        Returns (score, assignment, (mining_total, scrambling_total, aligning_total))
        """
        assignment, score = find_optimal_assignment(
            team.policies,
            self.mining_req,
            self.scrambling_req,
            self.aligning_req,
        )
        totals = team.get_totals_for_assignment(assignment)
        return score, assignment, totals

    def __str__(self) -> str:
        return f"{self.name}(m={self.mining_req},s={self.scrambling_req},a={self.aligning_req})"


def create_policies(
    n: int,
    rng: random.Random | None = None,
    max_skill: int = 9,
    max_total_skill: int | None = None,
) -> list[Policy]:
    """Create n policies with random skills.

    Args:
        n: Number of policies to create.
        rng: Random number generator.
        max_skill: Maximum value for any single skill (default 9).
        max_total_skill: Maximum sum of all skills. If provided, policies are
            resampled until their total is at or below this value.
    """
    if rng is None:
        rng = random.Random()

    policies = []
    for i in range(n):
        while True:
            mining = rng.randint(0, max_skill)
            scrambling = rng.randint(0, max_skill)
            aligning = rng.randint(0, max_skill)

            if max_total_skill is None or (mining + scrambling + aligning) <= max_total_skill:
                break

        policy = Policy(
            name=f"P{i:02d}",
            mining=mining,
            scrambling=scrambling,
            aligning=aligning,
        )
        policies.append(policy)
    return policies


def create_envs(n: int, rng: random.Random | None = None) -> list[CogsEnv]:
    """Create n environments with random requirements (1-4)."""
    if rng is None:
        rng = random.Random()

    envs = []
    for i in range(n):
        env = CogsEnv(
            name=f"E{i:02d}",
            mining_req=rng.randint(1, 4),
            scrambling_req=rng.randint(1, 4),
            aligning_req=rng.randint(1, 4),
        )
        envs.append(env)
    return envs


def create_teams(
    policies: list[Policy],
    team_size: int,
    n_teams: int,
    rng: random.Random | None = None,
) -> list[CogsTeam]:
    """Create n_teams by sampling from policies."""
    if rng is None:
        rng = random.Random()

    teams = []
    for _ in range(n_teams):
        members = tuple(rng.sample(policies, team_size))
        teams.append(CogsTeam(policies=members))
    return teams


def main():
    """Run the CogsGuard tournament simulation."""
    # Capture command line for plot annotation
    cmd_line = " ".join(sys.argv)

    parser = argparse.ArgumentParser(
        description="CogsGuard Tournament Simulation",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--policies", "-p", type=int, default=20, help="Number of policies to create")
    parser.add_argument("--teams", "-t", type=int, default=100, help="Number of teams to create")
    parser.add_argument("--team-size", "-s", type=int, default=3, help="Number of policies per team")
    parser.add_argument("--envs", "-e", type=int, default=5, help="Number of environments")
    parser.add_argument(
        "--max-skill",
        type=int,
        default=9,
        help="Maximum value for any single skill (default: 9)",
    )
    parser.add_argument(
        "--max-total-skill",
        type=int,
        default=None,
        help="Maximum sum of all skills per policy (default: no limit)",
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
        choices=["sample", "evolve"],
        help="Team creation mode: sample (by policy weight) or evolve (mutate existing teams)",
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
    parser.add_argument(
        "--show-assignments",
        action="store_true",
        help="Show optimal assignments for sample teams",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed policy and env info")

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
        "evolve": TeamCreationMode.EVOLVE,
    }
    initial_team_map = {
        "random": InitialTeamMode.RANDOM,
        "clones": InitialTeamMode.CLONES,
    }

    rng = random.Random(args.seed)

    # Create policies and environments
    policies = create_policies(
        args.policies,
        rng=rng,
        max_skill=args.max_skill,
        max_total_skill=args.max_total_skill,
    )
    envs = create_envs(args.envs, rng=rng)

    # Build advantage exaggeration if specified
    advantage_exaggeration = None
    if args.power is not None:
        advantage_exaggeration = AdvantageExaggeration(power=args.power)
    elif args.temperature is not None:
        advantage_exaggeration = AdvantageExaggeration(temperature=args.temperature)

    # Tournament config
    config = TournamentConfig(
        scale_invariance=scale_map[args.scale],
        advantage_exaggeration=advantage_exaggeration,
        env_balancing=balance_map[args.balance],
        policy_aggregation=agg_map[args.policy_agg],
    )

    print("CogsGuard Tournament")
    print("=" * 60)
    print(f"Policies: {args.policies}, Teams: {args.teams} (size {args.team_size}), Envs: {args.envs}")
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
        print("\nPolicies:")
        for p in policies:
            print(f"  {p}")

        print("\nEnvironments:")
        for e in envs:
            print(f"  {e}")

    if args.generations > 1:
        print(f"Generations: {args.generations}")
        print()

        # Multi-generation tournament
        np_rng = np.random.default_rng(args.seed)

        def team_factory(members: tuple[Policy, ...]) -> CogsTeam:
            return CogsTeam(policies=members)

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
            rng=np_rng,
        )

        if args.verbose:
            print_generation_summary(multi_result, top_n=args.top_policies)

        # Show final generation results
        result = multi_result.final_result
        final_weights = multi_result.final_weights
        print(f"\nFinal Generation ({args.generations})")
        print("-" * 40)

        # Get teams from final generation for show_assignments
        teams = list(result.team_scores)
    else:
        print()
        # Single generation
        teams = create_teams(policies, team_size=args.team_size, n_teams=args.teams, rng=rng)
        result = run_tournament(teams, envs, config)
        final_weights = None

    print_team_scores(result, "Team Scores", max_display=args.top_teams)
    print_policy_rankings(result, "Policy Rankings", max_display=args.top_policies, weights=final_weights)

    if args.show_assignments:
        print("\n" + "=" * 60)
        print("Optimal Assignments (first 5 teams)")
        print("=" * 60)

        skill_names = {Skill.MINING: "M", Skill.SCRAMBLING: "S", Skill.ALIGNING: "A"}

        for team in teams[:5]:
            print(f"\n{team}")
            for p in team.policies:
                print(f"  {p}")

            for env in envs:
                score, assignment, totals = env.score_with_assignment(team)
                assign_str = " ".join(
                    f"{p.name}->{skill_names[s]}" for p, s in zip(team.policies, assignment, strict=True)
                )
                print(f"  {env}: {assign_str} => totals=({totals[0]},{totals[1]},{totals[2]}) score={score:.2f}")

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
