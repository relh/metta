# Sample Data for Policy Dashboard Demo

This directory contains 25 sample episodes designed to showcase all features of the policy dashboard. Use it to
familiarize yourself with the dashboard's capabilities.

## Generate the Dashboard

```bash
uv run python skills/cg.policy-dashboard/generate.py \
  --local-results skills/cg.policy-dashboard/sample_data \
  --policy-name "demo-policy" \
  --output demo_dashboard.html
```

## Extended JSON Format

Sample data files can include optional metadata fields (prefixed with `_`) to demonstrate tournament-like features:

```json
{
  "_opponent_name": "aggressive-bot",
  "_opponent_version": 3,
  "_assignments": [0, 0, 1, 1],
  "_status": "completed",
  "_error_type": null,
  "rewards": [...],
  "stats": {...},
  "steps": 10000
}
```

| Field               | Description                                                             |
| ------------------- | ----------------------------------------------------------------------- |
| `_opponent_name`    | Name of the opponent policy                                             |
| `_opponent_version` | Version number of opponent                                              |
| `_assignments`      | Which agents belong to which policy (0=ours, 1+=opponent)               |
| `_status`           | Episode status: "completed", "failed", "timeout"                        |
| `_error_type`       | Error type if failed: "OOMKilled", "Timeout", "RuntimeError", "S3Error" |

## Episode Scenarios

### Solo Episodes (4v0) - Episodes 01-10

| File                      | Scenario             | Key Features                                  |
| ------------------------- | -------------------- | --------------------------------------------- |
| `01_dominant_win`         | Top-tier performance | High rewards (55-62), excellent success rates |
| `02_close_match`          | Competitive game     | Mid-range rewards, mixed results              |
| `03_crushing_defeat`      | Poor performance     | Very low rewards, high failures               |
| `04_resource_hoarder`     | Resource strategy    | High carbon/silicon, focus on gathering       |
| `05_aggressive_fighter`   | Junction focus       | High junction alignment, resource churn       |
| `06_junction_master`      | Junction optimized   | 52-65 aligned per agent                       |
| `07_timeout_prone`        | Latency issues       | 25-45 timeouts per agent                      |
| `08_early_termination`    | Short episode        | 2,500 steps only                              |
| `09_marathon_game`        | Extended play        | 20,000 steps, highest rewards                 |
| `10_balanced_performance` | Average baseline     | Median across all metrics                     |

### Opponent Matches (2v2) - Episodes 11-15, 22-24

| File                           | Opponent            | Outcome  | Features                                     |
| ------------------------------ | ------------------- | -------- | -------------------------------------------- |
| `11_vs_aggressive_bot_win`     | aggressive-bot v3   | Win      | Our policy outperforms opponent              |
| `12_vs_aggressive_bot_loss`    | aggressive-bot v3   | Loss     | Opponent dominates with better junction ctrl |
| `13_vs_defensive_turtle`       | defensive-turtle v7 | Close    | Long game against passive opponent           |
| `14_vs_random_chaos`           | random-chaos v1     | Easy win | Opponent has many timeouts and failures      |
| `15_vs_top_ranked`             | champion-v2 v15     | Loss     | Elite opponent with perfect efficiency       |
| `22_vs_aggressive_bot_rematch` | aggressive-bot v3   | Draw     | Close rematch, improved performance          |
| `23_vs_defensive_turtle_close` | defensive-turtle v7 | Draw     | Extended marathon, 18k steps                 |
| `24_mirror_match`              | demo-policy v1      | Draw     | Self-play, nearly identical stats            |

### Failure Episodes - Episodes 16-19

| File                 | Error Type   | Features                                    |
| -------------------- | ------------ | ------------------------------------------- |
| `16_failed_oom`      | OOMKilled    | Early termination at 1,500 steps            |
| `17_failed_timeout`  | Timeout      | High action.timeout metrics, 3,000 steps    |
| `18_failed_crash`    | RuntimeError | Very early crash at 250 steps, zero rewards |
| `19_failed_s3_error` | S3Error      | Mid-game failure at 5,500 steps             |

### Asymmetric Team Compositions - Episodes 20-21

| File                | Composition | Features                                |
| ------------------- | ----------- | --------------------------------------- |
| `20_asymmetric_1v3` | 1v3         | Our single agent vs three opponents     |
| `21_asymmetric_3v1` | 3v1         | Our three agents dominate lone opponent |

### Special Scenarios - Episode 25

| File                  | Scenario       | Features                                      |
| --------------------- | -------------- | --------------------------------------------- |
| `25_eight_player_ffa` | 2v6 (8 agents) | Large-scale match, multiple opponent policies |

## Dashboard Features to Explore

### Overview Tab

- **Reward Distribution**: Wide range from 0 (crash) to 73+ (marathon)
- **Key Metrics Summary**: Aggregated action success rates, resources
- **High/Low Performers**: Quick identification of best/worst episodes

### Episodes Tab

- **Sortable Columns**: Sort by reward, steps, status, opponent
- **Status Filtering**: Filter by completed vs failed episodes
- **Episode Details**: Expand for full metric breakdown

### Opponents Tab

- **Head-to-Head Records**: Win/loss against each opponent
- **Opponent Comparison**: aggressive-bot vs defensive-turtle vs champion-v2
- **Performance Trends**: Multiple matches against same opponent

### Behavior Tab

- **Action Efficiency**: Compare move success/fail ratios
- **Resource Management**: Carbon/silicon gain vs loss
- **Junction Performance**: Aligned vs scrambled ratios

### Failures Tab

- **Error Type Breakdown**: OOM, Timeout, RuntimeError, S3Error
- **Failure Patterns**: Correlation with opponent, step count
- **Timeout Analysis**: Episodes 07, 17 show high timeout rates
- **Early Termination**: Episodes 08, 16, 18 show short runs

## Metric Ranges in This Dataset

| Metric             | Low           | Typical | High   |
| ------------------ | ------------- | ------- | ------ |
| Reward (per agent) | 0-5           | 25-40   | 55-78  |
| Steps              | 250           | 10,000  | 20,000 |
| Move Success Rate  | 30%           | 85%     | 98%    |
| Junction Aligned   | 1-5           | 20-35   | 52-78  |
| Action Timeouts    | 0             | 1-5     | 25-52  |
| Failed Episodes    | 4 of 25 (16%) | -       | -      |

## CogsGuard Actions

The sample data uses the actual CogsGuard action set:

| Action        | Description             |
| ------------- | ----------------------- |
| `move`        | Move in a direction     |
| `noop`        | Do nothing              |
| `change_vibe` | Change agent vibe state |

## Opponent Summary

| Opponent            | Matches | Wins | Losses | Draws | Style                              |
| ------------------- | ------- | ---- | ------ | ----- | ---------------------------------- |
| aggressive-bot v3   | 3       | 1    | 1      | 1     | High junction activity             |
| defensive-turtle v7 | 2       | 0    | 0      | 2     | Passive, high noop, resource hoard |
| random-chaos v1     | 1       | 1    | 0      | 0     | Unpredictable, many timeouts       |
| champion-v2 v15     | 1       | 0    | 1      | 0     | Elite efficiency, top-tier         |
| demo-policy v1      | 1       | 0    | 0      | 1     | Mirror match                       |
| (failed opponents)  | 4       | -    | -      | -     | Various error conditions           |
