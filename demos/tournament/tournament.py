"""Generic tournament simulation for exploring scoring dynamics.

This module provides a framework for running tournaments where:
- Policies are the individual units we want to score
- Teams are combinations of policies that compete together
- Environments score teams (higher is better)

The framework supports various normalization schemes and aggregation methods
to go from (team, env) scores to per-policy scores.
"""

from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
from typing import Hashable, Protocol

import numpy as np

# =============================================================================
# Protocols for generic tournament components
# =============================================================================


class Team(Protocol):
    """A team is a collection of policies that compete together."""

    @property
    def members(self) -> tuple[Hashable, ...]:
        """Return the policies that make up this team."""
        ...

    def __str__(self) -> str: ...
    def __hash__(self) -> int: ...
    def __eq__(self, other: object) -> bool: ...


class Env(Protocol):
    """An environment scores teams."""

    def score(self, team: Team) -> float:
        """Return a score for the team (higher is better)."""
        ...

    def __str__(self) -> str: ...


# =============================================================================
# Normalization and aggregation methods
# =============================================================================


class ScaleInvariance(Enum):
    """Stage 1: Make scores scale-invariant, mapping to [0,1]."""

    DIVIDE_BY_MAX = "divide_by_max"  # Linear scaling, keeps relative differences
    RANK = "rank"  # Rank-based (0 to 1), ordinal only


class EnvBalancing(Enum):
    """Stage 3: Balance environment contributions."""

    MAX_1 = "max_1"  # Divide by max so highest score is 1
    TOTAL_1 = "total_1"  # Divide by sum so total weight is 1


@dataclass
class AdvantageExaggeration:
    """Stage 2: Exaggerate advantage of higher scores (optional).

    Either power or temperature should be set, not both.
    If neither is set, no exaggeration is applied.
    """

    power: float | None = None  # Raise scores to this power (e.g., 2.0 for squared)
    temperature: float | None = None  # Exponential: score -> exp(score / temperature)

    def apply(self, scores: np.ndarray) -> np.ndarray:
        """Apply the exaggeration transformation."""
        if self.power is not None:
            return scores**self.power
        elif self.temperature is not None:
            # Shift for numerical stability before exp
            shifted = scores - scores.max()
            return np.exp(shifted / self.temperature)
        return scores


# Legacy enum for backwards compatibility
class EnvNormalization(Enum):
    """Methods for normalizing scores within an environment (DEPRECATED)."""

    RAW = "raw"  # No normalization
    DIVIDE_BY_MAX = "divide_by_max"  # Linear, keeps relative differences
    MIN_MAX = "min_max"  # Subtract min, divide by range
    RANK = "rank"  # Rank-based (0 to 1)
    RANK_SQUARED = "rank_squared"  # rank^2, rewards beating others
    SOFTMAX = "softmax"  # Exponential emphasis on top scores
    SOFTMAX_RANK = "softmax_rank"  # Softmax applied to ranks
    PROPORTIONAL = "proportional"  # Divide by sum, so total weight = 1


class TeamAggregation(Enum):
    """Methods for combining (team, env) scores into a single team score."""

    MEAN = "mean"  # Average across environments
    MEDIAN = "median"  # Median across environments
    MIN = "min"  # Worst-case performance


class TeamCreationMode(Enum):
    """Methods for creating teams in multi-generation tournaments."""

    SAMPLE = "sample"  # Sample policies weighted by policy scores (no replacement within team)
    SAMPLE_WITH_REPLACEMENT = "sample_replace"  # Sample with replacement (duplicates allowed within team)
    EVOLVE = "evolve"  # Evolve teams: sample teams by score, then mutate by swapping policies


class InitialTeamMode(Enum):
    """Methods for creating the initial teams in generation 0."""

    RANDOM = "random"  # Randomly sample policies without replacement (default)
    CLONES = "clones"  # Each team is N copies of a single policy (one team per policy)


class PolicyAggregation(Enum):
    """Methods for going from team scores to policy scores."""

    SUM = "sum"  # Sum of all teams containing this policy (rewards winning, doesn't punish losing)
    MEAN = "mean"  # Average of all teams containing this policy
    MEDIAN = "median"  # Median team score
    MAX = "max"  # Best team this policy appears in
    PERCENTILE_75 = "p75"  # 75th percentile of teams


@dataclass
class TournamentConfig:
    """Configuration for a tournament simulation.

    Score normalization happens in three stages:
    1. scale_invariance: Map raw scores to [0,1] using divide_by_max or rank
    2. advantage_exaggeration: Optionally apply power or exponential transform
    3. env_balancing: Normalize so environments have equal impact (max_1 or total_1)
    """

    # New three-stage normalization
    scale_invariance: ScaleInvariance = ScaleInvariance.DIVIDE_BY_MAX
    advantage_exaggeration: AdvantageExaggeration | None = None
    env_balancing: EnvBalancing = EnvBalancing.MAX_1

    # Legacy field for backwards compatibility
    env_normalization: EnvNormalization | None = None

    team_aggregation: TeamAggregation = TeamAggregation.MEAN
    policy_aggregation: PolicyAggregation = PolicyAggregation.SUM


# =============================================================================
# Tournament results
# =============================================================================


@dataclass
class TournamentResult:
    """Results from a tournament simulation."""

    policy_scores: dict[Hashable, float]
    team_scores: dict[Team, float]
    raw_scores: dict[Team, dict[Env, float]]  # raw_scores[team][env] = score
    team_counts: dict[Team, int] | None = None  # Number of times each team appeared

    def top_policies(self, n: int = 10) -> list[tuple[Hashable, float]]:
        """Get the top N policies by score."""
        sorted_policies = sorted(
            self.policy_scores.items(),
            key=lambda x: x[1],
            reverse=True,
        )
        return sorted_policies[:n]

    def bottom_policies(self, n: int = 10) -> list[tuple[Hashable, float]]:
        """Get the bottom N policies by score."""
        sorted_policies = sorted(
            self.policy_scores.items(),
            key=lambda x: x[1],
        )
        return sorted_policies[:n]


# =============================================================================
# Normalization functions
# =============================================================================


def normalize_scores_three_stage(
    scores: list[float],
    scale_invariance: ScaleInvariance,
    advantage_exaggeration: AdvantageExaggeration | None,
    env_balancing: EnvBalancing,
) -> list[float]:
    """Normalize scores using the three-stage pipeline.

    Stage 1 (scale_invariance): Map to [0,1]
    Stage 2 (advantage_exaggeration): Optional power/exp transform
    Stage 3 (env_balancing): Normalize environment contributions
    """
    if not scores:
        return []

    arr = np.array(scores, dtype=float)

    # Stage 1: Scale invariance -> [0,1]
    if scale_invariance == ScaleInvariance.DIVIDE_BY_MAX:
        max_val = arr.max()
        if max_val > 0:
            arr = arr / max_val
        # If max is 0, all scores are 0, keep as-is
    elif scale_invariance == ScaleInvariance.RANK:
        # Rank from 0 to 1, where 1 is best
        order = arr.argsort().argsort()  # Rank (0 = lowest)
        arr = order / (len(arr) - 1) if len(arr) > 1 else np.array([0.5])
    else:
        raise ValueError(f"Unknown scale_invariance method: {scale_invariance}")

    # Stage 2: Advantage exaggeration (optional)
    if advantage_exaggeration is not None:
        arr = advantage_exaggeration.apply(arr)

    # Stage 3: Environment balancing
    if env_balancing == EnvBalancing.MAX_1:
        max_val = arr.max()
        if max_val > 0:
            arr = arr / max_val
    elif env_balancing == EnvBalancing.TOTAL_1:
        total = arr.sum()
        if total > 0:
            arr = arr / total
        else:
            # If all scores are 0, give uniform weight
            arr = np.ones(len(arr)) / len(arr)
    else:
        raise ValueError(f"Unknown env_balancing method: {env_balancing}")

    return list(arr)


def normalize_scores(
    scores: list[float],
    method: EnvNormalization,
) -> list[float]:
    """Normalize a list of scores using the specified method (LEGACY)."""
    if not scores:
        return []

    arr = np.array(scores, dtype=float)

    if method == EnvNormalization.RAW:
        return list(arr)

    elif method == EnvNormalization.DIVIDE_BY_MAX:
        max_val = arr.max()
        if max_val == 0:
            return list(arr)
        return list(arr / max_val)

    elif method == EnvNormalization.MIN_MAX:
        min_val, max_val = arr.min(), arr.max()
        if max_val == min_val:
            return [0.5] * len(arr)
        return list((arr - min_val) / (max_val - min_val))

    elif method == EnvNormalization.RANK:
        # Rank from 0 to 1, where 1 is best
        order = arr.argsort().argsort()  # Rank (0 = lowest)
        return list(order / (len(arr) - 1) if len(arr) > 1 else [0.5])

    elif method == EnvNormalization.RANK_SQUARED:
        order = arr.argsort().argsort()
        ranks = order / (len(arr) - 1) if len(arr) > 1 else np.array([0.5])
        return list(ranks**2)

    elif method == EnvNormalization.SOFTMAX:
        # Shift for numerical stability, then apply softmax
        shifted = arr - arr.max()
        # Scale factor to prevent extreme values
        scale = max(1.0, arr.std()) if arr.std() > 0 else 1.0
        exp_scores = np.exp(shifted / scale)
        return list(exp_scores / exp_scores.sum())

    elif method == EnvNormalization.SOFTMAX_RANK:
        # First convert to ranks (0 to n-1), then apply softmax
        order = arr.argsort().argsort().astype(float)  # Rank (0 = lowest)
        # Apply softmax to ranks
        exp_ranks = np.exp(order)
        return list(exp_ranks / exp_ranks.sum())

    elif method == EnvNormalization.PROPORTIONAL:
        # Divide by sum so total weight = 1
        total = arr.sum()
        if total == 0:
            # If all scores are 0, give uniform weight
            return [1.0 / len(arr)] * len(arr)
        return list(arr / total)

    raise ValueError(f"Unknown normalization method: {method}")


def aggregate_team_scores(
    normalized_scores: dict[Team, dict[Env, float]],
    method: TeamAggregation,
) -> dict[Team, float]:
    """Aggregate per-environment scores into a single score per team."""
    team_scores: dict[Team, float] = {}

    for team, env_scores in normalized_scores.items():
        values = list(env_scores.values())
        arr = np.array(values)

        if method == TeamAggregation.MEAN:
            team_scores[team] = float(arr.mean())
        elif method == TeamAggregation.MEDIAN:
            team_scores[team] = float(np.median(arr))
        elif method == TeamAggregation.MIN:
            team_scores[team] = float(arr.min())
        else:
            raise ValueError(f"Unknown team aggregation method: {method}")

    return team_scores


def aggregate_policy_scores(
    team_scores: dict[Team, float],
    method: PolicyAggregation,
) -> dict[Hashable, float]:
    """Aggregate team scores to get per-policy scores."""
    # Collect all scores for each policy
    policy_team_scores: dict[Hashable, list[float]] = defaultdict(list)
    for team, score in team_scores.items():
        for member in team.members:
            policy_team_scores[member].append(score)

    # Aggregate
    policy_scores: dict[Hashable, float] = {}
    for policy, scores in policy_team_scores.items():
        arr = np.array(scores)
        if method == PolicyAggregation.SUM:
            policy_scores[policy] = float(arr.sum())
        elif method == PolicyAggregation.MEAN:
            policy_scores[policy] = float(arr.mean())
        elif method == PolicyAggregation.MEDIAN:
            policy_scores[policy] = float(np.median(arr))
        elif method == PolicyAggregation.MAX:
            policy_scores[policy] = float(arr.max())
        elif method == PolicyAggregation.PERCENTILE_75:
            policy_scores[policy] = float(np.percentile(arr, 75))
        else:
            raise ValueError(f"Unknown policy aggregation method: {method}")

    return policy_scores


# =============================================================================
# Main tournament runner
# =============================================================================


def run_tournament(
    teams: list[Team],
    envs: list[Env],
    config: TournamentConfig,
) -> TournamentResult:
    """Run a tournament with the given teams and environments.

    Args:
        teams: The teams competing in the tournament. May contain duplicates.
        envs: The environments that score the teams.
        config: Tournament configuration (normalization and aggregation methods).

    Returns:
        TournamentResult with policy scores, team scores, and raw scores.
        Note: team_scores and raw_scores are keyed by unique teams (duplicates merged),
        but policy_scores account for team multiplicity.
    """
    # Count team occurrences to handle duplicates
    team_counts: dict[Team, int] = {}
    for team in teams:
        team_counts[team] = team_counts.get(team, 0) + 1

    unique_teams = list(team_counts.keys())

    # Step 1: Get raw scores for each unique (team, env) pair
    raw_scores: dict[Team, dict[Env, float]] = {}
    for team in unique_teams:
        raw_scores[team] = {}
        for env in envs:
            raw_scores[team][env] = env.score(team)

    # Step 2: Normalize scores per environment
    # Important: normalize over ALL team instances (with duplicates), not just unique teams
    # This ensures duplicate teams affect the normalization properly
    normalized_scores_by_idx: list[dict[Env, float]] = [{} for _ in teams]

    for env in envs:
        # Get scores for all team instances (with duplicates)
        env_scores = [raw_scores[team][env] for team in teams]

        # Use legacy normalization if specified, otherwise use three-stage
        if config.env_normalization is not None:
            normalized = normalize_scores(env_scores, config.env_normalization)
        else:
            normalized = normalize_scores_three_stage(
                env_scores,
                config.scale_invariance,
                config.advantage_exaggeration,
                config.env_balancing,
            )

        # Store normalized scores by index
        for idx, norm_score in enumerate(normalized):
            normalized_scores_by_idx[idx][env] = norm_score

    # Step 3: Aggregate across environments to get team scores (per instance)
    team_scores_by_idx: list[float] = []
    for idx in range(len(teams)):
        env_scores_dict = normalized_scores_by_idx[idx]
        values = list(env_scores_dict.values())
        arr = np.array(values)

        if config.team_aggregation == TeamAggregation.MEAN:
            team_scores_by_idx.append(float(arr.mean()))
        elif config.team_aggregation == TeamAggregation.MEDIAN:
            team_scores_by_idx.append(float(np.median(arr)))
        elif config.team_aggregation == TeamAggregation.MIN:
            team_scores_by_idx.append(float(arr.min()))
        else:
            raise ValueError(f"Unknown team aggregation method: {config.team_aggregation}")

    # Step 4: Aggregate to policy scores (accounting for all team instances)
    policy_team_scores: dict[Hashable, list[float]] = defaultdict(list)
    for idx, team in enumerate(teams):
        score = team_scores_by_idx[idx]
        for member in team.members:
            policy_team_scores[member].append(score)

    policy_scores: dict[Hashable, float] = {}
    for policy, scores in policy_team_scores.items():
        arr = np.array(scores)
        if config.policy_aggregation == PolicyAggregation.SUM:
            policy_scores[policy] = float(arr.sum())
        elif config.policy_aggregation == PolicyAggregation.MEAN:
            policy_scores[policy] = float(arr.mean())
        elif config.policy_aggregation == PolicyAggregation.MEDIAN:
            policy_scores[policy] = float(np.median(arr))
        elif config.policy_aggregation == PolicyAggregation.MAX:
            policy_scores[policy] = float(arr.max())
        elif config.policy_aggregation == PolicyAggregation.PERCENTILE_75:
            policy_scores[policy] = float(np.percentile(arr, 75))
        else:
            raise ValueError(f"Unknown policy aggregation method: {config.policy_aggregation}")

    # Build team_scores dict for unique teams (use first instance's score)
    # This is for display purposes; the actual policy scores already account for duplicates
    team_scores: dict[Team, float] = {}
    for idx, team in enumerate(teams):
        if team not in team_scores:
            team_scores[team] = team_scores_by_idx[idx]

    return TournamentResult(
        policy_scores=policy_scores,
        team_scores=team_scores,
        raw_scores=raw_scores,
        team_counts=team_counts,
    )


# =============================================================================
# Multi-generation tournament
# =============================================================================


@dataclass
class GenerationResult:
    """Results from a single generation in a multi-generation tournament."""

    generation: int
    result: TournamentResult
    policy_weights: dict[Hashable, float]  # Weights used for sampling this generation


@dataclass
class MultiGenResult:
    """Results from a multi-generation tournament."""

    generations: list[GenerationResult]
    final_weights: dict[Hashable, float]

    @property
    def final_result(self) -> TournamentResult:
        """Get the result from the final generation."""
        return self.generations[-1].result

    def weight_history(self, policy: Hashable) -> list[float]:
        """Get the weight history for a policy across generations."""
        return [g.policy_weights.get(policy, 0.0) for g in self.generations]

    def score_history(self, policy: Hashable) -> list[float]:
        """Get the score history for a policy across generations."""
        return [g.result.policy_scores.get(policy, 0.0) for g in self.generations]


def create_clone_teams(
    policies: list[Hashable],
    team_size: int,
    team_factory: callable,
) -> list[Team]:
    """Create teams where each team is N copies of a single policy.

    Creates exactly len(policies) teams, one per policy.

    Args:
        policies: List of all policies.
        team_size: Number of copies of the policy in each team.
        team_factory: Function that takes a tuple of policies and returns a Team.

    Returns:
        List of clone teams (one per policy).
    """
    return [team_factory((policy,) * team_size) for policy in policies]


def sample_teams_weighted(
    policies: list[Hashable],
    weights: dict[Hashable, float],
    team_size: int,
    n_teams: int,
    team_factory: callable,
    rng: np.random.Generator | None = None,
    allow_duplicate_policies: bool = False,
    allow_duplicate_teams: bool = True,
) -> list[Team]:
    """Sample teams using weighted policy selection.

    Args:
        policies: List of all policies.
        weights: Weight for each policy (should sum to 1).
        team_size: Number of policies per team.
        n_teams: Number of teams to create.
        team_factory: Function that takes a tuple of policies and returns a Team.
        rng: Random number generator.
        allow_duplicate_policies: If True, same policy can appear multiple times in a team.
        allow_duplicate_teams: If True, same team can be created multiple times.

    Returns:
        List of sampled teams.
    """
    if rng is None:
        rng = np.random.default_rng()

    # Normalize weights for given policies
    policy_weights = np.array([weights.get(p, 0.0) for p in policies])
    if policy_weights.sum() == 0:
        policy_weights = np.ones(len(policies))
    policy_weights = policy_weights / policy_weights.sum()

    teams = []
    seen_teams: set[tuple[Hashable, ...]] = set()

    max_attempts = n_teams * 10  # Avoid infinite loop if unique teams are exhausted
    attempts = 0

    while len(teams) < n_teams and attempts < max_attempts:
        attempts += 1

        # Sample policies for the team
        indices = rng.choice(
            len(policies),
            size=team_size,
            replace=allow_duplicate_policies,
            p=policy_weights,
        )
        team_policies = tuple(policies[i] for i in indices)

        # Check for duplicate teams if not allowed
        if not allow_duplicate_teams:
            # Use sorted tuple for comparison (order-independent)
            team_key = tuple(sorted(team_policies, key=hash))
            if team_key in seen_teams:
                continue
            seen_teams.add(team_key)

        teams.append(team_factory(team_policies))

    return teams


def evolve_teams(
    prev_teams: list[Team],
    team_scores: dict[Team, float],
    policies: list[Hashable],
    policy_weights: dict[Hashable, float],
    n_teams: int,
    n_mutations: int,
    team_factory: callable,
    rng: np.random.Generator | None = None,
) -> list[Team]:
    """Create new teams by evolving previous teams.

    Teams are sampled in proportion to their scores, then mutated by
    swapping out some policies for new ones (sampled by policy weight).

    Args:
        prev_teams: Teams from the previous generation.
        team_scores: Scores for each team (used for weighted sampling).
        policies: List of all policies.
        policy_weights: Weight for each policy (for replacement sampling).
        n_teams: Number of teams to create.
        n_mutations: Number of policies to swap out per team.
        team_factory: Function that takes a tuple of policies and returns a Team.
        rng: Random number generator.

    Returns:
        List of evolved teams.
    """
    if rng is None:
        rng = np.random.default_rng()

    # Build team weights from scores
    teams_list = list(prev_teams)
    team_weights = np.array([max(team_scores.get(t, 0.0), 1e-10) for t in teams_list])
    team_weights = team_weights / team_weights.sum()

    # Normalize policy weights
    policy_list = list(policies)
    policy_weight_arr = np.array([policy_weights.get(p, 0.0) for p in policy_list])
    if policy_weight_arr.sum() == 0:
        policy_weight_arr = np.ones(len(policy_list))
    policy_weight_arr = policy_weight_arr / policy_weight_arr.sum()

    new_teams = []
    for _ in range(n_teams):
        # Sample a parent team weighted by score
        parent_idx = rng.choice(len(teams_list), p=team_weights)
        parent_team = teams_list[parent_idx]
        members = list(parent_team.members)

        # Decide how many to mutate (up to n_mutations, but not more than team size)
        actual_mutations = min(n_mutations, len(members))

        if actual_mutations > 0:
            # Select random positions to replace
            positions_to_replace = rng.choice(len(members), size=actual_mutations, replace=False)

            # Get policies not currently in the team for replacement candidates
            current_set = set(members)
            available_policies = [p for p in policy_list if p not in current_set]

            if available_policies:
                # Build weights for available policies
                available_weights = np.array([policy_weights.get(p, 0.0) for p in available_policies])
                if available_weights.sum() == 0:
                    available_weights = np.ones(len(available_policies))
                available_weights = available_weights / available_weights.sum()

                # Sample replacements
                replacement_indices = rng.choice(
                    len(available_policies),
                    size=min(actual_mutations, len(available_policies)),
                    replace=False,
                    p=available_weights,
                )

                # Apply mutations
                for i, pos in enumerate(positions_to_replace):
                    if i < len(replacement_indices):
                        members[pos] = available_policies[replacement_indices[i]]

        new_teams.append(team_factory(tuple(members)))

    return new_teams


def run_multi_generation_tournament(
    policies: list[Hashable],
    envs: list[Env],
    config: TournamentConfig,
    team_factory: callable,
    team_size: int,
    n_teams: int,
    n_generations: int,
    min_weight: float = 0.01,
    team_creation_mode: TeamCreationMode = TeamCreationMode.SAMPLE,
    initial_team_mode: InitialTeamMode = InitialTeamMode.RANDOM,
    n_mutations: int = 1,
    team_decay: float = 1.0,
    allow_duplicate_policies: bool = False,
    allow_duplicate_teams: bool = True,
    rng: np.random.Generator | None = None,
) -> MultiGenResult:
    """Run a multi-generation tournament with weighted resampling.

    After each generation, policy weights are updated based on scores.
    Teams are created for the next generation using the specified mode.

    Args:
        policies: List of all policies.
        envs: Environments that score teams.
        config: Tournament configuration.
        team_factory: Function that takes tuple of policies and returns a Team.
        team_size: Number of policies per team.
        n_teams: Number of teams per generation.
        n_generations: Number of generations to run.
        min_weight: Minimum weight to ensure all policies have some chance.
        team_creation_mode: How to create teams (SAMPLE, SAMPLE_WITH_REPLACEMENT, or EVOLVE).
        initial_team_mode: How to create initial teams in generation 0.
        n_mutations: Number of policies to swap per team (only used in EVOLVE mode).
        team_decay: Multiplier for number of teams each generation (default 1.0, no decay).
        allow_duplicate_policies: If True, same policy can appear multiple times in a team.
        allow_duplicate_teams: If True, same team can be created multiple times.
        rng: Random number generator.

    Returns:
        MultiGenResult with all generation results and final weights.
    """
    if rng is None:
        rng = np.random.default_rng()

    # Initialize with uniform weights
    weights = {p: 1.0 / len(policies) for p in policies}

    generations = []
    prev_teams: list[Team] = []
    prev_team_scores: dict[Team, float] = {}

    for gen in range(n_generations):
        # Calculate number of teams for this generation (with decay)
        current_n_teams = max(1, int(n_teams * (team_decay**gen)))

        # Determine if we allow duplicate policies (from mode or explicit flag)
        dup_policies = allow_duplicate_policies or team_creation_mode == TeamCreationMode.SAMPLE_WITH_REPLACEMENT

        # Create teams based on mode
        if gen == 0:
            # Initial generation: use initial_team_mode
            if initial_team_mode == InitialTeamMode.CLONES:
                # Each team is N copies of a single policy
                teams = create_clone_teams(
                    policies=policies,
                    team_size=team_size,
                    team_factory=team_factory,
                )
            else:
                # RANDOM mode: sample teams by policy weight
                teams = sample_teams_weighted(
                    policies=policies,
                    weights=weights,
                    team_size=team_size,
                    n_teams=current_n_teams,
                    team_factory=team_factory,
                    rng=rng,
                    allow_duplicate_policies=dup_policies,
                    allow_duplicate_teams=allow_duplicate_teams,
                )
        elif team_creation_mode in (TeamCreationMode.SAMPLE, TeamCreationMode.SAMPLE_WITH_REPLACEMENT):
            # SAMPLE mode: sample teams by policy weight
            teams = sample_teams_weighted(
                policies=policies,
                weights=weights,
                team_size=team_size,
                n_teams=current_n_teams,
                team_factory=team_factory,
                rng=rng,
                allow_duplicate_policies=dup_policies,
                allow_duplicate_teams=allow_duplicate_teams,
            )
        else:
            # EVOLVE mode: evolve from previous teams
            teams = evolve_teams(
                prev_teams=prev_teams,
                team_scores=prev_team_scores,
                policies=policies,
                policy_weights=weights,
                n_teams=current_n_teams,
                n_mutations=n_mutations,
                team_factory=team_factory,
                rng=rng,
            )

        # Run tournament
        result = run_tournament(teams, envs, config)

        # Store teams and scores for potential evolution in next generation
        prev_teams = teams
        prev_team_scores = result.team_scores

        # Store generation result
        generations.append(
            GenerationResult(
                generation=gen,
                result=result,
                policy_weights=weights.copy(),
            )
        )

        # Update weights: set directly from scores (with min floor), then normalize
        # The accumulation effect comes implicitly from team composition
        new_weights = {}
        for p in policies:
            score = result.policy_scores.get(p, min_weight)
            new_weights[p] = max(score, min_weight)

        # Normalize to sum to 1
        total = sum(new_weights.values())
        weights = {p: w / total for p, w in new_weights.items()}

    return MultiGenResult(
        generations=generations,
        final_weights=weights,
    )


def print_generation_summary(
    multi_result: MultiGenResult,
    top_n: int = 10,
):
    """Print a summary of multi-generation tournament results."""
    print("\nMulti-Generation Tournament Summary")
    print("=" * 70)

    for gen_result in multi_result.generations:
        gen = gen_result.generation
        result = gen_result.result
        top_policies = result.top_policies(top_n)

        print(f"\nGeneration {gen + 1}")
        print("-" * 40)
        for i, (policy, score) in enumerate(top_policies[:5], 1):
            weight = gen_result.policy_weights.get(policy, 0.0)
            print(f"  #{i}: {policy!s:20s} score={score:.4f} weight={weight:.4f}")

    print(f"\nFinal Weights (top {top_n})")
    print("-" * 40)
    sorted_weights = sorted(
        multi_result.final_weights.items(),
        key=lambda x: x[1],
        reverse=True,
    )
    for i, (policy, weight) in enumerate(sorted_weights[:top_n], 1):
        final_score = multi_result.final_result.policy_scores.get(policy, 0.0)
        print(f"  #{i}: {policy!s:20s} weight={weight:.4f} score={final_score:.4f}")


# =============================================================================
# Utility functions
# =============================================================================


def rank_correlation(
    scores1: dict[Hashable, float],
    scores2: dict[Hashable, float],
) -> float:
    """Compute Spearman rank correlation between two score dictionaries.

    Only considers policies present in both dictionaries.
    """
    common_policies = set(scores1.keys()) & set(scores2.keys())
    if len(common_policies) < 2:
        return 0.0

    policies = sorted(common_policies, key=str)
    vals1 = [scores1[p] for p in policies]
    vals2 = [scores2[p] for p in policies]

    # Convert to ranks
    def to_ranks(vals: list[float]) -> np.ndarray:
        return np.argsort(np.argsort(vals))

    ranks1 = to_ranks(vals1)
    ranks2 = to_ranks(vals2)

    # Spearman correlation
    n = len(policies)
    d_squared = sum((r1 - r2) ** 2 for r1, r2 in zip(ranks1, ranks2, strict=True))
    return 1 - (6 * d_squared) / (n * (n**2 - 1))


def print_policy_rankings(
    result: TournamentResult,
    title: str = "Policy Rankings",
    max_display: int | None = None,
    weights: dict[Hashable, float] | None = None,
):
    """Print policy rankings in a readable format.

    Args:
        result: Tournament result containing policy scores.
        title: Title for the output section.
        max_display: Maximum number of policies to display.
        weights: Optional dictionary of policy weights to display alongside scores.
    """
    print(f"\n{title}")
    print("=" * 60)

    sorted_policies = sorted(
        result.policy_scores.items(),
        key=lambda x: x[1],
        reverse=True,
    )

    if max_display is not None:
        sorted_policies = sorted_policies[:max_display]

    if weights is not None:
        for i, (policy, score) in enumerate(sorted_policies, 1):
            weight = weights.get(policy, 0.0)
            print(f"#{i:3d}: {policy!s:20s} score={score:.4f}  weight={weight:.4f}")
    else:
        for i, (policy, score) in enumerate(sorted_policies, 1):
            print(f"#{i:3d}: {policy!s:20s} -> {score:.6f}")


def print_team_scores(
    result: TournamentResult,
    title: str = "Team Scores",
    max_display: int | None = None,
):
    """Print team scores sorted by score."""
    print(f"\n{title}")
    print("=" * 80)

    sorted_teams = sorted(
        result.team_scores.items(),
        key=lambda x: x[1],
        reverse=True,
    )

    if max_display is not None:
        sorted_teams = sorted_teams[:max_display]

    # Check if we have team counts to display
    has_counts = result.team_counts is not None and any(c > 1 for c in result.team_counts.values())

    for i, (team, score) in enumerate(sorted_teams, 1):
        if has_counts:
            count = result.team_counts.get(team, 1)
            print(f"#{i:3d}: {team!s:40s} -> {score:.4f} (x{count})")
        else:
            print(f"#{i:3d}: {team!s:40s} -> {score:.4f}")
