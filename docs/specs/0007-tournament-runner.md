# Tournament Runner V1

> **Status:** Completed **Author:** Nishad **Created:** 2026-01-15

## Summary

System for competitive evaluation of user-submitted policies.

## Problem

Users submit policies and want to see how they rank against others. Need automated match scheduling, qualification
gates, and leaderboards.

## Solution

Users submit policies to **Seasons**. Each season contains **Pools** where matches happen. A **Commissioner** runs as a
background process managing the season: handling promotions/relegations between its constituent Pools. Each pool has a
**Referee** that decides what matches to schedule for its policies. A **Scorer** computes leaderboard rankings from
match results.

## Goals

- We set up a more future-proof data model than we previously had with eval-scheduler. One with multiple seasons,e tc.
- We gate submissions from contributing to the combinatorial explosion by checking if they succeed a basic test first
- We have simple multi-submitted-policy interactive games for rankings
- Leaderboard rankings roughly correspond value over replacement
- Softmax website and cogames cli are updated to use this setup
- Old tournament code is removed

## Non-goals

- Teams-based matchmaking (searching for best teams rather than exhaustive pairwise)
- Specific latency targets

## Design

### Commissioner

Each cycle:

1. Sync match statuses from job statuses
2. Sync match scores from episode metrics
3. For each pool, ask referee for matches to schedule (up to `MAX_OUTSTANDING_MATCHES=5` total)
4. Apply membership changes (promotions, retirements)

### Referee

Decides what matches to schedule for a pool. Given current pool membership and match history, returns list of
`MatchRequest`s.

`MatchRequest` contains:

- `pool_player_ids` - which pool players participate
- `assignments` - maps agent slot to policy index, e.g. `[0, 0, 1, 1]` for 2v2
- `env` - MettaGridConfig
- `seed`,
- `episode_tags`

### Scorer

Computes per-policy scores from completed matches, and so is responsible for leaderboard rankings.

## Data Model

```
Season
  id, name, description, created_at
  → pools[]

Pool
  id, season_id, name, created_at
  → players[], matches[]

PoolPlayer
  id, pool_id, policy_version_id, retired, created_at

Match
  id, pool_id, job_id, assignments[], status, created_at, completed_at
  → players[]

MatchPlayer
  id, match_id, pool_player_id, policy_index, score

MembershipChange
  id, pool_player_id, action (add|remove), notes, created_at
```

`MatchStatus`: pending → scheduled → running → completed|failed

## Current Implementation: Beta Season

`BetaCommissioner` manages pool membership like so:

1. User submits policy → added to qualifying pool
2. Once SelfPlayReferee is done with it, if it scores on avg above a threshold (0.1), policy is upgraded to
   "competition" pool, else retired
3. `PairingReferee` schedules matches between all pairs in "competition" pool

### SelfPlayReferee: qualifying pool

Schedules two matches (with at most 3 failures) of pure self-play on Machina 1 open world with 4 agents.

### PairingReferee: competition pool

- Schedules 5 matches per configuration pair of policies in the pool.
- Configurations are: `[0, 1, 1, 1]`, `[0, 0, 0, 1]`, `[0, 0, 1, 1]` (1v3, 3v1, 2v2)
- Schedules to maximize coverage first (one of each config per pair), then replicates
- Uses Machina1OpenWorldSharedRewards mission

### WeightedScorer

Weights each policy's score by fraction of agents it controlled, allowing fair comparison across different
configurations.
