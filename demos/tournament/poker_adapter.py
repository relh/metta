"""Poker adapter for the generic tournament framework.

This module provides poker-specific implementations of Team and Env
that work with the generic tournament.py framework.
"""

import random
from dataclasses import dataclass

from poker_hands import Card, HandValue, Rank, Suit, evaluate_hand, hand_to_numeric_score


@dataclass(frozen=True)
class PokerHand:
    """A poker hand (team) consisting of 5 cards (policies)."""

    cards: tuple[Card, ...]

    def __post_init__(self):
        if len(self.cards) != 5:
            raise ValueError(f"Poker hand must have 5 cards, got {len(self.cards)}")

    @property
    def members(self) -> tuple[Card, ...]:
        """Return the cards that make up this hand."""
        return self.cards

    @property
    def hand_value(self) -> HandValue:
        """Evaluate and return the poker hand value."""
        return evaluate_hand(list(self.cards))

    def __str__(self) -> str:
        cards_str = " ".join(str(c) for c in self.cards)
        return f"{cards_str} ({self.hand_value.rank.name})"

    def __hash__(self) -> int:
        return hash(self.cards)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PokerHand):
            return False
        return self.cards == other.cards


@dataclass(frozen=True)
class StandardPokerEnv:
    """Standard poker hand ranking environment."""

    name: str = "Standard"

    def score(self, team: PokerHand) -> float:
        """Score a poker hand using standard rankings."""
        return hand_to_numeric_score(team.hand_value)

    def __str__(self) -> str:
        return self.name


@dataclass(frozen=True)
class LowballPokerEnv:
    """Lowball poker where low hands win (Ace is low)."""

    name: str = "Lowball"

    def score(self, team: PokerHand) -> float:
        """Score a poker hand - lower standard score is better."""
        # Invert the standard score
        standard_score = hand_to_numeric_score(team.hand_value)
        # Use a large constant minus the score to flip rankings
        return 10**12 - standard_score

    def __str__(self) -> str:
        return self.name


def create_deck() -> list[Card]:
    """Create a standard 52-card deck."""
    return [Card(rank=r, suit=s) for r in Rank for s in Suit]


def sample_hands(
    deck: list[Card],
    n_hands: int,
    hand_size: int = 5,
    rng: random.Random | None = None,
) -> list[PokerHand]:
    """Sample n_hands random poker hands from the deck.

    Each hand is sampled by drawing hand_size cards without replacement
    from the deck, but different hands can share cards.
    """
    if rng is None:
        rng = random.Random()

    hands = []
    for _ in range(n_hands):
        cards = tuple(rng.sample(deck, hand_size))
        hands.append(PokerHand(cards=cards))
    return hands


# Demo usage
if __name__ == "__main__":
    import argparse
    import sys

    import numpy as np

    # Capture command line for plot annotation
    cmd_line = " ".join(sys.argv)

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

    parser = argparse.ArgumentParser(description="Poker Tournament Simulation")
    parser.add_argument(
        "--hands",
        "-n",
        type=int,
        default=100,
        help="Number of hands to sample (default: 100)",
    )
    parser.add_argument(
        "--envs",
        "-e",
        type=str,
        nargs="+",
        default=["standard"],
        choices=["standard", "lowball"],
        help="Environments to use (default: standard)",
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
        help="Policy score aggregation method (default: sum)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducibility (default: 42)",
    )
    parser.add_argument(
        "--top-hands",
        "-t",
        type=int,
        default=20,
        help="Number of top hands to display (default: 20)",
    )
    parser.add_argument(
        "--top-cards",
        "-c",
        type=int,
        default=20,
        help="Number of top cards to display (default: 20)",
    )
    parser.add_argument(
        "--generations",
        "-g",
        type=int,
        default=1,
        help="Number of generations (default: 1, single generation)",
    )
    parser.add_argument(
        "--min-weight",
        type=float,
        default=0.01,
        help="Minimum weight per policy (default: 0.01)",
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
        "--verbose",
        "-v",
        action="store_true",
        help="Show detailed info",
    )

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

    # Create deck
    deck = create_deck()

    # Create environments
    env_map = {
        "standard": StandardPokerEnv(),
        "lowball": LowballPokerEnv(),
    }
    envs = [env_map[e] for e in args.envs]

    # Build advantage exaggeration if specified
    advantage_exaggeration = None
    if args.power is not None:
        advantage_exaggeration = AdvantageExaggeration(power=args.power)
    elif args.temperature is not None:
        advantage_exaggeration = AdvantageExaggeration(temperature=args.temperature)

    # Run tournament
    config = TournamentConfig(
        scale_invariance=scale_map[args.scale],
        advantage_exaggeration=advantage_exaggeration,
        env_balancing=balance_map[args.balance],
        policy_aggregation=agg_map[args.policy_agg],
    )

    print("Poker Tournament")
    print("=" * 60)
    print(f"Hands: {args.hands}, Envs: {', '.join(args.envs)}")
    # Print normalization stages
    norm_str = f"Scale: {args.scale}"
    if args.power is not None:
        norm_str += f", Power: {args.power}"
    elif args.temperature is not None:
        norm_str += f", Temp: {args.temperature}"
    norm_str += f", Balance: {args.balance}"
    print(f"{norm_str}, Aggregation: {args.policy_agg}")
    print(f"Seed: {args.seed}")

    if args.generations > 1:
        print(f"Generations: {args.generations}")
        print()

        # Multi-generation tournament
        rng = np.random.default_rng(args.seed)

        def hand_factory(cards: tuple[Card, ...]) -> PokerHand:
            return PokerHand(cards=cards)

        multi_result = run_multi_generation_tournament(
            policies=deck,
            envs=envs,
            config=config,
            team_factory=hand_factory,
            team_size=5,
            n_teams=args.hands,
            n_generations=args.generations,
            min_weight=args.min_weight,
            team_creation_mode=team_creation_map[args.team_creation],
            initial_team_mode=initial_team_map[args.initial_teams],
            n_mutations=args.mutations,
            team_decay=args.team_decay,
            rng=rng,
        )

        if args.verbose:
            print_generation_summary(multi_result, top_n=args.top_cards)

        # Show final generation results
        result = multi_result.final_result
        final_weights = multi_result.final_weights
        print(f"\nFinal Generation ({args.generations})")
        print("-" * 40)
    else:
        print()
        # Single generation
        rng = random.Random(args.seed)
        hands = sample_hands(deck, n_hands=args.hands, rng=rng)
        result = run_tournament(hands, envs, config)
        final_weights = None

        if args.verbose:
            print(f"Deck: {len(deck)} cards")
            print(f"Sampled {len(hands)} hands")
            print()

    print_team_scores(result, "Hand Rankings", max_display=args.top_hands)
    print_policy_rankings(result, "Card Rankings", max_display=args.top_cards, weights=final_weights)

    # Plot weight history if requested
    if args.plot_weights > 0 and args.generations > 1:
        import matplotlib.pyplot as plt

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
