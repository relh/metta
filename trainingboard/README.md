# Trainingboard

`trainingboard/` is a local package for one job: show and rank training-loop improvement ideas on a wall-screen board.

It combines:

- a local API server (`backend`)
- a local dashboard (`frontend`)
- Asana ingestion + normalization (`ingest`)
- LLM-based task scoring cache (`data/task_llm_scores.ndjson`)

## What The Board Shows

Training opportunities are scored on 12 metrics:

- Impact (6): experience parallelism, experience quality, loss parallelism, loss signal quality, parameter parallelism,
  hyperparameter quality
- Execution (6): simplicity, time to implement, failure likelihood, dependency load, measurement speed, reversibility

Top Bets is the global top-15 list, split into:

- `Now` (ranks 1-5)
- `Next` (ranks 6-10)
- `Later` (ranks 11-15)

## Scoring Model (Important)

LLM scores are the canonical source of truth.

- Dashboard axis panels use cached LLM scores only.
- Top Bets ranking uses cached LLM scores only.
- Tasks without LLM scores are excluded from LLM-only ranking.

If no LLM cache exists yet, board rankings will be empty until you generate scores.

## Quickstart

From repo root (fastest for daily use):

```bash
metta trainingboard
```

This starts the board server on `127.0.0.1:8877`.

Direct package mode:

```bash
cd trainingboard
uv sync
uv run trainingboard serve --host 127.0.0.1 --port 8877
```

Open `http://127.0.0.1:8877`.

## Typical Workflow

1. Ingest tasks from Asana

```bash
cd trainingboard
ASANA_TOKEN=... uv run trainingboard ingest-asana --project-gid <ASANA_PROJECT_GID> --story-workers 12
```

Or from a specific Asana list:

```bash
ASANA_TOKEN=... uv run trainingboard ingest-asana \
  --source-url "https://app.asana.com/1/<workspace>/project/<project_gid>/list/<section_gid>" \
  --story-workers 12
```

2. Generate/refresh LLM scores in batches

```bash
OPENAI_API_KEY=... uv run trainingboard rank-tasks --llm --llm-task-limit 50 --llm-task-offset 0 --limit 50
OPENAI_API_KEY=... uv run trainingboard rank-tasks --llm --llm-task-limit 50 --llm-task-offset 50 --limit 50
```

3. Launch the board and verify coverage

The header shows `scoring: LLM only (x/y)`.

## CLI Commands

- `trainingboard serve`
  - run local board server
- `trainingboard ingest-asana`
  - fetch + normalize Asana tasks/stories into NDJSON cache
- `trainingboard snapshot`
  - print dashboard JSON payload
- `trainingboard rank-tasks`
  - print ranked task JSON (12 metrics + aggregate scores)

`rank-tasks` behavior:

- always loads cached LLM scores for output ranking
- defaults to LLM-only ranking (`require_llm_scores=True`)
- with `--llm`, it refreshes cache entries via OpenAI first, then ranks from cache

## Cache Files

- Normalized state cache: `~/.trainingboard/cache/asana_research_cache.ndjson`
- Normalized repo cache (committed): `trainingboard/data/asana_research_cache.ndjson`
- LLM state cache: `~/.trainingboard/cache/task_llm_scores.ndjson`
- LLM repo cache (committed): `trainingboard/data/task_llm_scores.ndjson`
- Raw ingest cache: `~/.trainingboard/cache/asana_research_raw_cache_<project_gid>_<section_or_all>.json`

When serving/ranking, trainingboard prefers the newer of repo vs state caches.

## Wall-Screen Notes

- Board mode is default.
- Auto-refresh is every 45 seconds.
- Header includes a compact legend for the 12 metric abbreviations.

## Helper Script

`trainingboard/scripts/ingest_asana_project.sh` is a small wrapper around `trainingboard ingest-asana`.
