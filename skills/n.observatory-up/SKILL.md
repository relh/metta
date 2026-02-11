---
name: n.observatory-up
description:
  Start, test, and debug the local Observatory dev environment (metta observatory up). Use when running the Observatory
  server locally, testing API endpoints, managing migrations, or debugging startup failures.
---

# Observatory Local Dev

## Quick Start

```bash
metta observatory up                    # Start ALL services (postgres, server, frontend, watcher, tournament, etc.)
metta observatory postgres up -d        # Start just postgres (backgrounded)
metta observatory server                # Start just the API server (needs postgres + localstack)
```

Selective service startup: `metta observatory up server` starts only server + its dependencies (postgres, localstack,
k8s). Useful for testing APIs without frontend/watcher/tournament overhead.

## Architecture

```
process-compose.yaml orchestrates:
  localstack  (port 4566) ─── S3 emulation
  k8s         ─────────────── K8s health check (OrbStack or k3d)
  postgres    (port 5432) ─── PostgreSQL via docker-compose
  server      (port 8000) ─── FastAPI backend (depends on postgres + localstack)
  frontend    (port 5173) ─── Next.js UI
  watcher     ─────────────── K8s job watcher (depends on server)
  tournament  ─────────────── Tournament commissioner (depends on server)
```

Process-compose API runs on port 8090:

```bash
curl http://localhost:8090/processes                    # List all processes
curl -X POST http://localhost:8090/process/restart/server  # Restart a service
curl -X POST http://localhost:8090/process/stop/tournament # Stop a service
```

Note: URLs are `/process/{action}/{name}`, NOT `/process/{name}/{action}`.

## Authentication

For local dev, the server accepts a debug token via the `X-Auth-Token` header.

**The debug token value** is the `LOCAL_MACHINE_TOKEN` constant in `metta/setup/tools/observatory/cli.py` (an email
address). Set it as `LOCAL_DEV_TOKEN` below:

```bash
curl -H "X-Auth-Token: $LOCAL_DEV_TOKEN" http://127.0.0.1:8000/whoami
# Returns: {"user_email":"$LOCAL_DEV_TOKEN"}
```

**WARNING:** `~/.metta/config.yaml` stores `local-dev-token` for `http://127.0.0.1:8000`, but the server only recognizes
`$LOCAL_DEV_TOKEN`. The Python client (`BaseAppBackendClient`) will read the wrong token from config. For local dev,
construct the client manually:

```python
from metta.app_backend.clients.stats_client import StatsClient
client = StatsClient(backend_url="http://127.0.0.1:8000", machine_token="$LOCAL_DEV_TOKEN")
```

Or use curl/httpx directly with the header.

## Migrations

The server runs migrations on startup (`RUN_MIGRATIONS=true` in local dev env).

### Migration failures (most common issue)

**Symptom:** Server crashes at startup with `DuplicateColumn`, `DuplicateTable`, or similar.

**Cause:** Database was created with a different branch's migration ordering. The migration system tracks the last
Alembic revision hash, but if branch A and B have divergent migration histories, switching branches can leave the DB at
a revision the new code doesn't recognize.

**Fix (nuclear - reset DB):**

```bash
metta observatory postgres down
docker volume rm app_backend_postgres_data
metta observatory up  # Fresh DB, all migrations re-applied
```

**Fix (surgical - stamp to a known revision):**

```bash
docker exec app_backend-postgres-1 psql -U postgres -d metta \
  -c "UPDATE alembic_version SET version_num = '<target_revision>'"
```

**Check current migration state:**

```bash
docker exec app_backend-postgres-1 psql -U postgres -d metta \
  -c "SELECT * FROM alembic_version"
```

**Migrations:** Managed via Alembic (`app_backend/alembic/versions/`). To create a new migration:
`cd app_backend && alembic revision --autogenerate -m "description"`

## Tournament CLI

```bash
metta observatory tournament run                            # Run commissioner
metta observatory tournament roll-season beta-cogsguard     # Roll season to new version
```

**PATH gotcha:** If `which metta` points to a different worktree (e.g., `m2/.venv/bin/metta`), tournament subcommands
may not exist. Use the repo-local binary: `/path/to/repo/.venv/bin/metta observatory tournament ...`

Alternative (direct Python, no metta binary needed):

```bash
STATS_DB_URI="postgres://postgres:password@127.0.0.1:5432/metta" \
  uv run python -c "from metta.app_backend.tournament.cli import roll_season; roll_season('beta-cogsguard')"
```

## Key Files

| Area                      | Path                                                                  |
| ------------------------- | --------------------------------------------------------------------- |
| CLI entry                 | `metta/setup/tools/observatory/cli.py`                                |
| Process orchestration     | `metta/setup/tools/observatory/process-compose.yaml`                  |
| Server startup/lifespan   | `app_backend/src/metta/app_backend/server.py`                         |
| Auth middleware           | `app_backend/src/metta/app_backend/auth.py`                           |
| Migrations (Alembic)      | `app_backend/alembic/versions/`                                       |
| Database config           | `app_backend/src/metta/app_backend/database.py`                       |
| Tournament routes         | `app_backend/src/metta/app_backend/routes/tournament_routes.py`       |
| Season resolver           | `app_backend/src/metta/app_backend/tournament/season_resolver.py`     |
| Roll season script        | `app_backend/src/metta/app_backend/tournament/scripts/roll_season.py` |
| Tournament CLI            | `app_backend/src/metta/app_backend/tournament/cli.py`                 |
| Docker compose (postgres) | `app_backend/docker-compose.dev.yml`                                  |
| K8s management            | `metta/setup/tools/observatory/local_k8s.py`                          |
| Python client             | `app_backend/src/metta/app_backend/clients/stats_client.py`           |
| Auth config reader        | `common/src/metta/common/auth/auth_config_reader_writer.py`           |
| Design notes              | `.devcontainer/observatory_design_notes.md`                           |

## DB Connection

```
Host: 127.0.0.1
Port: 5432
User: postgres
Password: password
Database: metta
URI: postgres://postgres:password@127.0.0.1:5432/metta
```

Container name: `app_backend-postgres-1`

```bash
docker exec app_backend-postgres-1 psql -U postgres -d metta -c "SELECT ..."
```

## Known Agent Pitfalls

1. **Backgrounding:** `metta observatory up` is a long-running process. Background it and poll for readiness:

   ```bash
   # Background the process
   metta observatory up &
   # Wait for server
   until curl -sf http://127.0.0.1:8000/whoami > /dev/null 2>&1; do sleep 2; done
   ```

2. **Auth confusion:** Don't look in `~/.metta/config.yaml` for local tokens. The local dev token is hardcoded:
   `$LOCAL_DEV_TOKEN` via `X-Auth-Token` header.

3. **Wrong `metta` binary:** If `which metta` points to a different worktree, commands may be missing or behave
   differently. Always verify `which metta` or use the repo-local binary.

4. **Migration state between branches:** Alembic supports downgrades, so switching branches rarely requires a DB reset.
   If startup fails, check `SELECT * FROM alembic_version` and run `alembic downgrade <target>` to reach the expected
   revision.
