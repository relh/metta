# Agent Metrics

> **Status:** Draft **Author:** Marty Hess **Created:** 2026-01-31

## Summary

Define two families of agent metrics: **internal metrics** that help Softmax understand whether customers are improving
their agents, and **customer-facing metrics** that help customers understand where their training is improving and where
it is lagging. These metrics are derived from data already flowing through the system (environment stats, evaluation
results, tournament matches) but are not yet surfaced in a structured way for either audience.

## Problem

Today, metrics are scattered across systems with no unified taxonomy:

- The **training loop** logs ~30 metrics to W&B (rewards, losses, entropy, timing) but these are raw training signals,
  not interpretable performance summaries.
- The **environment** (mettagrid) produces per-agent stats (`heart.gained`, `chest.heart.deposited`, etc.) but these are
  game internals, not user-facing indicators.
- **Evaluation** aggregates per-episode rewards by category but doesn't track improvement over time.
- The **tournament** computes weighted scores and leaderboard rankings but only from match reward sums.
- The **Observatory DB** stores `EpisodePolicyMetric` rows but almost exclusively just `reward` and `action_timeout`.

The result:

- **Customers** cannot answer "is my agent getting better at combat?" or "why did my score plateau?" They see a single
  reward number and a leaderboard rank. There is no breakdown by capability, no trend visualization, and no diagnostic
  guidance.
- **Softmax internally** cannot answer "are customers improving over time?" or "which customers are stuck?" without
  manually querying W&B and tournament databases. There is no aggregate health signal across the customer base.

## Solution

Define concrete metrics for each audience, specify how each is computed, and identify where each should be surfaced.
Metrics are organized into categories that answer specific questions.

### Metric Order Classification

Each metric is classified by its derivation complexity. This matters for implementation because higher-order metrics
depend on lower-order ones being computed and stored first.

| Order | Name      | Definition                                                                                                                                  | Example                                                                                                |
| ----- | --------- | ------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| 1st   | Raw       | A discrete value from a single episode or event. Directly observed, not computed from other metrics.                                        | `reward`, `heart.gained`, `tournament_rank`                                                            |
| 2nd   | Aggregate | A simple operation (sum, mean, count, stddev) over multiple instances of the **same** 1st-order metric across a time window or episode set. | `win_rate` (mean of per-match win flag), `consistency` (stddev of match scores)                        |
| 3rd   | Composite | A combination of **different** metrics, possibly across a time window. Requires multiple 1st- or 2nd-order inputs.                          | `resource_efficiency` (deposited / gathered), `improvement_rate` (diff of eval_scores across versions) |

## Training Modes

Customers use the platform with different objectives. Knowing the customer's intent lets the Observatory surface the
most relevant metrics by default instead of showing everything equally.

### Mode Definitions

| Mode           | Tag Value     | Primary Metric Categories              | Description                                                                                                   |
| -------------- | ------------- | -------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| Skill Training | `skill`       | Behavioral Capabilities                | Focus on specific skills (resource gathering, combat, territory control) without concern for overall win rate |
| Performance    | `performance` | Overall Performance, Training Progress | Improve aggregate score and track training effectiveness outside competition                                  |
| Competition    | `competition` | Competitive Standing                   | Optimize for tournament rankings and match results                                                            |

### How Mode Is Expressed

Training mode is a property of a **policy version**, not of individual episodes. A single version may be evaluated
across many episode types (self-play, pairing, various simulations), but the intent that produced it is singular.

- **Storage**: `policy_version_tags` with key `training_mode` and value `skill`, `performance`, or `competition`
- **Set by**: Training pipeline automatically (from `EvaluatorConfig`) or customer manually via API
- **API**: `PUT /stats/policies/versions/{id}/tags` (existing endpoint, no changes needed)

### Design Rules

- **All metric categories remain visible** regardless of mode. Mode controls which dashboard is primary/default, not
  which data exists.
- **Mode is optional.** Versions without a `training_mode` tag show all dashboards equally. This preserves backwards
  compatibility — existing versions without the tag continue to work as they do today.
- **Mode can change between versions.** A customer might train v1–v5 in `skill` mode, then switch to `performance` for
  v6+. Each version independently declares its intent.

## Model Version Metadata

Customers iterate on different neural network architectures and training algorithms. Structured metadata on policy
versions enables filtering and comparison ("show all transformer runs", "PPO vs GRPO across versions").

### Reserved Policy Version Tags

| Tag Key              | Example Values                         | Purpose                                                     |
| -------------------- | -------------------------------------- | ----------------------------------------------------------- |
| `training_mode`      | `skill`, `performance`, `competition`  | Selects primary metric dashboard (see Training Modes above) |
| `model_architecture` | `transformer`, `mamba`, `gtrxl`, `mlp` | Neural network backbone type                                |
| `algorithm`          | `ppo`, `grpo`, `cmpo`                  | Training algorithm used                                     |
| `model_version`      | `v2.1`, `alpha-3`                      | Customer's own version label for their model lineage        |

These tags are **queryable** (indexed on `(key, value)` in `policy_version_tags`) and returned in all policy version API
responses.

### Metadata Layering

| What                                                            | Where                                 | Why                                        |
| --------------------------------------------------------------- | ------------------------------------- | ------------------------------------------ |
| Queryable labels (architecture, algorithm, mode)                | `policy_version_tags`                 | Indexed, filterable across versions        |
| Detailed config (layer sizes, attention heads, hyperparameters) | `policy_versions.attributes` (JSONB)  | Inspected per-version, not filtered across |
| Serialized policy for loading                                   | `policy_versions.policy_spec` (JSONB) | Runtime loading only, not display metadata |

Tags are **set automatically by the training pipeline** when `EvaluatorConfig` includes the corresponding fields, and
can be **overridden via API** by the customer at any time.

## Episode Source Tags

Episodes are produced by different systems (training evaluator, tournament, manual CLI). Tagging each episode's source
enables mode-aware filtering — skill mode can show training evaluations while competition mode shows tournament matches.

### Reserved Episode Tags

| Tag Key            | Values                                                                            | Set By                                              |
| ------------------ | --------------------------------------------------------------------------------- | --------------------------------------------------- |
| `source`           | `training_eval`, `tournament_qualifying`, `tournament_competition`, `manual_eval` | Evaluator, tournament referees, CLI tools           |
| `curriculum_stage` | Free-form (e.g., `resource_gathering`, `combat`, `exploration`)                   | Evaluator, from curriculum state at checkpoint time |

These supplement the existing episode tags (`job_id`, `category`, `name`, `match_type`, `game`) and are queryable via
the existing `tag_filters` parameter on `POST /stats/episodes/query`.

### Mode-Aware Filtering

Each mode uses source tags to scope the episodes shown by default:

| Mode        | Default Episode Filter                                            | Grouping                                                |
| ----------- | ----------------------------------------------------------------- | ------------------------------------------------------- |
| Skill       | `source=training_eval`                                            | Group by `curriculum_stage` to show per-skill breakdown |
| Performance | `source=training_eval`                                            | Show reward trajectory across policy versions           |
| Competition | `source=tournament_qualifying` or `source=tournament_competition` | Show match results and standings                        |

### Dashboard Routing

The Observatory UI reads `training_mode` from the policy version tags and adjusts the default view:

1. Read `training_mode` from the policy version's tags
2. Default the dashboard to the mode's primary metric categories
3. Apply the mode's default episode source filter
4. Allow the customer to switch to other categories — mode is a default, not a restriction
5. When no mode is set, show all categories equally (backwards-compatible)

## Customer-Facing Metrics

Metrics surfaced to customers via Observatory UI, CLI evaluation output, and tournament dashboard. All are computed
per-policy-version so customers can compare across training checkpoints.

### Overall Performance

> **Primary for:** `performance` mode

These answer: "How good is my agent?"

| Metric              | Order | Definition                                                   | Source                                     | Status            |
| ------------------- | ----- | ------------------------------------------------------------ | ------------------------------------------ | ----------------- |
| `score`             | 2nd   | Weighted average reward across tournament matches            | `MatchPlayer.score` via `WeightedScorer`   | Exists            |
| `win_rate`          | 2nd   | Fraction of matches where policy scored above median         | Computed from `MatchPlayer` scores         | New               |
| `reward_trajectory` | 2nd   | Reward over training steps (area under reward curve)         | `area_under_reward` in `stats_reporter.py` | Exists (W&B only) |
| `eval_score`        | 2nd   | Average reward across evaluation episodes by category        | `handle_results.py` category scores        | Exists (W&B only) |
| `consistency`       | 2nd   | Standard deviation of match scores (lower = more consistent) | Computed from `MatchPlayer` scores         | New               |

### Behavioral Capabilities

> **Primary for:** `skill` mode

These answer: "What is my agent good and bad at?" Derived from environment stats, aggregated across evaluation episodes.

| Metric                 | Order | Definition                                               | Source Stat                                                          | Status            |
| ---------------------- | ----- | -------------------------------------------------------- | -------------------------------------------------------------------- | ----------------- |
| `resource_gathering`   | 2nd   | Average resources collected per episode                  | `heart.gained`, `carbon.gained`, `oxygen.gained`, etc.               | New (stats exist) |
| `resource_efficiency`  | 3rd   | Resources deposited / resources gathered                 | `chest.heart.deposited_by_agent` / `heart.gained`                    | New (stats exist) |
| `territory_control`    | 2nd   | Average junctions held by agent's collective             | `collective.aligned.junction.held`                                   | New (stats exist) |
| `combat_effectiveness` | 3rd   | Net alignment actions (aligned - scrambled by opponents) | `junction.aligned_by_agent` - opponent `junction.scrambled_by_agent` | New (stats exist) |
| `survivability`        | 2nd   | Average steps alive per episode                          | `steps` from episode stats                                           | New (stats exist) |
| `cooperation`          | 3rd   | Score differential in team vs solo play                  | Comparison of 2v2 vs 1v3 match scores                                | New               |
| `action_reliability`   | 3rd   | 1 - (action_timeouts / total_steps)                      | `action_timeout` metric                                              | Exists (raw only) |

### Training Progress

> **Primary for:** `performance` mode

These answer: "Is my training working? Where is it stuck?"

| Metric              | Order | Definition                                            | Source                                                | Status            |
| ------------------- | ----- | ----------------------------------------------------- | ----------------------------------------------------- | ----------------- |
| `improvement_rate`  | 3rd   | Score delta between consecutive policy versions       | Diff of `eval_score` across versions                  | New               |
| `plateau_detection` | 3rd   | Flag when improvement_rate < threshold for N versions | Computed from `improvement_rate` series               | New               |
| `regression_alert`  | 3rd   | Flag when latest version scores below previous best   | Comparison across `eval_score` history                | New               |
| `capability_delta`  | 3rd   | Per-capability change between versions                | Diff of behavioral capability metrics across versions | New               |
| `training_steps`    | 1st   | Total environment steps at this checkpoint            | `metric/agent_step` from training                     | Exists (W&B only) |

### Competitive Standing

> **Primary for:** `competition` mode

These answer: "How do I compare to others?"

| Metric             | Order | Definition                                    | Source                    | Status |
| ------------------ | ----- | --------------------------------------------- | ------------------------- | ------ |
| `tournament_rank`  | 1st   | Position on leaderboard                       | Leaderboard query         | Exists |
| `percentile`       | 2nd   | Rank as percentile of all active policies     | Computed from leaderboard | New    |
| `score_vs_top`     | 3rd   | Score gap to #1 ranked policy                 | Leaderboard comparison    | New    |
| `promotion_status` | 1st   | Whether policy qualified for competition pool | `PoolPlayer` membership   | Exists |
| `matches_played`   | 2nd   | Total completed tournament matches            | `MatchPlayer` count       | Exists |

## Internal Metrics

Metrics for the Softmax team to monitor customer health and product effectiveness. Not exposed to customers.

### Per-Customer Health

| Metric                   | Order | Definition                                    | Source                            | Status |
| ------------------------ | ----- | --------------------------------------------- | --------------------------------- | ------ |
| `versions_submitted`     | 2nd   | Total policy versions uploaded to tournament  | `PolicyVersion` count per user    | New    |
| `submission_frequency`   | 2nd   | Policy versions per week                      | `PolicyVersion` timestamps        | New    |
| `best_score`             | 2nd   | Highest tournament score achieved             | Max `MatchPlayer.score` per user  | New    |
| `score_trajectory`       | 2nd   | Best score over time (is customer improving?) | Time series of `best_score`       | New    |
| `days_since_improvement` | 3rd   | Days since last score increase                | `score_trajectory` staleness      | New    |
| `peak_rank`              | 2nd   | Best leaderboard position achieved            | Min rank from leaderboard history | New    |
| `active`                 | 3rd   | Submitted a version in the last 7 days        | `submission_frequency` threshold  | New    |

### Aggregate Platform Health

| Metric                     | Order | Definition                                           | Source                                  | Status |
| -------------------------- | ----- | ---------------------------------------------------- | --------------------------------------- | ------ |
| `active_customers`         | 2nd   | Customers with a submission in last 7 days           | Count of `active` users                 | New    |
| `improving_customers`      | 3rd   | Customers whose best score increased this week       | `score_trajectory` filter               | New    |
| `stuck_customers`          | 3rd   | Customers with >14 days since improvement            | `days_since_improvement` filter         | New    |
| `median_best_score`        | 2nd   | Median of all customers' best scores                 | Aggregate `best_score`                  | New    |
| `score_distribution`       | 2nd   | Histogram of customer best scores                    | Aggregate `best_score`                  | New    |
| `churn_risk`               | 3rd   | Customers with declining submission frequency        | `submission_frequency` trend            | New    |
| `tournament_participation` | 3rd   | Fraction of customers with active tournament entries | `PoolPlayer` active count / total users | New    |

## Data Sources

Where each metric's raw data comes from today:

```
Training Loop (W&B)
  └─ rewards, losses, entropy, timing, throughput, area_under_reward
       └─ feeds: reward_trajectory, training_steps

Environment (mettagrid episode_stats)
  ├─ game stats: chest.heart.deposited, junctions, ...
  ├─ agent stats: heart.gained, carbon.gained, junction.aligned_by_agent, ...
  └─ collective stats: collective.aligned.junction.held, ...
       └─ feeds: all behavioral capability metrics

Evaluation (handle_results.py)
  └─ per-category scores, per-simulation scores
       └─ feeds: eval_score, improvement_rate, plateau/regression detection

Tournament (commissioner + scorer)
  ├─ MatchPlayer.score (weighted per-agent reward)
  ├─ Leaderboard rankings
  └─ Pool membership (qualifying → competition)
       └─ feeds: score, win_rate, consistency, tournament_rank, percentile

Observatory DB (EpisodePolicyMetric)
  └─ reward, action_timeout per episode per policy
       └─ feeds: action_reliability, matches_played
```

### Gaps

The following data is **not currently persisted** and would need to be added:

1. **Per-agent environment stats in Observatory** -- today only `reward` and `action_timeout` are stored as
   `EpisodePolicyMetric`. The behavioral capability metrics require storing additional stats like `heart.gained`,
   `junction.aligned_by_agent`, etc. The schema supports this (metric_name is a string), but the recording code in
   `episode_recording.py` only writes reward and timeout.

2. **Per-customer aggregation** -- no customer/user-level aggregation exists. The tournament has `PoolPlayer` per policy
   version but no roll-up by user across versions over time.

3. **Historical leaderboard snapshots** -- current leaderboard is a point-in-time query. Tracking rank over time
   requires periodic snapshots or a changelog.

4. **Cross-version comparison** -- no built-in mechanism to compare metrics between two policy versions of the same
   policy. This is needed for improvement_rate, capability_delta, and regression detection.

## Design

### Where This Lives

All metrics computation and serving centralizes in **`app_backend/src/metta/app_backend/metrics/`**. This is the right
location because:

- `app_backend` already owns the Observatory API, episode DB, and tournament system -- the primary data sources
- It can import `metta.common` and `metta_alo` (scoring) per the import linter rules
- Customer-facing metrics are served via new Observatory API endpoints alongside existing routes
- Internal metrics query the same DB tables (policies, episodes, matches) that `app_backend` already manages
- No new dependency violations or packages required

```
app_backend/src/metta/app_backend/metrics/
├── __init__.py
├── capabilities.py       # Behavioral capability metrics from episode agent stats
├── training_progress.py  # Cross-version improvement, plateau, regression detection
├── competitive.py        # Tournament rank, percentile, win rate
├── customer_health.py    # Internal: per-customer aggregates
├── platform_health.py    # Internal: platform-wide aggregates
└── routes.py             # API endpoints exposing metrics to Observatory frontend
```

### Shared Tag Constants

Reserved tag keys (`training_mode`, `model_architecture`, `algorithm`, etc.) must be importable by both `metta.rl`
(training pipeline writes tags) and `metta.app_backend` (Observatory reads/filters by tags). Per the import linter
rules, shared constants go in `common/src/metta/common/` — the bottom of the layer hierarchy, importable by all
`metta.*` packages. A `tag_conventions` module there defines the canonical key names and valid values.

### Why Not Other Locations

| Location                   | Why not                                                                      |
| -------------------------- | ---------------------------------------------------------------------------- |
| `metta/rl/`                | Training-time only; can't access tournament/Observatory data at serving time |
| `common/`                  | Too low in the import hierarchy; can't import app_backend models             |
| `mettagrid/`               | Environment-only; no access to tournament or cross-episode data              |
| `cogames/` or `metta_alo/` | Forbidden from importing `metta.*` or `app_backend` by import linter         |
| `softmax/`                 | Currently CI/GitHub health metrics; different purpose and audience           |
| New top-level package      | Unnecessary complexity; app_backend already has all the data and access      |

### Data Collection Changes

The metrics module consumes data, but one upstream change is needed to feed it: `episode_recording.py` must persist
additional per-agent environment stats (e.g., `heart.gained`, `junction.aligned_by_agent`) as `EpisodePolicyMetric`
rows. The schema already supports arbitrary metric names -- only the recording code needs to write them.

## Goals

- [ ] Define metric names and computation methods for both families
- [ ] Identify which metrics exist today vs. need new collection/computation
- [ ] Map metrics to surfacing locations (Observatory UI, CLI, internal dashboard)
- [ ] Expand behavioral capability metrics based on customer feedback

## Non-Goals

- Implementing the metrics pipeline (this spec defines what, not how to build it)
- Designing the Observatory UI for these metrics
- Defining alerting thresholds (these require tuning with real data)
- Metrics for game designers or environment authoring (separate concern)

## Open Questions

1. **Which behavioral capabilities matter most to customers?** The current list is based on CogsGuard game mechanics.
   Customer interviews should validate which breakdowns are actually useful vs. noise.

2. **How should capabilities generalize across games?** `heart.gained` is CogsGuard-specific. If we add more games, do
   we need abstract capability categories (e.g., "resource gathering") that map to different stats per game?

3. **What granularity for training progress?** Should improvement_rate compare every checkpoint, or only versions
   submitted to tournament? Frequent checkpoints give better signal but more noise.

4. **ELO or TrueSkill for competitive standing?** The current weighted score is simple but doesn't account for opponent
   strength. A proper rating system would give better competitive metrics but adds complexity.

5. **Where should internal metrics live?** Separate internal dashboard? Observatory admin view? Existing BI tools?

6. **How do we handle team-based metrics?** In team games (2v2), individual capability metrics may not reflect the
   agent's actual contribution. Do we need team-aware attribution?

7. **What defines a "customer" for internal metrics?** A GitHub user? An organization? A policy lineage?

8. **Should customers see opponent-relative metrics?** E.g., "your resource gathering is top 20%" vs. just raw numbers.
   This reveals information about the competitive field.
