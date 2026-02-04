---
name: cg.policy-dashboard
description:
  Generate an interactive HTML dashboard for deep-dive analysis of a single tournament policy's performance. Fetches
  episode data, opponent matchups, behavioral metrics, and failure patterns.
---

## Usage

```bash
/cg.policy-dashboard [--policy name:version] [--limit 100] [--output ./dashboard.html]
```

## Parameters

- `--policy`: Policy to analyze (format: `name:version` or `name` for latest). If omitted, shows interactive picker.
- `--limit`: Maximum episodes to fetch detailed stats for (default: 100).
- `--output`: Output HTML file path (default: `./cg_dashboard_{policy}_{version}_{timestamp}.html`).
- `--season`: Tournament season (default: `beta-cvc`).

## What It Does

1. Authenticates with tournament API (reuses `cogames login` token)
2. If `--policy` not provided, lists your policies for selection
3. Fetches:
   - Leaderboard entry (rank, score)
   - Match history (opponents, scores, job IDs)
   - Episode stats for each match (detailed metrics)
4. Generates self-contained HTML dashboard with:
   - Overview: reward distribution, key metrics, high/low scoring analysis
   - Episodes: sortable/filterable table with drill-down
   - Opponents: head-to-head breakdown
   - Behavior: action efficiency, resources, junctions
   - Failures: error analysis, diagnostic patterns
5. Opens dashboard in default browser

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
```
