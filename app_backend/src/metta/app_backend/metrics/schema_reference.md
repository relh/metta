# Schema Reference

> **Status:** Draft **Created:** 2026-01-31 **Related:** `data_flow.md`, `metrics_design.md`

This document describes both database schemas used in the episode metrics pipeline: the DuckDB staging format
(ephemeral, one file per episode on S3) and the PostgreSQL Observatory database (persistent, queryable).

---

## Part 1: DuckDB Staging Schema

Defined in `app_backend/src/metta/app_backend/episode_stats_db.py`. Each episode produces one DuckDB file containing 4
tables. The file is created locally during recording, uploaded to S3 at `episodes/{upload_id}.duckdb`, then processed
into PostgreSQL. The S3 copy persists indefinitely.

### `episodes`

One row per file (always exactly one episode per DuckDB file).

| Column          | Type    | Constraints | Description                                                               |
| --------------- | ------- | ----------- | ------------------------------------------------------------------------- |
| `id`            | VARCHAR | PRIMARY KEY | Episode UUID (generated in `episode_recording.py`)                        |
| `replay_url`    | VARCHAR |             | HTTP URL to the episode replay file on S3, or NULL if replay not recorded |
| `thumbnail_url` | VARCHAR |             | Always NULL today — reserved for future episode thumbnail images          |
| `attributes`    | JSON    |             | Always `{}` today — episode attributes are not populated in DuckDB        |
| `eval_task_id`  | VARCHAR |             | Always NULL today — reserved for linking to legacy eval task system       |

### `episode_tags`

Key-value metadata attached to the episode. Used for filtering and grouping.

| Column       | Type    | Constraints    | Description                      |
| ------------ | ------- | -------------- | -------------------------------- |
| `episode_id` | VARCHAR | PK (composite) | FK to `episodes.id`              |
| `key`        | VARCHAR | PK (composite) | Tag key (see Valid Values below) |
| `value`      | VARCHAR | NOT NULL       | Tag value                        |

### `episode_agent_policies`

Maps each agent slot in the episode to the policy version it ran. One row per agent.

| Column              | Type    | Constraints | Description                                           |
| ------------------- | ------- | ----------- | ----------------------------------------------------- |
| `episode_id`        | VARCHAR | NOT NULL    | FK to `episodes.id`                                   |
| `policy_version_id` | VARCHAR | NOT NULL    | UUID of the policy version this agent used            |
| `agent_id`          | INTEGER | NOT NULL    | Zero-indexed agent slot in the episode (0, 1, 2, ...) |

No primary key constraint in DuckDB. Agent IDs are unique per episode in practice but not enforced.

### `episode_agent_metrics`

Per-agent metric values. This is the primary data table — one row per agent per metric. Contains ALL metrics from the
simulator, including those that are currently filtered out during PostgreSQL processing.

| Column       | Type    | Constraints | Description                                                                 |
| ------------ | ------- | ----------- | --------------------------------------------------------------------------- |
| `episode_id` | VARCHAR | NOT NULL    | FK to `episodes.id`                                                         |
| `agent_id`   | INTEGER | NOT NULL    | Zero-indexed agent slot matching `episode_agent_policies.agent_id`          |
| `metric`     | VARCHAR | NOT NULL    | Metric name string (see Valid Values below)                                 |
| `value`      | REAL    |             | Metric value as a float. NULL is allowed by schema but not used in practice |

**Row count per episode:** For an 8-agent episode with ~50 stats each, plus `reward` and `action_timeout` per agent,
expect ~416 rows. Typical file size: 5-20KB.

---

## Part 2: PostgreSQL Schema (Observatory)

Defined across `migrations.py` (v0-v10) and SQLModel classes in `app_backend/src/metta/app_backend/models/`. 20 tables,
1 view, 3 enum types.

### Enum Types

```sql
CREATE TYPE job_status AS ENUM ('pending', 'dispatched', 'running', 'completed', 'failed');
CREATE TYPE match_status AS ENUM ('pending', 'scheduled', 'running', 'completed', 'failed');
CREATE TYPE membership_action AS ENUM ('add', 'remove');
```

---

### 2.1 Core: Policies & Episodes

#### `policies`

A named policy owned by a user. Multiple versions can exist under one policy.

| Column       | Type      | Constraints                      | Description                                                           |
| ------------ | --------- | -------------------------------- | --------------------------------------------------------------------- |
| `id`         | UUID      | PK, DEFAULT `uuid_generate_v4()` | Unique policy identifier                                              |
| `name`       | TEXT      | NOT NULL, UNIQUE                 | Human-readable policy name (unique across all users)                  |
| `user_id`    | TEXT      | NOT NULL                         | Owner's user ID (from auth system), or `"system"` for system policies |
| `attributes` | JSONB     |                                  | Arbitrary policy metadata. No defined schema                          |
| `created_at` | TIMESTAMP | NOT NULL, DEFAULT `now()`        | When the policy was first created                                     |

#### `policy_versions`

A specific checkpoint/snapshot of a policy. Immutable once created.

| Column        | Type      | Constraints                          | Description                                                                                    |
| ------------- | --------- | ------------------------------------ | ---------------------------------------------------------------------------------------------- |
| `id`          | UUID      | PK, DEFAULT `uuid_generate_v4()`     | Unique version identifier (used in APIs)                                                       |
| `internal_id` | SERIAL    | UNIQUE                               | Auto-incrementing integer ID (used in metric FKs for performance)                              |
| `policy_id`   | UUID      | NOT NULL, FK → `policies.id` CASCADE | Parent policy                                                                                  |
| `version`     | INTEGER   | NOT NULL, UNIQUE with `policy_id`    | Sequential version number (1, 2, 3, ...)                                                       |
| `s3_path`     | TEXT      |                                      | S3 URI to the policy checkpoint zip (e.g., `s3://observatory-private/cogames/submissions/...`) |
| `git_hash`    | TEXT      |                                      | Git commit hash if the policy is version-controlled                                            |
| `policy_spec` | JSONB     |                                      | Serialized policy configuration/architecture definition                                        |
| `attributes`  | JSONB     |                                      | Arbitrary version metadata                                                                     |
| `created_at`  | TIMESTAMP | NOT NULL, DEFAULT `now()`            | When this version was created                                                                  |

**Indexes:** `(policy_id)`, unique on `(policy_id, version)`, unique on `(internal_id)`.

#### `policy_version_tags`

Key-value tags on policy versions. Used for filtering in queries.

| Column              | Type | Constraints                                       | Description |
| ------------------- | ---- | ------------------------------------------------- | ----------- |
| `policy_version_id` | UUID | PK (composite), FK → `policy_versions.id` CASCADE |             |
| `key`               | TEXT | PK (composite), NOT NULL                          | Tag key     |
| `value`             | TEXT | NOT NULL                                          | Tag value   |

**Indexes:** `idx_policy_version_tags_key_value (key, value)`.

#### `episodes`

A single episode (game) that was played and recorded.

| Column          | Type      | Constraints                      | Description                                                                                                           |
| --------------- | --------- | -------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| `id`            | UUID      | PK, DEFAULT `uuid_generate_v4()` | Unique episode identifier                                                                                             |
| `internal_id`   | SERIAL    | UNIQUE                           | Auto-incrementing integer ID (used in metric FKs for performance)                                                     |
| `data_uri`      | TEXT      |                                  | S3 URI to the DuckDB file containing full episode data (e.g., `s3://observatory-private/episodes/{upload_id}.duckdb`) |
| `replay_url`    | TEXT      |                                  | HTTP URL to the episode replay file                                                                                   |
| `thumbnail_url` | TEXT      |                                  | Episode thumbnail image URL (unused today)                                                                            |
| `attributes`    | JSONB     |                                  | Episode metadata (see Valid Values below)                                                                             |
| `eval_task_id`  | UUID      |                                  | Link to legacy eval task system (unused in current flow)                                                              |
| `created_at`    | TIMESTAMP | NOT NULL, DEFAULT `now()`        | When the episode record was created in PostgreSQL                                                                     |

#### `episode_tags`

Key-value metadata on episodes. Primary mechanism for filtering episodes in queries.

| Column       | Type | Constraints                                | Description                      |
| ------------ | ---- | ------------------------------------------ | -------------------------------- |
| `episode_id` | UUID | PK (composite), FK → `episodes.id` CASCADE |                                  |
| `key`        | TEXT | PK (composite), NOT NULL                   | Tag key (see Valid Values below) |
| `value`      | TEXT | NOT NULL                                   | Tag value                        |

**Indexes:** `idx_episode_tags_key_value (key, value)`, `idx_episode_tags_episode_key_value (episode_id, key, value)`.

#### `episode_policies`

Which policy versions participated in an episode and how many agents each controlled.

| Column              | Type    | Constraints                                       | Description                                                         |
| ------------------- | ------- | ------------------------------------------------- | ------------------------------------------------------------------- |
| `episode_id`        | UUID    | PK (composite), FK → `episodes.id` CASCADE        |                                                                     |
| `policy_version_id` | UUID    | PK (composite), FK → `policy_versions.id` CASCADE |                                                                     |
| `num_agents`        | INTEGER | NOT NULL                                          | How many agent slots this policy version controlled in this episode |

#### `episode_policy_metrics`

Metric values per episode per policy version. Currently stores only `reward` (see data_flow.md for why). After the
metrics project removes the filter, this table will store all agent stats.

| Column                | Type    | Constraints                                                | Description                                                                                                                                                       |
| --------------------- | ------- | ---------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `episode_internal_id` | INTEGER | PK (composite), FK → `episodes.internal_id` CASCADE        | Uses integer ID for join performance                                                                                                                              |
| `pv_internal_id`      | INTEGER | PK (composite), FK → `policy_versions.internal_id` CASCADE | Uses integer ID for join performance                                                                                                                              |
| `metric_name`         | TEXT    | PK (composite), NOT NULL                                   | Free-form metric name string (see Valid Values below)                                                                                                             |
| `value`               | FLOAT   | NOT NULL                                                   | Metric value. For `reward`, this is the **sum** across all agents of this policy in this episode (divided by `num_agents` at query time to get per-agent average) |

**Important:** This table aggregates per-agent values to per-policy-version values. If 3 agents use policy A with
rewards [10, 8, 12], the stored value is 30. The query layer divides by `episode_policies.num_agents` to recover the
per-agent average.

---

### 2.2 Jobs

#### `job_requests`

Job queue for episode execution on K8s. Each tournament match or evaluation creates a job request.

| Column          | Type         | Constraints                      | Description                                               |
| --------------- | ------------ | -------------------------------- | --------------------------------------------------------- |
| `id`            | UUID         | PK, DEFAULT `uuid_generate_v4()` | Unique job identifier                                     |
| `job_type`      | TEXT         | NOT NULL                         | Job type string (e.g., `"single_episode"`)                |
| `job`           | JSONB        | NOT NULL                         | Serialized job specification (`SingleEpisodeJob` as JSON) |
| `user_id`       | TEXT         | NOT NULL                         | User who created the job                                  |
| `status`        | `job_status` | NOT NULL, DEFAULT `'pending'`    | Current job state                                         |
| `created_at`    | TIMESTAMP    | NOT NULL, DEFAULT `now()`        | When the job was created                                  |
| `dispatched_at` | TIMESTAMP    |                                  | When the job was dispatched to K8s                        |
| `running_at`    | TIMESTAMP    |                                  | When the K8s pod started running                          |
| `completed_at`  | TIMESTAMP    |                                  | When the job finished (success or failure)                |
| `worker`        | TEXT         |                                  | K8s pod name that executed the job                        |
| `result`        | JSONB        |                                  | Job result. For episode jobs: `{"episode_id": "<UUID>"}`  |
| `error`         | TEXT         |                                  | Error message if job failed                               |
| `error_type`    | TEXT         |                                  | Structured error classification (see Valid Values below)  |

**Indexes:** `(job_type, status, created_at DESC)`, `(job_type, created_at DESC)`, `(created_at DESC)`, `(status)`,
`(user_id)`.

#### `job_policy_versions`

Junction table linking jobs to the policy versions they use. Enables querying "all jobs involving policy X."

| Column              | Type    | Constraints                                    | Description                                            |
| ------------------- | ------- | ---------------------------------------------- | ------------------------------------------------------ |
| `job_id`            | UUID    | PK (composite), FK → `job_requests.id` CASCADE |                                                        |
| `policy_version_id` | UUID    | FK → `policy_versions.id` CASCADE              |                                                        |
| `position`          | INTEGER | PK (composite), NOT NULL                       | Index into the job's `policy_uris` list (0, 1, 2, ...) |

**Indexes:** `idx_job_policy_versions_policy_version_id (policy_version_id)`.

---

### 2.3 Tournament

#### `seasons`

A competitive season grouping pools and defining the tournament structure.

| Column        | Type      | Constraints                      | Description                                                          |
| ------------- | --------- | -------------------------------- | -------------------------------------------------------------------- |
| `id`          | UUID      | PK, DEFAULT `uuid_generate_v4()` |                                                                      |
| `name`        | TEXT      | NOT NULL, UNIQUE                 | Season identifier (e.g., `"beta"`, `"beta-cogsguard"`, `"beta-cvc"`) |
| `description` | TEXT      |                                  | Human-readable season description                                    |
| `created_at`  | TIMESTAMP | NOT NULL, DEFAULT `now()`        |                                                                      |

**Indexes:** `idx_seasons_name (name)`.

#### `pools`

A pool of policy versions within a season. Each season typically has a qualifying pool and a competition pool.

| Column          | Type      | Constraints                      | Description                                             |
| --------------- | --------- | -------------------------------- | ------------------------------------------------------- |
| `id`            | UUID      | PK, DEFAULT `uuid_generate_v4()` |                                                         |
| `season_id`     | UUID      | FK → `seasons.id` CASCADE        | Parent season                                           |
| `env_config_id` | UUID      | FK → `mettagrid_env_configs.id`  | Environment configuration used for matches in this pool |
| `name`          | TEXT      |                                  | Pool name (e.g., `"qualifying"`, `"competition"`)       |
| `created_at`    | TIMESTAMP | NOT NULL, DEFAULT `now()`        |                                                         |

**Indexes:** `idx_pools_season_id (season_id)`.

#### `pool_players`

Policy versions enrolled in a pool. A policy version can be in multiple pools (qualifying + competition).

| Column              | Type      | Constraints                                 | Description                                                  |
| ------------------- | --------- | ------------------------------------------- | ------------------------------------------------------------ |
| `id`                | UUID      | PK, DEFAULT `uuid_generate_v4()`            |                                                              |
| `pool_id`           | UUID      | NOT NULL, FK → `pools.id` CASCADE           |                                                              |
| `policy_version_id` | UUID      | NOT NULL, FK → `policy_versions.id` CASCADE |                                                              |
| `retired`           | BOOLEAN   | NOT NULL, DEFAULT `FALSE`                   | Whether this player has been removed from active matchmaking |
| `created_at`        | TIMESTAMP | NOT NULL, DEFAULT `now()`                   | When the player was added to the pool                        |

**Constraints:** UNIQUE on `(pool_id, policy_version_id)`. **Indexes:** `idx_pool_players_pool_id`,
`idx_pool_players_policy_version_id`.

#### `matches`

A tournament match between policy versions in a pool. Each match maps to one episode via a job.

| Column         | Type           | Constraints                       | Description                                                                                                        |
| -------------- | -------------- | --------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| `id`           | UUID           | PK, DEFAULT `uuid_generate_v4()`  |                                                                                                                    |
| `pool_id`      | UUID           | NOT NULL, FK → `pools.id` CASCADE | Pool this match belongs to                                                                                         |
| `job_id`       | UUID           | FK → `job_requests.id` SET NULL   | Job that executes the episode. SET NULL (not CASCADE) so match history survives job cleanup                        |
| `assignments`  | INTEGER[]      | NOT NULL                          | Array mapping agent slots to policy indices. E.g., `[0, 1, 1, 1]` = agent 0 uses policy 0, agents 1-3 use policy 1 |
| `status`       | `match_status` | NOT NULL, DEFAULT `'pending'`     | Current match state                                                                                                |
| `created_at`   | TIMESTAMP      | NOT NULL, DEFAULT `now()`         |                                                                                                                    |
| `completed_at` | TIMESTAMP      |                                   | When the match finished                                                                                            |

**Indexes:** `idx_matches_pool_id`, `idx_matches_job_id`, `idx_matches_status`.

#### `match_players`

Links match participants (pool players) to their match and stores their score.

| Column           | Type    | Constraints                              | Description                                                                                                                                |
| ---------------- | ------- | ---------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| `id`             | UUID    | PK, DEFAULT `uuid_generate_v4()`         |                                                                                                                                            |
| `match_id`       | UUID    | NOT NULL, FK → `matches.id` CASCADE      |                                                                                                                                            |
| `pool_player_id` | UUID    | NOT NULL, FK → `pool_players.id` CASCADE |                                                                                                                                            |
| `policy_index`   | INTEGER | NOT NULL, DEFAULT 0                      | Index into the match's policy list (corresponds to `assignments` values)                                                                   |
| `score`          | FLOAT   |                                          | Per-agent normalized reward. NULL until match completes and scores sync. Computed as: `sum(reward for agents of this policy) / num_agents` |

**Indexes:** `idx_match_players_match_id`, `idx_match_players_pool_player_id`.

#### `membership_changes`

Audit trail of pool membership additions and removals (promotions, retirements).

| Column           | Type                | Constraints                              | Description                                                        |
| ---------------- | ------------------- | ---------------------------------------- | ------------------------------------------------------------------ |
| `id`             | UUID                | PK, DEFAULT `uuid_generate_v4()`         |                                                                    |
| `pool_player_id` | UUID                | NOT NULL, FK → `pool_players.id` CASCADE |                                                                    |
| `action`         | `membership_action` | NOT NULL                                 | `'add'` or `'remove'`                                              |
| `notes`          | TEXT                |                                          | Human-readable reason (e.g., `"promoted: avg_score 0.15 >= 0.10"`) |
| `created_at`     | TIMESTAMP           | NOT NULL, DEFAULT `now()`                |                                                                    |

**Indexes:** `idx_membership_changes_pool_player_id`, `idx_membership_changes_created_at (created_at DESC)`.

#### `mettagrid_env_configs`

Deduplicated environment configurations used by pools. Content-addressed by hash.

| Column        | Type      | Constraints                      | Description                                                                  |
| ------------- | --------- | -------------------------------- | ---------------------------------------------------------------------------- |
| `id`          | UUID      | PK, DEFAULT `uuid_generate_v4()` |                                                                              |
| `config_hash` | TEXT      | NOT NULL, UNIQUE                 | Hash of the config JSONB for deduplication                                   |
| `config`      | JSONB     | NOT NULL                         | Full mettagrid environment configuration (grid size, game type, rules, etc.) |
| `created_at`  | TIMESTAMP | NOT NULL, DEFAULT `now()`        |                                                                              |

---

### 2.4 Eval Tasks (Legacy)

These tables predate the job_requests system and are used for older-style evaluation tasks.

#### `eval_tasks`

| Column              | Type      | Constraints                     | Description                    |
| ------------------- | --------- | ------------------------------- | ------------------------------ |
| `id`                | SERIAL    | PK, UNIQUE                      | Auto-incrementing task ID      |
| `command`           | TEXT      | NOT NULL                        | Shell command to execute       |
| `data_uri`          | TEXT      |                                 | URI to input data              |
| `git_hash`          | TEXT      |                                 | Git hash for reproducibility   |
| `attributes`        | JSONB     |                                 | Task metadata                  |
| `user_id`           | TEXT      | NOT NULL                        | Task creator                   |
| `is_finished`       | BOOLEAN   | NOT NULL, DEFAULT `FALSE`       | Whether the task has completed |
| `latest_attempt_id` | INTEGER   | FK → `task_attempts.id` CASCADE | Most recent attempt            |
| `created_at`        | TIMESTAMP | NOT NULL, DEFAULT `now()`       |                                |

#### `task_attempts`

| Column            | Type      | Constraints                            | Description                            |
| ----------------- | --------- | -------------------------------------- | -------------------------------------- |
| `id`              | SERIAL    | PK, UNIQUE                             | Auto-incrementing attempt ID           |
| `task_id`         | INTEGER   | NOT NULL, FK → `eval_tasks.id` CASCADE | Parent task                            |
| `attempt_number`  | INTEGER   | NOT NULL, DEFAULT 0                    | Retry count (0-indexed)                |
| `status`          | TEXT      | NOT NULL, DEFAULT `'unprocessed'`      | Attempt state (see Valid Values below) |
| `status_details`  | JSONB     |                                        | Error details, diagnostic data         |
| `assignee`        | TEXT      |                                        | Worker that claimed this attempt       |
| `assigned_at`     | TIMESTAMP |                                        | When the attempt was assigned          |
| `started_at`      | TIMESTAMP |                                        | When execution began                   |
| `finished_at`     | TIMESTAMP |                                        | When execution ended                   |
| `output_log_path` | TEXT      |                                        | Path to output logs                    |

#### `eval_tasks_view`

View joining `eval_tasks` with their latest `task_attempts` for convenient querying.

```sql
SELECT t.id, t.command, t.data_uri, t.git_hash, t.attributes,
       t.user_id, t.created_at, t.is_finished, t.latest_attempt_id,
       a.attempt_number, a.status, a.status_details, a.assigned_at,
       a.assignee, a.started_at, a.finished_at, a.output_log_path
FROM eval_tasks t
LEFT JOIN task_attempts a ON t.latest_attempt_id = a.id
```

---

### 2.5 Infrastructure

#### `k8s_events`

Raw Kubernetes watch events for monitoring and debugging.

| Column       | Type        | Constraints               | Description                           |
| ------------ | ----------- | ------------------------- | ------------------------------------- |
| `id`         | BIGSERIAL   | PK                        | Auto-incrementing event ID            |
| `cluster`    | TEXT        | NOT NULL                  | K8s cluster name                      |
| `created_at` | TIMESTAMPTZ | NOT NULL, DEFAULT `now()` | When the event was recorded in the DB |
| `event_time` | TIMESTAMPTZ | NOT NULL                  | When the event occurred in K8s        |
| `event`      | JSONB       | NOT NULL                  | Full Kubernetes event object          |

**Indexes:** `idx_k8s_events_cluster_event_time (cluster, event_time DESC)`.

#### `sweeps`

W&B hyperparameter sweep tracking.

| Column           | Type      | Constraints                      | Description                  |
| ---------------- | --------- | -------------------------------- | ---------------------------- |
| `id`             | UUID      | PK, DEFAULT `uuid_generate_v4()` |                              |
| `name`           | TEXT      | NOT NULL, UNIQUE                 | Sweep name                   |
| `project`        | TEXT      | NOT NULL                         | W&B project name             |
| `entity`         | TEXT      | NOT NULL                         | W&B entity/organization      |
| `wandb_sweep_id` | TEXT      | NOT NULL                         | W&B sweep identifier         |
| `state`          | TEXT      | NOT NULL, DEFAULT `'running'`    | Sweep state                  |
| `run_counter`    | INTEGER   | NOT NULL, DEFAULT 0              | Number of runs in this sweep |
| `user_id`        | TEXT      | NOT NULL                         | Sweep creator                |
| `created_at`     | TIMESTAMP | NOT NULL, DEFAULT `now()`        |                              |
| `updated_at`     | TIMESTAMP | NOT NULL, DEFAULT `now()`        |                              |

**Indexes:** `idx_sweeps_name (name)`.

---

## Part 3: Valid Values Reference

### Metric Names

Values for DuckDB `episode_agent_metrics.metric` and PostgreSQL `episode_policy_metrics.metric_name`.

The C++ simulator can emit arbitrary stat names depending on the mission configuration. The following are the known
metric names as of this writing. New game types will add new names without requiring schema changes.

**Hardcoded in `episode_recording.py`** (always present):

| Metric           | Description                                                                   |
| ---------------- | ----------------------------------------------------------------------------- |
| `reward`         | Agent's per-episode reward. The only metric currently persisted to PostgreSQL |
| `action_timeout` | Number of times the agent's action generation exceeded the time limit         |

**CogsGuard Agent Stats** (from `cogsguard_reward_variants.py`, emitted by C++ simulator):

| Metric                           | Description                                                        |
| -------------------------------- | ------------------------------------------------------------------ |
| `heart.gained`                   | Heart resources collected by the agent                             |
| `carbon.gained`                  | Carbon element collected                                           |
| `oxygen.gained`                  | Oxygen element collected                                           |
| `germanium.gained`               | Germanium element collected                                        |
| `silicon.gained`                 | Silicon element collected                                          |
| `aligner.gained`                 | Aligner gear acquired (used to align junctions)                    |
| `scrambler.gained`               | Scrambler gear acquired (used to scramble opponent junctions)      |
| `junction.aligned_by_agent`      | Number of junctions this agent aligned to its collective           |
| `junction.scrambled_by_agent`    | Number of junctions this agent scrambled (converted from opponent) |
| `aligned_junction_held`          | Number of junctions currently held by this agent's collective      |
| `chest.heart.deposited_by_agent` | Hearts deposited into the collective chest by this agent           |
| `chest.heart.amount`             | Current heart inventory held by the agent                          |

**CogsGuard Collective Stats** (from reward variants, may appear as agent-level aggregates):

| Metric                             | Description                                        |
| ---------------------------------- | -------------------------------------------------- |
| `collective.carbon.deposited`      | Total carbon deposited to collective               |
| `collective.oxygen.deposited`      | Total oxygen deposited to collective               |
| `collective.germanium.deposited`   | Total germanium deposited to collective            |
| `collective.silicon.deposited`     | Total silicon deposited to collective              |
| `collective.aligned.junction.held` | Junctions currently aligned to the cogs collective |

**Game-Level Stats** (from `stats["game"]`, may appear in DuckDB but not in per-agent metrics):

| Metric                  | Description                                          |
| ----------------------- | ---------------------------------------------------- |
| `chest.heart.deposited` | Total hearts deposited across all agents (game-wide) |

**Note:** This list is not exhaustive. The C++ simulator emits stats based on mission configuration. Different game
types (Machina, CvC, future games) will have different stat names. The metric name is a free-form string in both DuckDB
and PostgreSQL — no schema change is needed to add new names.

### Episode Tag Keys

Values for `episode_tags.key` (both DuckDB and PostgreSQL).

| Key        | Source                                   | Description                                       |
| ---------- | ---------------------------------------- | ------------------------------------------------- |
| `job_id`   | `episode_recording.py` (always present)  | UUID of the job_request that created this episode |
| `category` | `handle_results.py` / eval context       | Evaluation category (e.g., mission name)          |
| `name`     | `handle_results.py` / eval context       | Simulation/evaluation name                        |
| _(custom)_ | `job.episode_tags` in `SingleEpisodeJob` | Arbitrary tags set by the job creator             |

### Episode Attributes (JSONB)

Values for `episodes.attributes` in PostgreSQL. Populated from `StatsTracker` in `stats_tracker.py`.

| Key                        | Type   | Description                                                                                     |
| -------------------------- | ------ | ----------------------------------------------------------------------------------------------- |
| `seed`                     | int    | Random seed used for the episode                                                                |
| `map_w`                    | int    | Map width in cells                                                                              |
| `map_h`                    | int    | Map height in cells                                                                             |
| `steps`                    | int    | Number of timesteps executed                                                                    |
| `max_steps`                | int    | Maximum steps configured for the episode                                                        |
| `completion_time`          | float  | Unix timestamp when the episode completed                                                       |
| `config.*`                 | varies | Flattened environment config. All config keys prefixed with `config.`, with `/` replaced by `.` |
| `per_label_rewards`        | dict   | Map of config labels to mean rewards (multi-episode tracking)                                   |
| `per_label_chest_deposits` | dict   | Map of config labels to chest deposit amounts                                                   |
| `reward_estimates`         | dict   | Contains `best_case_optimal_diff` and `worst_case_optimal_diff` if configured                   |
| `timing_per_epoch`         | dict   | Per-timestep timing: `active_frac/{op}`, `msec/{op}`, `frac/thread_idle`                        |
| `timing_cumulative`        | dict   | Cumulative timing: `active_frac/{op}`, `frac/thread_idle`                                       |

### Job Status Lifecycle

`job_requests.status` (`job_status` enum):

```
pending → dispatched → running → completed
                              → failed
```

### Job Error Types

`job_requests.error_type` (TEXT, not an enum):

| Value          | Description                         |
| -------------- | ----------------------------------- |
| `timeout`      | Job exceeded time limit             |
| `oom`          | Out of memory (OOMKilled)           |
| `policy_error` | Error loading or running the policy |
| `unknown`      | Unclassified error                  |

### Match Status Lifecycle

`matches.status` (`match_status` enum):

```
pending → scheduled → running → completed
                             → failed
```

### Membership Actions

`membership_changes.action` (`membership_action` enum):

| Value    | Description                                                |
| -------- | ---------------------------------------------------------- |
| `add`    | Policy version added to pool (new submission or promotion) |
| `remove` | Policy version removed from pool (retirement or demotion)  |

### Task Attempt Status

`task_attempts.status` (TEXT, not an enum):

| Value          | Description                 |
| -------------- | --------------------------- |
| `unprocessed`  | Not yet claimed by a worker |
| `running`      | Currently executing         |
| `done`         | Completed successfully      |
| `error`        | Failed with an error        |
| `canceled`     | Manually canceled           |
| `system_error` | Infrastructure failure      |

---

## Part 4: Key Relationships

### Metrics-Relevant Path

The primary FK chain for querying metrics:

```
policies
  │
  │ policies.id ← policy_versions.policy_id
  ▼
policy_versions
  │
  │ policy_versions.id ← episode_policies.policy_version_id
  │ policy_versions.internal_id ← episode_policy_metrics.pv_internal_id
  ▼
episode_policies ◄──── episodes
  │                       │
  │                       │ episodes.internal_id ← episode_policy_metrics.episode_internal_id
  │                       │ episodes.id ← episode_tags.episode_id
  ▼                       ▼
episode_policy_metrics  episode_tags
```

### Tournament Path

```
seasons
  │
  │ seasons.id ← pools.season_id
  ▼
pools
  │
  ├──► pool_players ──► match_players ──► matches ──► job_requests ──► episodes
  │
  └──► mettagrid_env_configs
```

### Dual ID Pattern

`episodes` and `policy_versions` both have two identifiers:

|               | UUID (`id`)                   | Integer (`internal_id`)                                 |
| ------------- | ----------------------------- | ------------------------------------------------------- |
| **Used by**   | API layer, FKs in most tables | `episode_policy_metrics` FKs only                       |
| **Why**       | Standard external identifier  | Integer joins are faster for high-volume metric queries |
| **Generated** | Application-side (`uuid4()`)  | Database-side (`SERIAL`)                                |

---

## Part 5: DuckDB → PostgreSQL Mapping

How data transforms during `complete_bulk_upload()` in `stats_routes.py`:

### Direct Mappings

| DuckDB Table.Column       | PostgreSQL Table.Column   | Transformation                                     |
| ------------------------- | ------------------------- | -------------------------------------------------- |
| `episodes.id`             | `episodes.id`             | VARCHAR → UUID cast                                |
| `episodes.replay_url`     | `episodes.replay_url`     | Direct copy                                        |
| `episodes.thumbnail_url`  | `episodes.thumbnail_url`  | Direct copy                                        |
| `episodes.attributes`     | `episodes.attributes`     | Direct copy (JSON → JSONB)                         |
| `episodes.eval_task_id`   | `episodes.eval_task_id`   | VARCHAR → UUID cast                                |
| _(not in DuckDB)_         | `episodes.data_uri`       | Set to `s3://{bucket}/episodes/{upload_id}.duckdb` |
| _(not in DuckDB)_         | `episodes.internal_id`    | Auto-generated by PostgreSQL SERIAL                |
| `episode_tags.episode_id` | `episode_tags.episode_id` | VARCHAR → UUID cast                                |
| `episode_tags.key`        | `episode_tags.key`        | Direct copy                                        |
| `episode_tags.value`      | `episode_tags.value`      | Direct copy                                        |

### Aggregated Mappings

| DuckDB Source                                             | PostgreSQL Target                    | Transformation                                     |
| --------------------------------------------------------- | ------------------------------------ | -------------------------------------------------- |
| `episode_agent_policies` (grouped by `policy_version_id`) | `episode_policies.num_agents`        | `COUNT(agent_id)` per policy version               |
| `episode_agent_metrics` where `metric = 'reward'`         | `episode_policy_metrics.value`       | `SUM(value)` across agents of same policy version  |
| `episode_agent_metrics.metric`                            | `episode_policy_metrics.metric_name` | Renamed column; **only `'reward'` passes through** |

### What's Lost

| DuckDB Data                                             | Why It's Lost                                                                      |
| ------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| `episode_agent_metrics` rows where `metric != 'reward'` | Filtered out by `if metric_name != "reward": continue` in `complete_bulk_upload()` |
| Per-agent granularity (individual `agent_id` values)    | Aggregated to per-policy-version sums                                              |
| `episode_agent_policies.agent_id` mapping               | Only agent count per policy is preserved (`num_agents`)                            |

### After Metrics Project

Removing the `reward`-only filter changes the aggregated mapping:

| DuckDB Source                         | PostgreSQL Target              | Transformation                                                               |
| ------------------------------------- | ------------------------------ | ---------------------------------------------------------------------------- |
| `episode_agent_metrics` (ALL metrics) | `episode_policy_metrics.value` | `SUM(value)` across agents of same policy version, for **every** metric name |

Per-agent granularity is still lost (summed to policy-version level), but all metric names are preserved.
