# Episode Metrics Data Flow

> **Status:** Draft **Created:** 2026-01-31 **Related:** `metrics_design.md`, `docs/specs/0020-metrics.md`

This document traces the complete journey of agent metrics from episode execution to queryable state in the Observatory.
It covers both the Observatory path (episode-level metrics) and the W&B path (training-loop metrics), which are separate
systems with different data.

## Overview

```
                         TRAINING TIME                           EVAL / TOURNAMENT TIME
                    ┌─────────────────────┐              ┌──────────────────────────────────┐
                    │                     │              │                                  │
  RL Training Loop  │  StatsReporter      │   K8s Pod    │  mettagrid Rollout               │
  (metta/rl/)       │  .report_epoch()    │   executes   │  + StatsTracker                  │
                    │       │              │   episode    │       │                          │
                    │       ▼              │              │       ▼                          │
                    │  W&B API            │              │  PureSingleEpisodeResult         │
                    │  (losses, entropy,  │              │  (rewards, stats, timeouts)      │
                    │   LR, throughput)   │              │       │                          │
                    │                     │              │       ▼                          │
                    │  ┌─────────────┐    │              │  JSON → S3 (results_uri)         │
                    │  │ wandb.log() │    │              │       │                          │
                    │  └─────────────┘    │              │       │                          │
                    └─────────────────────┘              └───────┼──────────────────────────┘
                                                                │
                                                                ▼
                                                   ┌───────────────────────┐
                                                   │ watcher.py            │
                                                   │ (polls K8s pods)      │
                                                   │ _handle_pod_succeeded │
                                                   └───────────┬───────────┘
                                                               │
                                                               ▼
                                                   ┌───────────────────────┐
                                                   │ episode_recording.py  │
                                                   │ record_job_episode()  │
                                                   │                       │
                                                   │ ALL stats → DuckDB   │
                                                   │ (one file per episode)│
                                                   └───────────┬───────────┘
                                                               │
                                                               ▼
                                                   ┌───────────────────────┐
                                                   │ StatsClient           │
                                                   │ .bulk_upload_episodes │
                                                   │                       │
                                                   │ 1. Get presigned URL  │
                                                   │ 2. PUT DuckDB → S3   │
                                                   │ 3. POST /complete    │
                                                   └───────────┬───────────┘
                                                               │
                                              ┌────────────────┼────────────────┐
                                              │                │                │
                                              ▼                ▼                │
                                     ┌──────────────┐  ┌──────────────┐        │
                                     │ S3 (durable) │  │ PostgreSQL   │        │
                                     │ ALL metrics  │  │ reward ONLY  │        │
                                     │ per agent    │  │ per policy   │        │
                                     │              │  │ version      │        │
                                     │ episodes/    │  │              │        │
                                     │ {id}.duckdb  │  │ episode_     │        │
                                     └──────────────┘  │ policy_      │        │
                                                       │ metrics      │        │
                                                       └──────┬───────┘        │
                                                              │                │
                                                              ▼                │
                                                   ┌───────────────────┐       │
                                                   │ Observatory API   │       │
                                                   │ /stats/episodes/  │       │
                                                   │ query             │       │
                                                   └───────────────────┘       │
                                                              │                │
                                                              ▼                │
                                                   ┌───────────────────┐       │
                                                   │ Tournament        │◄──────┘
                                                   │ _sync_match_scores│
                                                   │ → Leaderboard     │
                                                   └───────────────────┘
```

## Step 1: Episode Execution

An episode runs inside a K8s pod as an isolated subprocess.

**Key files:**

- `packages/mettagrid/python/src/mettagrid/simulator/rollout.py` -- `Rollout` class
- `packages/mettagrid/python/src/mettagrid/envs/stats_tracker.py` -- `StatsTracker`
- `packages/cogames/src/metta_alo/pure_single_episode_runner.py` -- `PureSingleEpisodeResult`
- `packages/mettagrid/python/src/mettagrid/types.py` -- `EpisodeStats` TypedDict

**What happens:**

1. `Rollout.__init__()` creates a simulation with agent policies and optionally attaches a `StatsTracker`.
2. `Rollout.run_until_done()` steps the simulation until the episode ends.
3. `StatsTracker.on_episode_end()` collects stats from the C++ simulator:

   ```python
   stats = self._sim.episode_stats  # EpisodeStats TypedDict
   # stats["game"]       → dict[str, float]           (game-level: e.g. total_steps)
   # stats["agent"]      → list[dict[str, float]]     (per-agent: e.g. heart.gained)
   # stats["collective"] → dict[str, dict[str, float]] (optional: e.g. collective.aligned.junction.held)
   ```

4. The subprocess produces a `PureSingleEpisodeResult`:

   ```python
   class PureSingleEpisodeResult(BaseModel):
       rewards: list[float]           # One per agent
       action_timeouts: list[int]     # One per agent
       stats: EpisodeStats            # Full stats structure above
       steps: int                     # Total steps in episode
   ```

5. Result JSON is written to S3 at the job's `results_uri`.

**Data at this stage:** Everything the simulator produces. Nothing is filtered or aggregated.

## Step 2: Job Completion Detection

The Observatory backend watches for completed K8s pods and triggers recording.

**Key files:**

- `app_backend/src/metta/app_backend/job_runner/watcher.py` -- `_handle_pod_succeeded()`

**What happens:**

1. `watcher.py` polls K8s pods via the watch API.
2. When a pod reaches `Succeeded` phase, `_handle_pod_succeeded()` fires.
3. It reads `PureSingleEpisodeResult` from S3 using `_read_results_with_retry()`.
4. It calls `record_job_episode(job_id, job, results, stats_client)`.

**Data at this stage:** Same as step 1 -- full `PureSingleEpisodeResult` in memory.

## Step 3: DuckDB Recording

All agent stats are written to a local DuckDB file. Nothing is filtered at this stage.

**Key files:**

- `app_backend/src/metta/app_backend/job_runner/episode_recording.py` -- `populate_single_episode_duckdb()`
- `app_backend/src/metta/app_backend/episode_stats_db.py` -- DuckDB schema and helpers

**DuckDB schema:**

```sql
episodes              (id, primary_pv_id, replay_url, thumbnail_url, attributes, eval_task_id)
episode_tags          (episode_id, key, value)
episode_agent_policies(episode_id, policy_version_id, agent_id)
episode_agent_metrics (episode_id, agent_id, metric, value)
```

**What happens:**

1. `episode_stats_db()` creates a temporary DuckDB file with the schema above.
2. `populate_single_episode_duckdb()` inserts one episode:

   ```python
   for agent_id, assignment in enumerate(assignments):
       # Policy assignment
       insert_agent_policy(episode_id, policy_version_ids[assignment], agent_id)

       # Explicit metrics
       insert_agent_metric(episode_id, agent_id, "reward", results.rewards[agent_id])
       insert_agent_metric(episode_id, agent_id, "action_timeout", float(results.action_timeouts[agent_id]))

       # ALL agent stats from the simulator
       agent_stats = results.stats["agent"][agent_id]
       for metric_name, metric_value in agent_stats.items():
           insert_agent_metric(episode_id, agent_id, metric_name, metric_value)
   ```

3. `conn.execute("CHECKPOINT")` flushes to disk.

**Granularity:** One DuckDB file per episode. Typical file size: 5-20KB.

**Data at this stage:** Every per-agent metric is stored. For an 8-agent episode with ~50 stats each, that's ~400 metric
rows plus `reward` and `action_timeout` per agent = ~416 rows total.

## Step 4: S3 Upload (Presigned URL Flow)

The DuckDB file is uploaded to S3 via a three-step presigned URL process.

**Key files:**

- `app_backend/src/metta/app_backend/clients/stats_client.py` -- `bulk_upload_episodes()`
- `app_backend/src/metta/app_backend/routes/stats_routes.py` -- presigned URL endpoints

**What happens:**

1. **Request presigned URL:**

   ```
   POST /stats/episodes/bulk_upload/presigned-url
   → { upload_url: "https://s3...", s3_key: "episodes/{upload_id}.duckdb", upload_id: UUID }
   ```

   Presigned URL expires in 1 hour.

2. **Upload DuckDB directly to S3:**

   ```
   PUT {upload_url}
   Content-Type: application/octet-stream
   Body: <duckdb file bytes>
   ```

   5-minute timeout on the HTTP PUT.

3. **Notify backend that upload is complete:**
   ```
   POST /stats/episodes/bulk_upload/complete
   Body: { upload_id: UUID }
   ```
   This triggers PostgreSQL processing (step 5).

**S3 key pattern:** `s3://{POLICY_S3_BUCKET}/episodes/{upload_id}.duckdb`

- Bucket defaults to `observatory-private`.
- `upload_id` is a UUID generated per upload (not the episode ID).

**After upload:** The local temp DuckDB file is deleted. The S3 copy persists indefinitely (no lifecycle policy exists
today -- see Retention Policy in `metrics_design.md`).

## Step 5: PostgreSQL Processing

The `complete_bulk_upload` endpoint downloads the DuckDB from S3, extracts episode data, and inserts it into PostgreSQL.
**This is where most metrics are currently dropped.**

**Key files:**

- `app_backend/src/metta/app_backend/routes/stats_routes.py` -- `complete_bulk_upload()`
- `app_backend/src/metta/app_backend/queries/episode_queries.py` -- `record_episode()`

**What happens:**

1. Download DuckDB from S3 to a local temp file.
2. Open in read-only mode.
3. Read all episodes (typically just one per file).
4. For each episode, read tags, agent policies, and agent metrics from DuckDB.
5. **Filter metrics -- only `reward` passes through:**

   ```python
   for agent_id, metric_name, metric_value in agent_metrics_result:
       if metric_name != "reward":    # <-- Everything except reward is discarded
           continue
       # ...
   ```

6. **Aggregate rewards by policy version** (sum across agents of same policy):

   ```python
   policy_metrics[pv_id]["reward"] += metric_value
   ```

   Per-agent granularity is lost. If 3 agents use policy A with rewards [10, 8, 12], PostgreSQL stores
   `(episode, policy_A, "reward", 30)`. The query layer divides by `num_agents` to recover the average.

7. Insert into PostgreSQL tables:
   - `episodes` -- basic episode info, `data_uri` pointing to S3 DuckDB file
   - `episode_tags` -- key-value metadata (e.g., `job_id`, `season`)
   - `episode_policies` -- which policy versions participated and how many agents each
   - `episode_policy_metrics` -- reward per policy version (aggregated)

**Data at this stage:**

| What's stored                                      | What's dropped                        |
| -------------------------------------------------- | ------------------------------------- |
| `reward` per policy version (summed across agents) | `action_timeout`                      |
| Episode metadata (tags, attributes, replay URL)    | All game stats (e.g., `heart.gained`) |
| Policy version assignments with agent counts       | All agent-level stats                 |
| S3 URI to full DuckDB file (`data_uri`)            | Collective stats                      |

## Step 6: Observatory Queries

The Observatory frontend and API consumers query PostgreSQL for episode and metric data.

**Key files:**

- `app_backend/src/metta/app_backend/queries/episode_queries.py` -- `get_episodes()`
- `app_backend/src/metta/app_backend/routes/stats_routes.py` -- `POST /stats/episodes/query`

**Query structure:**

The `get_episodes()` function builds a SQLAlchemy query with two CTEs:

1. **Tags CTE:** Aggregates `episode_tags` into a JSONB object per episode.
2. **Avg Rewards CTE:** Joins `episode_policy_metrics` (filtered to `metric_name = 'reward'`) with `episode_policies` to
   compute `reward / num_agents` per policy version per episode.

**Response model:**

```python
class EpisodeWithTags(BaseModel):
    id: UUID
    primary_pv_id: UUID | None
    replay_url: str | None
    thumbnail_url: str | None
    attributes: dict[str, Any]
    eval_task_id: UUID | None
    created_at: Any
    tags: dict[str, str]
    avg_rewards: dict[UUID, float]    # policy_version_id → average reward
```

**Filtering options:**

- `primary_policy_version_ids` -- episodes involving specific policies
- `episode_ids` -- specific episodes by ID
- `tag_filters` -- match on episode tag key-value pairs (uses EXISTS subqueries)
- `limit` / `offset` -- pagination

## Step 7: Tournament Scoring Path

Tournament matches use the same episode recording path, then read metrics back from PostgreSQL for scoring.

**Key files:**

- `app_backend/src/metta/app_backend/tournament/commissioners/base.py` -- `_sync_match_scores()`
- `packages/cogames/src/metta_alo/scoring.py` -- `WeightedScorer`, `compute_average_scores_per_agent()`
- `app_backend/src/metta/app_backend/tournament/referees/base.py` -- `get_leaderboard()`

**Flow:**

1. **Commissioner dispatches match** as a `SingleEpisodeJob` → K8s pod.
2. **Episode completes** → same recording path as steps 1-5 above.
3. **Score sync** (`_sync_match_scores()`):
   - Queries completed matches where `MatchPlayer.score IS NULL`.
   - Joins Match → Job → Episode → EpisodePolicy → EpisodePolicyMetric.
   - Reads `reward` values per policy version.
   - Normalizes: `score = total_reward / agent_count` via `compute_average_scores_per_agent()`.
   - Stores result in `MatchPlayer.score`.

4. **Leaderboard computation** (`get_leaderboard()` → `WeightedScorer.compute_scores()`):
   - Reads all completed, scored matches in a pool.
   - For each match, computes participation weight: `weight = agent_count / total_agents`.
   - Final score = weighted average of match scores across all matches.
   - Returns sorted list of `(policy_version_id, score, match_count)`.
   - **Computed on-the-fly per request** -- not cached or materialized.

**Season structure:**

```
Season (e.g., "beta-cogsguard")
├── Qualifying Pool (SelfPlayReferee)
│   ├── New submissions land here
│   ├── Self-play matches (all agents = same policy)
│   └── Promotion: avg_score ≥ threshold → Competition Pool
│
└── Competition Pool (PairingReferee) ← leaderboard pool
    ├── Head-to-head matches (1v9, 9v1, 5v5, etc.)
    ├── All unique pairs of active players
    └── Leaderboard computed from weighted match scores
```

## Step 8: W&B Path (Separate System)

Training-loop metrics go to W&B, not to the Observatory. These are different metrics collected at different times.

**Key files:**

- `metta/rl/training/stats_reporter.py` -- `StatsReporter.report_epoch()`
- `metta/rl/wandb.py` -- W&B run initialization

**What's logged to W&B:**

- `metric/agent_step` -- training step counter
- `metric/epoch` -- training epoch
- `overview/reward` -- mean reward from the experience buffer
- `losses/*` -- policy loss, value loss, entropy loss
- `hyperparameters/*` -- learning rates, batch sizes
- `experience/rewards` -- per-agent rewards from rollout buffer
- `metric/total_time`, `metric/train_time` -- wall clock timing

**Key differences from Observatory:**

|                 | W&B                                      | Observatory                               |
| --------------- | ---------------------------------------- | ----------------------------------------- |
| **When**        | Every training epoch                     | Per evaluation/tournament episode         |
| **What**        | Training signals (losses, gradients, LR) | Game outcomes (rewards, agent stats)      |
| **Granularity** | Aggregate over rollout buffer            | Individual episodes with per-agent detail |
| **Trigger**     | `StatsReporter.report_epoch()`           | `record_job_episode()` via K8s watcher    |
| **Storage**     | W&B cloud                                | S3 DuckDB + PostgreSQL                    |
| **Access**      | W&B dashboard                            | Observatory API                           |

These paths do not share data. Training metrics are not available in the Observatory, and episode stats are not logged
to W&B.

## What Changes for the Metrics Project

The metrics project (see `metrics_design.md`) requires one key upstream change to this data flow:

**Remove the `reward`-only filter in `complete_bulk_upload()`.**

Currently in `stats_routes.py`:

```python
if metric_name != "reward":
    continue
```

After the change, all metrics from the DuckDB file flow through to `episode_policy_metrics` in PostgreSQL. The schema
already supports this -- `metric_name` is a free-form `TEXT` column. No migration is needed for the table itself (only
new indexes for efficient querying).

**Before and after:**

```
BEFORE:  DuckDB (all stats) → PostgreSQL (reward only)
AFTER:   DuckDB (all stats) → PostgreSQL (all stats)
```

Historical data can be backfilled from S3 DuckDB files since they contain the full metric set. See the Backfill Strategy
section in `metrics_design.md`.
