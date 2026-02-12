---
name: cg.policy-dashboard
description:
  Generate an interactive HTML dashboard for deep-dive analysis of a single tournament policy's performance. Fetches
  episode data, opponent matchups, behavioral metrics, and failure patterns.
---

## Usage

```bash
# Tournament mode (fetches from Observatory API)
/cg.policy-dashboard [--policy name:version] [--limit 100] [--output ./dashboard.html]

# Local mode (reads from local result JSON files)
/cg.policy-dashboard --local-results DIR [--policy-name NAME] [--limit 100] [--output ./dashboard.html]
```

## Parameters

- `--policy`: Policy to analyze (format: `name:version` or `name` for latest). If omitted, shows interactive picker.
  Tournament mode only.
- `--limit`: Maximum episodes to fetch/load (default: 100).
- `--output`: Output HTML file path (default: `./cg_dashboard_{policy}_{version}_{timestamp}.html`).
- `--season`: Tournament season (default: `beta-cvc`). Tournament mode only.
- `--local-results`: Directory of episode result JSON files. Enables local mode (no auth required).
- `--policy-name`: Policy name for local mode (default: directory name).
- `--claude`: Include Claude AI analysis (adds 10-30s). Off by default.
- `--claude-model`: Model for Claude analysis (default: `sonnet`). Use `opus` for deeper analysis.

## What It Does

### Tournament Mode (default)

1. Authenticates with tournament API (reuses `cogames login` token)
2. If `--policy` not provided, lists your policies for selection
3. Fetches leaderboard entry, match history, and episode stats
4. Generates self-contained HTML dashboard
5. Opens dashboard in default browser

### Local Mode (`--local-results`)

1. Reads `*.json` files from the specified directory (sorted by modification time)
2. Parses each as a `PureSingleEpisodeResult` dict (expects `rewards`, `stats`, and optionally `steps` keys)
3. Skips non-matching files with a warning
4. No authentication required

Both modes generate the same dashboard with:

- Overview: reward distribution, key metrics, high/low scoring analysis
- Episodes: sortable/filterable table with drill-down
- Opponents: head-to-head breakdown (tournament mode)
- Behavior: action efficiency, resources, junctions
- Failures: error analysis, diagnostic patterns

## Analysis Guide

See `skills/cg.policy-dashboard/analysis-guide.md` for:

- Metric definitions and expected ranges
- Diagnostic patterns for common issues
- Benchmarks from top policies

## Examples

```bash
# Interactive policy selection, default 100 episodes
/cg.policy-dashboard

# Specific policy version
/cg.policy-dashboard --policy planky:v22

# More episodes, custom output
/cg.policy-dashboard --policy planky:v22 --limit 200 --output ./planky_analysis.html

# Local mode: analyze results from a cogames play run
/cg.policy-dashboard --local-results ./eval_results/ --policy-name my-policy

# Local mode with custom limit
/cg.policy-dashboard --local-results ./train_dir/my_run/eval/ --limit 50
```
