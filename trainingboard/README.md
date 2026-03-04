# Trainingboard

`trainingboard` is a standalone local package for ranking training-flywheel opportunities across six axes:

1. Experience-level parallelism
2. Experience quality
3. Loss-level parallelism
4. Loss signal quality
5. Parameter-level parallelism
6. Hyperparameter quality

The package provides three pieces:

- `backend`: local API server that computes and serves six-axis scores
- `frontend`: six-panel dashboard UI
- `ingest`: Asana project ingestion for research-paper/task fodder

## Quickstart

```bash
cd trainingboard
uv sync

# Sync from a whole Asana project
ASANA_TOKEN=... uv run trainingboard ingest-asana --project-gid <ASANA_PROJECT_GID> --story-workers 12

# Sync from a specific Asana list/section URL and merge into output cache
ASANA_TOKEN=... uv run trainingboard ingest-asana --source-url "https://app.asana.com/1/<workspace>/project/<project_gid>/list/<section_gid>" --story-workers 12

# Start dashboard
uv run trainingboard serve --host 127.0.0.1 --port 8877
```

Open `http://127.0.0.1:8877`.

## Data model

`trainingboard` computes a projected multiplier per axis from:

- a prior multiplier (seeded from current beliefs)
- evidence mass from ingested task titles/notes/custom-fields/comments
- extracted research-paper links (arXiv/OpenReview/etc)
- extracted recommendation/action snippets from task notes/comments
- inferred per-axis scores for each record based on six-axis keyword maps
- best-win candidate interventions per axis

The API response includes per-axis confidence, opportunity score, and suggested wins.

## CLI

- `trainingboard serve`: run local dashboard server
- `trainingboard ingest-asana`: incrementally sync Asana task + story data, then write normalized research cache
  - supports `--source-url` for list/section URLs
  - supports `--merge-output` (default) to combine multiple sources into one output cache
  - if a list/section URL yields zero tasks, ingestion falls back to the full project
- `trainingboard snapshot`: print computed dashboard JSON from current cache

## Caching

- Normalized cache (used by dashboard): `~/.trainingboard/cache/asana_research_cache.json`
- Raw cache (task+story incremental sync):
  `~/.trainingboard/cache/asana_research_raw_cache_<project_gid>_<section_or_all>.json`
- Unchanged tasks (by `modified_at`) reuse cached stories to avoid unnecessary API calls.

## Scripts

`trainingboard/scripts/ingest_asana_project.sh` wraps ingestion with basic env handling.
