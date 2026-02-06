# Testing the Policy Dashboard

## When to Run Tests

Run the test suite **before every commit** to this skill:

```bash
uv run python skills/cg.policy-dashboard/test_dashboard.py
```

All 11 tests must pass before committing changes.

## Test Fixtures

The `test_fixtures/` directory contains sample episode result JSON files that exercise different dashboard scenarios:

| File                       | Purpose                                                |
| -------------------------- | ------------------------------------------------------ |
| `episode_basic.json`       | 4 agents, standard metrics, mid-range rewards          |
| `episode_high_reward.json` | 4 agents, high performance (45-55 reward), 10000 steps |
| `episode_low_reward.json`  | 4 agents, poor performance, many action failures       |
| `episode_minimal.json`     | 1 agent, minimal required fields only                  |

## What the Tests Cover

1. **Data Conversion** (`result_to_episode_data`)
   - Basic conversion from result dict to EpisodeData
   - Handling split team compositions (e.g., 2v2 with opponents)
   - Graceful handling of missing optional fields like `steps`

2. **Metric Aggregation** (`aggregate_agent_metrics`)
   - Summing metrics across agents belonging to one policy
   - Excluding opponent agents from aggregation
   - Handling None values in metrics

3. **Local Mode** (`load_local_results`)
   - Loading JSON files from a directory
   - Respecting the `--limit` parameter
   - Handling empty directories gracefully
   - Skipping invalid/malformed JSON files with warnings

4. **Serialization** (`data_to_dict`)
   - Converting DashboardData to JSON-serializable dict
   - Preserving all fields including nested metrics

5. **Dashboard Generation** (`generate_dashboard`)
   - Creating valid HTML output
   - Embedding episode data correctly in the template

6. **Integration** (`test_full_local_mode_pipeline`)
   - End-to-end: load fixtures → generate dashboard → verify output

## Adding New Tests

When adding new features to the dashboard:

1. Add a test fixture in `test_fixtures/` if the feature needs specific data shapes
2. Add a test function in `test_dashboard.py` following the naming convention `test_<feature_name>`
3. Run the full suite to ensure no regressions

## Running Individual Tests

To run a specific test for debugging:

```python
# In Python
from test_dashboard import test_result_to_episode_data_basic
test_result_to_episode_data_basic()
```

Or modify the `main()` function temporarily to run only the test you're working on.
