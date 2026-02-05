# Tournament Simulation Tools

These scripts were vibe-coded to explore tournament dynamics for policy ranking. They simulate multi-generation
tournaments where policies are grouped into teams, scored by environments, and then resampled based on performance.

## Core Concepts

- **Policy**: An individual unit to be ranked (e.g., a card, a player with skills, a simple score)
- **Team**: A group of policies that compete together
- **Environment**: Scores teams (higher is better)
- **Generation**: One round of team creation, scoring, and weight update

## Files

- `tournament.py` - Core framework with normalization, aggregation, and multi-generation support
- `additive_adapter.py` - Simple simulation where team score = sum of policy scores
- `poker_adapter.py` - Poker hands as teams, cards as policies
- `cogsguard_adapter.py` - Skill-based assignment problem (policies have skills, environments have requirements)

## Quick Examples

### Additive Scoring

Basic run with policies having scores 0, 10, or 11:

```bash
uv run python additive_adapter.py --scores=0,0,10,10,10,11,11,11 --teams=100 --team-size=3
```

Multi-generation with compounding (use `sample_replace` for proper compounding):

```bash
uv run python additive_adapter.py \
  --scores=10,10,10,11,11,11 \
  --team-creation=sample_replace \
  --generations=50 \
  --teams=1000 \
  --team-size=1 \
  --min-weight=0
```

Plot weight evolution:

```bash
uv run python additive_adapter.py \
  --scores=0,0,10,10,11,11 \
  --team-creation=sample_replace \
  --generations=30 \
  --teams=500 \
  --team-size=3 \
  --plot-weights=6 \
  --plot-file=weights.png
```

### Poker

Single generation:

```bash
uv run python poker_adapter.py --hands=1000
```

With both standard and lowball environments:

```bash
uv run python poker_adapter.py --hands=500 --envs standard lowball
```

### CogsGuard

Policies have skills (mining, scrambling, aligning), environments have requirements:

```bash
uv run python cogsguard_adapter.py --policies=20 --teams=100 --envs=5 --show-assignments
```

## Key Options

### Team Creation Modes (`--team-creation`)

- `sample` - Sample policies without replacement within a team (default)
- `sample_replace` - Sample with replacement (allows duplicate policies in a team)
- `evolve` - Evolve teams from previous generation by mutation

### Normalization Stages

1. **Scale invariance** (`--scale`): `divide_by_max` or `rank`
2. **Advantage exaggeration** (`--power=K` or `--temperature=T`): Optional transform
3. **Environment balancing** (`--balance`): `max_1` or `total_1`

### Other Useful Options

- `--generations=N` - Run N generations with weight updates
- `--min-weight=0` - Allow policies to go to zero weight
- `--team-size=K` - Number of policies per team
- `--initial-teams=clones` - Start with clone teams (one policy repeated K times)
- `--verbose` - Show detailed output

## Understanding Weight Dynamics

With team size > 1 and `--team-creation=sample` (no replacement), weights tend to stabilize because:

1. Better policies appear on better teams
2. But with mixed team composition, the marginal advantage shrinks as good policies become prevalent

With `--team-creation=sample_replace` or `--team-size=1`, weights compound properly because policies can dominate teams.

Example showing compounding with team size 1:

```bash
uv run python additive_adapter.py \
  --scores=10,11 \
  --team-creation=sample_replace \
  --generations=20 \
  --teams=1000 \
  --team-size=1 \
  --min-weight=0
```

After 20 generations, the score-11 policy should dominate (~85% weight).
