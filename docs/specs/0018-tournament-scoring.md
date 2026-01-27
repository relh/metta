# Tournament Scoring

> **Status:** Approved **Author:** Alex Smith **Created:** 2026-01-23

## Summary

A scoring system for determining which policies win the benchmark each season, using an evolutionary tournament approach
where teams compete across environments and evolve based on performance.

## Problem

We need a scoring system to determine which policies win the benchmark each season. The system must handle a fixed
policy pool for end-of-season tournaments while being adaptable to continuous mid-season evaluation.

## Solution

Run the tournament as a series of rounds. In each round, teams compete across multiple environments. Each environment is
"the map" with a different seed, and each team plays on each seed for that round.

### Initialization

Each policy initially plays on environments with N-1 NPCs.

### Evolution

Between rounds, new teams are generated from prior teams using evolutionary sampling:

1. **Score normalization:** `normalized_team_env_score = team_env_score / max_score_on_this_env`
2. **Team scoring:** `team_score = sum(normalized_team_env_scores)`
3. **Policy scoring:** `policy_score = sum(team_score, for teams this policy is in)`

For team evolution, teams are sampled from existing teams in proportion to their score. Each member is replaced with
probability p, with replacements sampled from policies in proportion to their score.

### Final scoring

After M rounds, the top K policies (according to their score) are declared winners.

**Note** that the various normalizations and evolution functions are easy to swap, and thus iterate on. The architecture
of having fixed rounds is more expensive to update.

## Goals

- [ ] Scoring is team-centric
- [ ] Scoring is relatively unaffected by the addition of weak policies (e.g., determining "the best basketball players"
      isn't impacted by whether anyone at Softmax plays basketball)
- [ ] Scoring is sufficiently easy for competitors to understand
- [ ] Scoring is sufficiently efficient to compute
- [ ] Policy scoring captures "the chance that this policy is on the winning team"

## Non-Goals

- Continuous mid-season tournament design (deferred for future work)
- Agent memory persistence across team evolution (noted as possible but not required)

## Design

### Infinite Compute Reference Model

With infinite compute, we would: form every potential team, run them against every environment, normalize scores per
environment, combine (team, env) scores to get a single score per team, then derive per-policy scores from team scores.
With this as a mental model, we consider ways we could run these normalizations and generate per-policy scores.

### Environment Score Normalization Options

| Normalization               | Impact                                                                                                                                                                                                                                    |
| --------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| z-scores                    | Rewards doing well in environments with low variance. Not between [0, 1], and in particular, generates negative scores.                                                                                                                   |
| Divide by max               | Keeps scores linear, so agents should try to maximize mean score. Makes each environment give a maximum of 1 point.                                                                                                                       |
| Subtract min, divide by max | Removes "points that everybody gets". Makes scoring somewhat less linear.                                                                                                                                                                 |
| Rank, divide by num_teams   | Rewards "beating the pack" but not "by how much". Uses most of the space for poorly performing teams. Can be turned into odds/log-odds. Doesn't require scores, just win vs loss. Makes scoring non-linear with respect to the raw score. |
| Softmax                     | Emphasizes getting close to max score with exponential falloff. Not scale invariant.                                                                                                                                                      |
| (other normalization)^k     | Taking to the kth power pushes closer to "winner takes all". Somewhat emulates "do this for k generations".                                                                                                                               |
| exp(other normalization)    | Particular linear combination of rank^k. Ends up being softmax after further normalization.                                                                                                                                               |

Our current proposal is to just divide by the maximum score on the environment. This is simple, and makes each
environment equally important to do well on. (Exponential results may come implicitly via the generational effect.)

Taken directly, this is _not_ the probability of the team winning; but this does model something like "resources
available for reproduction".

### Team Scoring Options

| Function        | Impact                                                                                                                                                                                                                                                                           |
| --------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| mean/ sum       | Values incremental improvements equally across all environments. E.g., team scoring (0.9, 0.0) valued same as (0.45, 0.45). If (team, env) scores represent "chance of winning on env X", this is "chance of winning overall" assuming uniform distribution across environments. |
| Some percentile | Rewards doing well X% of the time. Discards outliers.                                                                                                                                                                                                                            |

Mean seems like the obvious default here. Note that mean and sum are equivalent up to a rescaling, since every team
should have a score for every environment.

### Policy Scoring Options

| Function            | Impact                                                                 |
| ------------------- | ---------------------------------------------------------------------- |
| mean of team scores | Seems "obvious" but punishes policies for being on bad teams.          |
| sum of team scores  | Effectively turns into "probability of you being on the winning team". |

Sum seems correct here -- a policy should not be considered worse just because it's drafted onto a bad team. For
comparison, consider a "ability to metabolize sucrose" gene. Its success should be measured by it being part of every
successful team, rather that it also being part of a bunch of failed teams.

### Team Evolution Methods

| Method                          | Description                                                                                                                                                                                                                            |
| ------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Random sampling                 | Create new teams from randomly sampled policies. Fails to preserve team structure. Rewards good generalists.                                                                                                                           |
| Weighted sampling with mutation | Teams sampled relative to weight, then mutated. Sample a team, for each member swap with probability lambda, replace with policy sampled proportionally to weight. Could limit duplication. Allows successful teams to mostly survive. |
| Breeding                        | Two teams chosen relative to weight, component policies mixed. Allows successful pairings to persist and merge. Could use chromosomes for clumped transfer.                                                                            |

### Team Seeding

| Method                                                | Description                                                                                                                                                                                                       |
| ----------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Each team is all a single policy                      | Allows failed policies to be totally weeded out at a first step. Also wipes out specialists. Starts with a team structures that violates what we expect to have long term (limit of 1 copy of a policy per team). |
| Each team is a single submitted policy + default NPCs | Dovetails well with the "real" game. Useless policies may be "carried", so we'll need to do more work to filter them.                                                                                             |

We should endeavor to use the "play with NPCs" option, since this fits better with batteries included (you don't need a
policy that's good at everything). We can have a minimum score of what a noop agent scores, and filter any policy that
doesn't pass this threshold.

### Experimental Validation

**Poker Hands:** Evolutionary approach drives to winner-take-all four of a kind. Which rank dominates depends on scoring
(by rank: aces; by hand value: any card). Four of a kind dominates over flush/royal flush because it's easier to
hill-climb to and more robust ("almost four of a kind" is three of a kind; "almost flush" is garbage). Poker strongly
rewards homogeneity, unlike desired tournament behavior.

**CvC Lite:** Game with environment difficulties and policy skill scores for mining/scrambling/aligning. Team score =
minimax of (team_activity_skill / activity_difficulty). Results:

- Much less collapse to dominant policies vs poker (CvC rewards diversity)
- Top policies tend to be "the best" (5 skill points), though some weaker policies get lucky team placement
- Larger teams support spiky policies better
- Modest extinction at beginning, followed by semi-stable mixing

## Open Questions

1. How should the mutation probability p be tuned? Should this just be "1 policy is evicted"?
2. How do we adapt this end-of-season tournament to continuous mid-season evaluation?
3. Should we support agent memory persistence across team evolution?
4. What constraints on team duplication are appropriate?
5. How many rounds do we need to run in order to get appropriate mixing?
6. How do we ensure that dead weight is eliminated?
