# Metrics System Design

> **Status:** Draft **Author:** Marty Hess **Created:** 2026-01-31 **Spec:** `docs/specs/0020-metrics.md`

## Overview

This document describes the technical design for the metrics system defined in the metrics spec. It covers storage,
schema evolution, query patterns, testing, and AWS infrastructure choices.

The core challenge: we need to store an evolving set of per-episode, per-agent numeric metrics that will grow over time
as we add new game types and capability breakdowns, without requiring schema migrations or degrading query performance
as the metric vocabulary expands.

## Current State

Today's data flow:

```
mettagrid episode
  → PureSingleEpisodeResult (all agent stats in memory)
    → episode_recording.py writes ALL stats to DuckDB staging file
      → DuckDB uploaded to S3
        → complete_bulk_upload reads DuckDB, inserts into PostgreSQL
          → BUT: only "reward" metric is persisted (others filtered out)
```

Key existing components:

- **`EpisodePolicyMetric`** table: `(episode_internal_id, pv_internal_id, metric_name, value)` with composite PK.
  `metric_name` is already a free-form `TEXT` -- no schema change needed to add new metric types.
- **DuckDB staging**: `episode_agent_metrics` table stores `(episode_id, agent_id, metric, value)` for ALL agent stats
  during recording. The data exists; it's just discarded during the PostgreSQL insert.
- **PostgreSQL**: Async via SQLAlchemy + psycopg, pool_size=5, max_overflow=10. Custom migration system (not Alembic).

## Storage Design

### Recommended Database: PostgreSQL (keep current)

After evaluating alternatives, PostgreSQL remains the best choice for this workload. Here's the analysis:

| Database                             | Strengths                                                                                       | Why not primary                                                                                              |
| ------------------------------------ | ----------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| **PostgreSQL**                       | Already deployed, JSONB support, mature async drivers, transactional consistency, rich indexing | Row-per-metric model can be verbose at high cardinality                                                      |
| **Amazon Timestream**                | Purpose-built for time-series, automatic tiering                                                | Expensive at scale, poor ad-hoc query support, vendor lock-in, no transactional guarantees with episode data |
| **Amazon DynamoDB**                  | Schema-free, auto-scaling, single-digit ms latency                                              | Poor for aggregation queries (scan-heavy), no JOINs to episode/policy tables, expensive for analytics        |
| **ClickHouse / DuckDB (analytical)** | Columnar compression, fast aggregations                                                         | Operational complexity of a second database; DuckDB is already used for staging but is single-process        |
| **Amazon RDS PostgreSQL**            | Managed PostgreSQL with same feature set                                                        | This is what we'd use -- "keep PostgreSQL" means RDS PostgreSQL                                              |

**Why PostgreSQL wins:**

1. **Metrics are relational.** Every metric query joins to episodes, policy versions, policies, and users. These
   relationships already exist in PostgreSQL. A separate time-series DB would need to duplicate or cross-query this
   data.

2. **The EAV (Entity-Attribute-Value) pattern already works.** `EpisodePolicyMetric` is already an EAV table with
   `metric_name` as the attribute. Adding new metrics means inserting rows with new `metric_name` values -- no DDL
   changes, no migrations, no downtime.

3. **Volume is manageable.** With ~50 metrics per agent, ~8 agents per episode, ~1000 episodes/day, that's ~400K metric
   rows/day, ~12M/month. PostgreSQL handles this comfortably with proper indexing. If volume grows 10x, we add
   partitioning before considering a different engine.

4. **Aggregation queries are infrequent.** Metrics dashboards refresh on page load, not in real-time. Queries that
   aggregate across thousands of episodes can tolerate 100-500ms response times. PostgreSQL with proper indexes and
   materialized views handles this.

5. **One fewer system to operate.** Every additional database adds deployment complexity, monitoring, backup procedures,
   failure modes, and on-call burden. The metrics workload doesn't justify this.

### Schema: Keep EAV, Add Indexes

The existing `episode_policy_metrics` table is the right foundation. No schema change is needed to start storing new
metrics -- only the filter in `complete_bulk_upload` needs to be removed.

Current schema (from migration v0):

```sql
CREATE TABLE episode_policy_metrics (
    episode_internal_id INTEGER NOT NULL REFERENCES episodes(internal_id),
    pv_internal_id INTEGER NOT NULL REFERENCES policy_versions(internal_id),
    metric_name TEXT NOT NULL,
    value FLOAT NOT NULL,
    PRIMARY KEY (episode_internal_id, pv_internal_id, metric_name)
);
```

New indexes needed (one migration):

```sql
-- Fast lookup: "all values of metric X for policy version Y"
CREATE INDEX idx_epm_pv_metric
    ON episode_policy_metrics (pv_internal_id, metric_name);

-- Fast lookup: "all metrics for episode E"
CREATE INDEX idx_epm_episode
    ON episode_policy_metrics (episode_internal_id);

-- Support time-range queries by joining to episodes.created_at
-- (episodes.internal_id is already indexed as SERIAL UNIQUE)
```

### Why EAV Works Here

The Entity-Attribute-Value pattern is often criticized, but it's a good fit when:

- **Attributes are homogeneous in type.** All metric values are `FLOAT`. No mixed types, no complex nested structures.
- **The attribute set changes frequently.** New game types, new stats, new capability breakdowns. Each is just a new
  `metric_name` string -- no ALTER TABLE, no migration, no deployment.
- **Queries filter on known attribute names.** We always query specific metrics (`WHERE metric_name = 'heart.gained'`),
  never "give me all columns." The composite PK and covering indexes make these point lookups fast.
- **The entity relationships are fixed.** The entity (episode × policy_version) is well-defined and doesn't change. Only
  the attributes (metric names) evolve.

The alternative -- a wide table with one column per metric -- would require a migration every time we add a stat, create
sparse rows (most metrics only apply to some game types), and hit PostgreSQL's column count limits as the metric
vocabulary grows.

### Adding New Metrics

To add a new metric type (e.g., a new game stat `gold.mined`):

1. The environment code emits the stat (mettagrid `stats_tracker.py`).
2. `episode_recording.py` already writes it to DuckDB (no change needed -- it iterates `agent_stats.items()`).
3. `complete_bulk_upload` persists it to PostgreSQL (after we remove the `reward`-only filter).
4. Query code references `metric_name = 'gold.mined'`.

No schema changes. No migrations. No deployments for the storage layer.

### Metric Name Registry

While the database is schema-free, the application layer should maintain a registry of known metric names. This serves
as documentation, enables validation, and provides display metadata.

```python
# metrics/registry.py

@dataclass(frozen=True)
class MetricDef:
    name: str              # DB metric_name, e.g. "heart.gained"
    display_name: str      # UI label, e.g. "Resources Gathered (Hearts)"
    category: str          # "capability", "performance", "training", "competitive"
    aggregation: str       # "sum", "mean", "max", "last" -- how to combine across episodes
    audience: str          # "customer", "internal", "both"
    description: str       # Human-readable explanation

METRICS: dict[str, MetricDef] = {
    "heart.gained": MetricDef(
        name="heart.gained",
        display_name="Hearts Gathered",
        category="capability",
        aggregation="mean",
        audience="customer",
        description="Average hearts collected per episode",
    ),
    # ... more metrics
}
```

This registry is code, not schema. Adding a metric means adding a Python dict entry and deploying -- no database
changes. Unregistered metrics can still be stored and queried; the registry just adds display metadata.

## Data Quality

### Current State: No Validation

Today there is **zero validation** of metric names or values at any stage of the pipeline:

- **C++ simulator** emits arbitrary string keys in `stats["agent"][agent_id]`. Metric names are hardcoded strings in C++
  with no centralized definition or naming convention enforcement.
- **`episode_recording.py`** iterates `agent_stats.items()` and inserts each name as-is into DuckDB. No allowlist, no
  pattern check, no normalization.
- **DuckDB schema** has `metric VARCHAR NOT NULL` — no constraints beyond non-null.
- **PostgreSQL schema** has `metric_name TEXT NOT NULL` — no CHECK constraint, no enum, no pattern enforcement.
- **No value validation** — NaN, infinity, and negative values where they shouldn't occur all pass through silently.
  Both `REAL` (DuckDB) and `FLOAT` (PostgreSQL) accept NaN and infinity.
- **No monitoring** — no logging when unexpected metric names appear, no dashboard of distinct metric names, no alerts
  on anomalous values.

### Risks

| Risk                                            | Impact                                                                                                                                                                | Likelihood                                   |
| ----------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------- |
| **Typo in C++ stat name** (e.g., `heart.ganed`) | Silently creates a new metric. Queries for the correct name return incomplete data. No error anywhere.                                                                | Medium — any C++ change can introduce this   |
| **NaN/infinity poisoning**                      | One bad value corrupts all aggregations. `AVG(...)` returns NaN if any input is NaN in PostgreSQL. Dashboard shows blank or broken charts.                            | Low — but catastrophic when it happens       |
| **Name drift across game versions**             | C++ renames a stat (e.g., `junction.held` → `aligned_junction_held`). Old and new episodes use different names. Queries return partial data. No migration path.       | High — already visible in current stat names |
| **Cross-game name collisions**                  | Two games use the same metric name for different things (e.g., `score` meaning different things in CogsGuard vs Machina). Aggregation across games produces nonsense. | Medium — grows as game types increase        |
| **Empty or whitespace metric names**            | `""` or `"  "` as metric name creates invisible, un-queryable rows                                                                                                    | Low — but no constraint prevents it          |

### Design: Defense in Depth

Validation should happen at multiple layers so that no single failure allows bad data through.

#### Layer 1: Write-Time Validation (in `complete_bulk_upload`)

Add validation when metrics flow from DuckDB into PostgreSQL. This is the narrowest chokepoint — all metrics pass
through `complete_bulk_upload()` in `stats_routes.py`.

```python
# metrics/validation.py

import math
import re
import logging

logger = logging.getLogger(__name__)

# Metric names must be non-empty, lowercase, using only [a-z0-9._] characters.
# This matches the existing convention (e.g., "heart.gained", "chest.heart.deposited_by_agent").
METRIC_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9._]{0,127}$")

def validate_metric_name(name: str) -> bool:
    """Check that a metric name follows the naming convention."""
    return bool(METRIC_NAME_PATTERN.match(name))

def validate_metric_value(value: float) -> bool:
    """Check that a metric value is a finite number."""
    return math.isfinite(value)

def validate_and_filter_metrics(
    metrics: list[tuple[int, str, float]],  # (agent_id, metric_name, value)
) -> list[tuple[int, str, float]]:
    """Validate metrics and filter out invalid ones. Log warnings for rejected metrics."""
    valid = []
    for agent_id, name, value in metrics:
        if not validate_metric_name(name):
            logger.warning("Rejected metric with invalid name: %r (agent %d)", name, agent_id)
            continue
        if not validate_metric_value(value):
            logger.warning("Rejected metric with non-finite value: %s=%r (agent %d)", name, value, agent_id)
            continue
        valid.append((agent_id, name, value))
    return valid
```

**Behavior:** Invalid metrics are logged and skipped, not rejected entirely. The episode still records — only the bad
metric rows are dropped. This avoids losing an entire episode because of one bad stat, while making problems visible in
logs.

#### Layer 2: Metric Name Registry (Warn on Unknown)

Upgrade the registry from pure documentation to active validation. Unknown metrics are still stored (the schema is
intentionally open), but a warning is logged so new metrics are noticed during development.

```python
# In validation.py or registry.py

def check_metric_registered(name: str) -> bool:
    """Check if a metric name is in the registry. Log a warning if not."""
    if name not in METRICS:
        logger.info("Unregistered metric name: %r (will be stored but has no display metadata)", name)
        return False
    return True
```

This creates a natural workflow: new stats from C++ show up as log warnings → developer adds them to the registry →
warnings stop. No hard failure, but no silent drift either.

#### Layer 3: PostgreSQL CHECK Constraint

Add a database-level constraint to prevent empty names and non-finite values from ever entering the table, regardless of
application bugs:

```sql
-- Migration v11 (alongside the new indexes)
ALTER TABLE episode_policy_metrics
    ADD CONSTRAINT chk_metric_name_nonempty CHECK (length(metric_name) > 0);

-- PostgreSQL FLOAT allows NaN/infinity by default. Reject them:
ALTER TABLE episode_policy_metrics
    ADD CONSTRAINT chk_value_finite CHECK (value = value AND value != 'Infinity' AND value != '-Infinity');
    -- Note: NaN != NaN in PostgreSQL, so "value = value" rejects NaN
```

These are last-resort guards. The application-layer validation (Layer 1) should catch problems first; the CHECK
constraints catch anything the application misses.

#### Layer 4: Periodic Audit Queries

Run periodic queries to detect data quality issues in existing data. These can run as a scheduled job or be checked
manually during development.

```sql
-- Find metric names that don't match the naming convention
SELECT DISTINCT metric_name
FROM episode_policy_metrics
WHERE metric_name !~ '^[a-z][a-z0-9._]{0,127}$';

-- Find non-finite values (NaN or infinity)
SELECT metric_name, COUNT(*)
FROM episode_policy_metrics
WHERE value != value  -- NaN
   OR value = 'Infinity'::float
   OR value = '-Infinity'::float
GROUP BY metric_name;

-- Find metrics that appear in very few episodes (possible typos)
SELECT metric_name, COUNT(*) as episode_count
FROM episode_policy_metrics
GROUP BY metric_name
HAVING COUNT(*) < 10
ORDER BY episode_count;

-- Find metric names not in the registry (requires a temp table or CTE of known names)
-- Useful for catching new stats from C++ that haven't been registered yet
SELECT DISTINCT metric_name
FROM episode_policy_metrics
WHERE metric_name NOT IN ('reward', 'action_timeout', 'heart.gained', ...);
```

#### Layer 5: C++ Side (Future)

Longer term, the C++ simulator should define stat names in a central header or config rather than scattering string
literals across game code. This is outside the scope of the metrics project but would eliminate the root cause of naming
inconsistency.

### Cleaning Existing Data

Before the metrics project starts serving data, audit the existing `episode_policy_metrics` table (currently only
`reward`) and the S3 DuckDB files (all metrics) for quality issues.

**Step 1: Audit current PostgreSQL data.**

```sql
-- What metric names exist today?
SELECT metric_name, COUNT(*), MIN(value), MAX(value), AVG(value)
FROM episode_policy_metrics
GROUP BY metric_name;
```

Expected result: only `reward` (since the filter has not been removed yet). If anything else appears, it indicates a bug
in the upload path.

**Step 2: Audit a sample of S3 DuckDB files.**

Download 100 random DuckDB files from S3 and inspect:

- Distinct metric names across files
- Distribution of values per metric (check for NaN, infinity, negative where unexpected)
- Naming consistency (are there both `junction.held` and `aligned_junction_held`?)

This produces the ground-truth vocabulary of metric names before we start persisting them all.

**Step 3: Build the initial registry from the audit.**

Every metric name found in the S3 audit becomes an entry in `metrics/registry.py`. Names that look like typos or
duplicates are documented as known issues with a plan to normalize (either fix the C++ code or add an alias mapping in
the validation layer).

**Step 4: Add a normalization mapping (if needed).**

If the audit reveals inconsistent naming (e.g., the same concept with two names), add a mapping:

```python
# metrics/validation.py

METRIC_NAME_ALIASES: dict[str, str] = {
    # Old name → canonical name
    # "junction.held": "aligned_junction_held",
}

def normalize_metric_name(name: str) -> str:
    """Normalize metric name to canonical form."""
    return METRIC_NAME_ALIASES.get(name, name)
```

Apply this in `complete_bulk_upload()` before insertion. Historical data can be corrected during backfill by applying
the same mapping.

## Data Durability

### Current Durability Model

```
Episode played → DuckDB file (local disk, ephemeral)
  → S3 upload (durable, referenced by episodes.data_uri)
    → PostgreSQL insert (durable, queryable)
```

The DuckDB file on S3 is the **source of truth**. PostgreSQL is a queryable index over it. If PostgreSQL data is lost,
it can be rebuilt from the S3 DuckDB files. This is important because:

- The DuckDB files contain ALL agent stats (not just the ones we filter for today).
- If we decide to store new metrics later, we can backfill from historical DuckDB files without re-running episodes.

### Durability Guarantees

| Layer                       | Durability                                | Recovery                                                |
| --------------------------- | ----------------------------------------- | ------------------------------------------------------- |
| DuckDB staging file (local) | Ephemeral -- exists during recording only | Lost if worker crashes mid-recording; episode is re-run |
| S3 DuckDB file              | 11 nines (S3 Standard)                    | Primary archive; survives any infrastructure failure    |
| PostgreSQL (RDS)            | Automated backups, point-in-time recovery | Restore from RDS backup or rebuild from S3 DuckDB files |

### Retention Policy

**Current state:** No S3 lifecycle policy exists. DuckDB files persist indefinitely, and storage costs grow unbounded.
This is accidental -- there was no explicit decision to retain or delete them.

**Why retention matters:** Until we remove the `reward`-only filter, the S3 DuckDB files are the **only record** of
non-reward agent stats for historical episodes. Deleting them before backfill would permanently lose that data.

**Recommended lifecycle:**

| Age              | Storage Class                | Rationale                                                                             |
| ---------------- | ---------------------------- | ------------------------------------------------------------------------------------- |
| 0-90 days        | S3 Standard                  | Active data; may need re-processing or debugging                                      |
| 90 days - 1 year | S3 Infrequent Access         | Backfill source; rare access but must be available                                    |
| 1+ years         | S3 Glacier Instant Retrieval | Archival; available for audit or re-processing within minutes                         |
| Never            | Delete                       | DuckDB files should not be deleted -- they're the only source of full per-agent stats |

**Implementation:** Add an S3 lifecycle rule to the `observatory-private` bucket for the `episodes/` prefix. This is a
Terraform change in `devops/tf/`, not application code.

**Object tagging (optional):** Tag DuckDB objects with `upload-date` and `season` at upload time to enable finer-grained
lifecycle rules (e.g., keep competition episodes longer than qualifying episodes). This requires a small change to
`get_bulk_upload_presigned_url()` to include tagging in the presigned URL.

### Backfill Strategy

Since historical DuckDB files on S3 contain all agent stats but PostgreSQL only has `reward`, we need a one-time
backfill to populate the new metrics.

**File granularity:** Each DuckDB file contains exactly one episode. Files are small (~5-20KB each) with S3 key pattern
`episodes/{upload_id}.duckdb`. This means backfill processes many small files rather than a few large ones.

**Estimated scale:** At ~1000 episodes/day for 6 months, that's ~180K files totaling ~2-3 GB of S3 storage. This is
small enough to process in a single batch run.

**Backfill process:**

1. **Enumerate files.** Use `ListObjectsV2` with prefix `episodes/` to list all DuckDB files. For larger volumes, use S3
   Inventory for a bulk manifest instead of paginated listing.

2. **Map S3 keys to episode records.** Each episode row in PostgreSQL has a `data_uri` column containing the full S3
   URI. Query `SELECT internal_id, data_uri FROM episodes` to build a lookup from S3 key → `episode_internal_id`. Files
   without a matching episode record can be skipped (orphaned uploads).

3. **Download and extract in parallel.** Process N files concurrently (e.g., 20 workers). For each file:
   - Download from S3 to a temp file.
   - Open with DuckDB in read-only mode.
   - Read `episode_agent_metrics` and `episode_agent_policies` tables.
   - Map `(episode_id, agent_id)` → `(episode_internal_id, pv_internal_id)` using the lookup from step 2.
   - Collect `(episode_internal_id, pv_internal_id, metric_name, value)` tuples.
   - Close connection and delete temp file.

4. **Batch insert.** Aggregate metrics from multiple files into batch INSERTs (e.g., 1000 rows per statement). Use
   `ON CONFLICT DO NOTHING` on the composite PK to skip `reward` rows that already exist. This makes backfill idempotent
   -- safe to re-run if interrupted.

5. **Track progress.** Record the last-processed S3 key (lexicographic order) in a simple state table or file. On
   restart, resume from the last key. Since UUIDs in S3 keys aren't time-ordered, this provides resumability but not
   strict chronological processing -- which is fine since backfill is idempotent.

**Consolidation (optional):** After backfill completes, consider merging small DuckDB files into larger time-based
archives (e.g., one file per day) for more efficient future re-processing. This is a separate optimization and not
required for the initial backfill.

## Query Patterns

### Primary Query: Capability Breakdown for a Policy Version

"Show me the behavioral capability metrics for my latest policy version."

```sql
SELECT metric_name, AVG(value) as avg_value, COUNT(*) as episode_count
FROM episode_policy_metrics epm
WHERE epm.pv_internal_id = :pv_internal_id
  AND epm.metric_name IN ('heart.gained', 'junction.aligned_by_agent', ...)
GROUP BY metric_name;
```

Uses index: `idx_epm_pv_metric`. Expected performance: <10ms for typical policy versions with <1000 episodes.

### Cross-Version Comparison

"Compare my last 5 policy versions on all capabilities."

```sql
SELECT pv.version, epm.metric_name, AVG(epm.value) as avg_value
FROM episode_policy_metrics epm
JOIN policy_versions pv ON pv.internal_id = epm.pv_internal_id
WHERE pv.policy_id = :policy_id
  AND pv.version >= :min_version
GROUP BY pv.version, epm.metric_name
ORDER BY pv.version, epm.metric_name;
```

### Internal: Customer Health Dashboard

"For each customer, what's their best score and latest submission date?"

```sql
SELECT p.user_id,
       MAX(epm.value) as best_reward,
       MAX(pv.created_at) as last_submission,
       COUNT(DISTINCT pv.id) as total_versions
FROM policies p
JOIN policy_versions pv ON pv.policy_id = p.id
LEFT JOIN episode_policy_metrics epm
    ON epm.pv_internal_id = pv.internal_id
    AND epm.metric_name = 'reward'
GROUP BY p.user_id;
```

### Materialized Views for Expensive Aggregates

For queries that scan large portions of the metrics table (platform-wide aggregates, percentile calculations), use
PostgreSQL materialized views refreshed on a schedule:

```sql
CREATE MATERIALIZED VIEW mv_policy_version_metrics AS
SELECT pv_internal_id, metric_name,
       AVG(value) as avg_value,
       STDDEV(value) as stddev_value,
       COUNT(*) as episode_count,
       MIN(value) as min_value,
       MAX(value) as max_value
FROM episode_policy_metrics
GROUP BY pv_internal_id, metric_name;

-- Refresh periodically (e.g., every 5 minutes via pg_cron or application timer)
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_policy_version_metrics;
```

This pre-computes per-policy-version metric summaries. Dashboard queries hit the materialized view instead of scanning
raw rows. The `CONCURRENTLY` option allows reads during refresh.

### Scaling Plan

If query performance degrades as data grows:

1. **Partitioning** -- Range-partition `episode_policy_metrics` by `episode_internal_id` (which correlates with time).
   Old partitions can be detached and archived. This is a PostgreSQL-native operation.

2. **Materialized views** -- Pre-aggregate expensive cross-episode queries as described above.

3. **Read replica** -- Route dashboard/analytics queries to a read replica, keeping the primary for writes.

4. **Archival** -- Move metrics older than N months to S3 (they're already there in DuckDB files). Drop old partitions
   from PostgreSQL. Rebuild from S3 if historical queries are needed.

None of these require changing the application schema or query patterns -- they're operational changes.

## Testing Strategy

### Unit Tests: Metric Computation Logic

Each metric computation module (`capabilities.py`, `training_progress.py`, etc.) should be testable in isolation with no
database dependency. Functions take dataframes or dicts of metric values and return computed results.

```python
# test_capabilities.py

def test_resource_efficiency():
    """resource_efficiency = deposited / gathered"""
    metrics = {
        "chest.heart.deposited_by_agent": 80.0,
        "heart.gained": 100.0,
    }
    result = compute_resource_efficiency(metrics)
    assert result == pytest.approx(0.8)

def test_resource_efficiency_zero_gathered():
    """Handle zero division gracefully."""
    metrics = {
        "chest.heart.deposited_by_agent": 0.0,
        "heart.gained": 0.0,
    }
    result = compute_resource_efficiency(metrics)
    assert result == 0.0
```

### Integration Tests: Database Round-Trip

Use the existing testcontainers PostgreSQL infrastructure (see `conftest.py`) to verify that metrics survive the full
write → read → aggregate cycle.

```python
# test_metrics_integration.py

class TestMetricsRoundTrip:
    """Tests use class-scoped postgres_container from conftest.py."""

    async def test_store_and_retrieve_capability_metrics(self, stats_client):
        """Write episode with multiple agent stats, verify all are queryable."""
        # 1. Create policy + version via stats_client
        # 2. Record episode with agent stats (heart.gained, junction.aligned_by_agent, etc.)
        # 3. Query metrics API endpoint
        # 4. Assert all metrics present with correct values

    async def test_new_metric_type_no_migration(self, stats_client):
        """Adding a metric type unknown to the registry still stores and queries correctly."""
        # 1. Record episode with metric_name="totally_new_stat"
        # 2. Query it back
        # 3. Assert it works -- no schema change needed

    async def test_cross_version_comparison(self, stats_client):
        """Verify capability delta between two policy versions."""
        # 1. Create policy with two versions
        # 2. Record episodes for each with different metric values
        # 3. Query cross-version comparison endpoint
        # 4. Assert deltas are correct
```

### Backfill Tests

Test the backfill process against a fixture DuckDB file to verify idempotency:

```python
def test_backfill_idempotent(isolated_stats_client, tmp_path):
    """Running backfill twice produces the same result."""
    # 1. Create a DuckDB file with known metrics
    # 2. Run backfill
    # 3. Assert metrics in PostgreSQL
    # 4. Run backfill again
    # 5. Assert no duplicates (ON CONFLICT DO NOTHING)
```

### Property-Based Tests

For aggregation correctness, consider hypothesis-based tests:

```python
from hypothesis import given, strategies as st

@given(values=st.lists(st.floats(min_value=-1e6, max_value=1e6, allow_nan=False), min_size=1))
def test_mean_aggregation_matches_manual(values):
    """Verify our mean aggregation matches Python's statistics.mean."""
    result = aggregate_metric(values, method="mean")
    assert result == pytest.approx(statistics.mean(values))
```

### Test Data Factories

Create factories for common test patterns to avoid boilerplate:

```python
# test_support/metric_factories.py

def make_episode_with_metrics(
    stats_client: StatsClient,
    policy_version_id: uuid.UUID,
    metrics: dict[str, float],
) -> uuid.UUID:
    """Create an episode with the given metrics. Returns episode_id."""
    ...
```

## API Design

### Endpoints

All endpoints live under `/stats/metrics/` and are added to the existing stats router.

```
GET  /stats/metrics/capabilities/{policy_version_id}
     → { metrics: { "heart.gained": { avg: 42.3, stddev: 5.1, episodes: 150 }, ... } }

GET  /stats/metrics/comparison/{policy_id}?versions=5
     → { versions: [ { version: 10, metrics: {...} }, { version: 9, metrics: {...} }, ... ] }

GET  /stats/metrics/progress/{policy_id}
     → { improvement_rate: 0.05, plateau: false, regression: false, ... }

GET  /stats/metrics/competitive/{policy_version_id}
     → { rank: 12, percentile: 85, win_rate: 0.62, ... }

# Internal endpoints (require admin auth)
GET  /stats/metrics/internal/customer-health
     → { customers: [ { user_id: "...", best_score: 1.2, ... }, ... ] }

GET  /stats/metrics/internal/platform-health
     → { active_customers: 45, improving: 30, stuck: 8, ... }
```

### Response Caching

Metric aggregates don't change between episodes. Use HTTP cache headers:

- **Capability/competitive metrics**: `Cache-Control: max-age=300` (5 minutes). Refreshes when new episodes complete.
- **Internal dashboards**: `Cache-Control: max-age=900` (15 minutes). Aggregate queries are expensive; staleness is
  acceptable.
- **Cross-version comparison**: `Cache-Control: max-age=3600` (1 hour). Historical data doesn't change.

## Implementation Phases

### Phase 0: Audit Existing Data & Establish Validation

Before opening the floodgates, understand what data exists and add validation so bad data can't get in.

Changes:

- Audit script: Sample S3 DuckDB files and report distinct metric names, value distributions, anomalies.
- `metrics/validation.py`: Write-time validation (name pattern, finite value checks).
- `metrics/registry.py`: Initial metric name registry built from audit results.
- `migrations.py`: Add CHECK constraints (`chk_metric_name_nonempty`, `chk_value_finite`) in migration v11.
- Tests for validation logic (invalid names, NaN, infinity, empty strings).

Result: Validation infrastructure is in place before we start persisting new metrics. Known metric vocabulary is
documented. Any naming inconsistencies in existing data are identified.

### Phase 1: Persist All Agent Stats

Remove the `reward`-only filter in `complete_bulk_upload` so all agent stats recorded in DuckDB flow through to
PostgreSQL. Validation from Phase 0 ensures only clean data enters.

Changes:

- `stats_routes.py`: Remove `if metric_name != "reward": continue` filter, add call to `validate_and_filter_metrics()`.
- `migrations.py`: Add new indexes (`idx_epm_pv_metric`, `idx_epm_episode`) in migration v11 (same migration as CHECK
  constraints).
- Backfill job: Script to re-process historical S3 DuckDB files, applying validation and normalization.

Result: All future episodes store full agent stats (validated). Historical data backfilled. No API changes yet.

### Phase 2: Metric Registry + Capability Queries

Build the computation and serving layer.

Changes:

- `metrics/registry.py`: Metric definitions with display metadata.
- `metrics/capabilities.py`: Compute capability breakdowns from stored metrics.
- `metrics/routes.py`: API endpoints for capability queries.
- Tests for computation logic and API round-trip.

Result: Observatory frontend can show capability breakdowns for any policy version.

### Phase 3: Training Progress + Competitive Metrics

Add cross-version analysis and tournament integration.

Changes:

- `metrics/training_progress.py`: Improvement rate, plateau/regression detection.
- `metrics/competitive.py`: Win rate, percentile, consistency from tournament data.
- Materialized view for pre-aggregated per-policy-version summaries.

Result: Customers see training progress trends and competitive standing details.

### Phase 4: Internal Dashboards

Add Softmax-internal customer health and platform health metrics.

Changes:

- `metrics/customer_health.py`: Per-customer aggregations.
- `metrics/platform_health.py`: Platform-wide aggregates.
- Internal API endpoints with admin auth.

Result: Softmax team can monitor customer health and platform trends.

## Decision Log

| Decision                                          | Rationale                                                                                                          |
| ------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| Keep PostgreSQL, don't add Timestream/DynamoDB    | Metrics are relational (join to episodes, policies, users). Volume is manageable. One fewer system to operate.     |
| Keep EAV pattern for metrics                      | Attribute set changes frequently. All values are FLOAT. Avoids migrations for new metric types.                    |
| S3 DuckDB files as source of truth                | Already durable (11 nines). Contains all stats. Enables backfill and re-processing.                                |
| Materialized views for aggregates                 | Avoid scanning raw table for dashboard queries. PostgreSQL-native, no new infrastructure.                          |
| Metric registry in code, not schema               | Adding metrics = code change + deploy, not migration + deploy. Registry is documentation + validation.             |
| Backfill from S3 before adding API                | Ensures historical data is available from day one. Idempotent via ON CONFLICT DO NOTHING.                          |
| Log-and-skip for invalid metrics, not hard reject | Avoids losing entire episodes over one bad stat. Problems are visible in logs but don't block the pipeline.        |
| Validate at write time + CHECK constraints        | Defense in depth: application catches most issues, DB constraints catch the rest. No single layer can be bypassed. |
| Audit before opening the filter                   | Phase 0 ensures we know what's in the data before we start persisting everything. Prevents surprises.              |
