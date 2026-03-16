# Vibeservatory Surfaces

Canonical docs for the Vibeservatory surface backend live here.

Related code paths:

- Backend: `vibeservatory/backend/dashboard_backend/`
- Standalone frontend: `dashboard/`
- Standalone surface frontends: `bardo/`, `pantheon/`, `diagnose/`
- Surface folders: `policy-dashboard/` (docs alias for dashboard route), `pantheon/`, `diagnose/`, `chatprop/`,
  `trainboard/`, `bardo/`
- Dev/smoke scripts: `vibeservatory/scripts/`
- Additional docs: `vibeservatory/docs/`
- Surface contract: `vibeservatory/iframe_surfaces.json`

## Service Boundaries

Canonical naming and ownership:

- `Vibeservatory` is the service that hosts these six surfaces and their backend endpoints.
- `Observatory` (`softmax.com/observatory`) is a separate service/deployment that embeds Vibeservatory surfaces in
  iframes.
- These services run in parallel; Observatory is not the host of the surface apps.

## Surface Ownership

The six embedded surfaces are peers. Each surface owns:

- a frontend host path
- a backend route namespace on the shared Vibeservatory backend
- a backend router module inside `vibeservatory/backend/dashboard_backend/`

Current ownership map:

- `policy-dashboard`: frontend `/policy-dashboard`, backend namespace `/policy-dashboard/v1/...`, backend module
  `policy_dashboard/router.py`
- `bardo`: frontend `/bardo`, backend namespace `/bardo/v1/...`, backend module `bardo/router.py`
- `pantheon`: frontend `/pantheon`, backend namespace `/pantheon/v1/...`, backend module `pantheon/router.py`
- `diagnose`: frontend `/diagnose`, backend namespace `/diagnose/v1/...`, backend module `diagnose/router.py`
- `chatprop`: frontend `/chatprop`, backend namespace `/chatprop/...`, backend module `chatprop/router.py`
- `trainboard`: frontend `/train-board`, backend namespace `/train-board/...`, backend module `trainboard/router.py`

## Backend

What it does:

- Mounts the six peer surface backends (policy-dashboard, bardo, pantheon, diagnose, chatprop, trainboard)
- Keeps route ownership per-surface rather than treating `policy-dashboard`, `pantheon`, and `diagnose` as generic
  dashboard subfeatures
- Also mounts shared role-stats endpoints from `vibeservatory/backend/dashboard_backend/role_stats/router.py`
- Exposes internal docs at `http://127.0.0.1:8010/internal/docs`
- Hides public docs (`/docs` is disabled)
- Forces read-only DB usage for the read-mostly surface queries in this process
- Blocks write SQL statements via a statement guard

Run:

```bash
uv run python -m vibeservatory.backend.dashboard_backend.main
```

Environment:

- `STATS_DB_READ_ONLY_URI` (required runtime URI; aligned with `observatory/readonly-db-uri`)
- `DASHBOARD_HOST` (default `127.0.0.1`)
- `DASHBOARD_PORT` (default `8010`)
- `DASHBOARD_CORS_ORIGINS` (default `*`)
- `DASHBOARD_AUTH_SECRET` (optional)
- `DASHBOARD_LOGIN_SERVICE_URL` (default `https://softmax.com`)
- `DASHBOARD_DEV_AUTH_BYPASS` (default `true`; bypass applies only for localhost requests)
- `DASHBOARD_PANTHEON_ROOT` (optional; defaults to `outputs/pantheon` when repo root is discoverable)
- `ANTHROPIC_API_KEY` (optional, for analysis endpoint)

## Standalone Frontend

What it does:

- Standalone dashboard UI that fetches from the Vibeservatory backend directly
- Loads dashboard data by policy-version UUID
- Tabs in the UI:
  - `Overview`: policy metadata, KPI snapshot, diagnostics, quality gates, rollout actions, and AI analysis
  - `Performance`: per-episode filters/export, replay links, health KPIs, failure/crash summaries, and tag inventory
  - `Coordination`: teammate-pairing diagnosis, teammate/composition slice tables, and role-percentile parses
  - `Capabilities`: unified capability tree plus diagnose run selector, stage gates, probes, symptoms, and prescriptions
  - `Pantheon`: hall-of-fame/lame/same motif stories from replay-derived behavior snippets (v0 includes seeded examples)

Run:

```bash
cd dashboard
pnpm install
pnpm dev
```

Environment:

- `NEXT_PUBLIC_DASHBOARD_API_BASE_URL` (default `http://127.0.0.1:8010`)

## Standalone Bardo Frontend

What it does:

- Standalone bardo UI served from top-level `bardo/`
- Uses Vibeservatory backend route `/bardo/v1/world-state`

Run:

```bash
cd bardo
pnpm install
pnpm dev
```

Open: `http://127.0.0.1:5175/bardo`

Environment:

- `BARDO_BASE_PATH` (default `/bardo`)
- `NEXT_PUBLIC_BARDO_BASE_PATH` (default `/bardo`; should match `BARDO_BASE_PATH`)
- `BARDO_WORLD_STATE_URL` (default `http://127.0.0.1:8010/bardo/v1/world-state`)

## Local Development

Production uses a private RDS read replica (`main-pg-ro...`) that is not directly reachable from laptops in many
environments (private subnets + security group ingress from EKS only).

Quickstart (backend + frontends together, live read-only DB via EKS tunnel):

```bash
vibeservatory/scripts/dev_local.sh
```

This starts:

- Vibeservatory backend at `http://127.0.0.1:8010`
- Standalone dashboard frontend at `http://127.0.0.1:5174`
- Standalone bardo frontend at `http://127.0.0.1:5175/bardo`
- Standalone pantheon frontend at `http://127.0.0.1:5176/pantheon`
- Standalone diagnose frontend at `http://127.0.0.1:5177/diagnose`
- Dashboard API base set to local backend (`NEXT_PUBLIC_DASHBOARD_API_BASE_URL=http://127.0.0.1:8010`)

Manual Alternative A: local snapshot

1. Start local Postgres:

```bash
metta dev postgres up -d
```

2. Seed local DB from production:

```bash
bash app_backend/scripts/seed_local_db.sh
```

3. Start backend (read-only URI pointed at local Postgres):

```bash
export STATS_DB_READ_ONLY_URI='postgresql://postgres:password@127.0.0.1:5432/metta'
export DASHBOARD_DEV_AUTH_BYPASS=true
export DASHBOARD_HOST=127.0.0.1
export DASHBOARD_PORT=8010
uv run python -m vibeservatory.backend.dashboard_backend.main
```

4. Start frontend:

```bash
cd dashboard
pnpm install
NEXT_PUBLIC_DASHBOARD_API_BASE_URL=http://127.0.0.1:8010 pnpm dev
```

5. Open:

- Frontend: `http://127.0.0.1:5174`
- Backend docs: `http://127.0.0.1:8010/internal/docs`

Manual Alternative B: live production read-replica via EKS tunnel

Prereqs:

- AWS auth for account `751442549699`
- `kubectl` access to cluster `main` / namespace `observatory`

1. Read the read-only URI from Secrets Manager:

```bash
export RO_URI="$(aws secretsmanager get-secret-value --secret-id observatory/readonly-db-uri --query SecretString --output text)"
```

2. Start in-cluster TCP proxy pod:

```bash
export RO_HOST="$(python - <<'PY' "$RO_URI"
import sys
from urllib.parse import urlparse
print(urlparse(sys.argv[1]).hostname)
PY
)"
kubectl -n observatory run ro-db-proxy --image=alpine/socat --restart=Never --command -- sh -c "socat TCP-LISTEN:5432,fork,reuseaddr TCP:${RO_HOST}:5432"
kubectl -n observatory wait --for=condition=Ready pod/ro-db-proxy --timeout=120s
```

3. Port-forward locally:

```bash
kubectl -n observatory port-forward pod/ro-db-proxy 15432:5432
```

4. Rewrite URI to local forwarded port and run backend:

```bash
export STATS_DB_READ_ONLY_URI="$(python - <<'PY' "$RO_URI"
import sys
from urllib.parse import urlparse, urlunparse
u = urlparse(sys.argv[1])
print(urlunparse(u._replace(netloc=f"{u.username}:{u.password}@127.0.0.1:15432")))
PY
)"
export DASHBOARD_DEV_AUTH_BYPASS=true
uv run python -m vibeservatory.backend.dashboard_backend.main
```

5. Start frontend as in Manual Alternative A.

6. Cleanup:

```bash
kubectl -n observatory delete pod ro-db-proxy --ignore-not-found=true
```

## Production Deployment

- Frontend workflow: `.github/workflows/build-vibeservatory-image.yml`
  - Dockerfile: `devops/docker/Dockerfile.vibeservatory-frontend`
  - Deploys Helm chart: `devops/charts/vibeservatory-frontend/`
  - Host: `https://vibeservatory.softmax-research.net` (`/policy-dashboard`, `/bardo`, `/pantheon`, `/diagnose`)
  - Runtime model: one frontend deployment/container serving all four routes (dashboard + bardo + pantheon + diagnose)
- Backend workflow: `.github/workflows/deploy-vibeservatory.yml`
  - Deploys Helm chart: `devops/charts/vibeservatory/`
  - Host: `https://api.vibeservatory.softmax-research.net`

Backend requires `STATS_DB_READ_ONLY_URI`, provisioned as the `vibeservatory-env` k8s secret from Terraform. The source
URI currently comes from `observatory/readonly-db-uri` in AWS Secrets Manager (temporarily managed outside Terraform per
`devops/tf/observatory/readonly_db.tf`), and runtime startup checks enforce non-writer + read-replica invariants.

## Analysis Key Strategy (BYO)

- The Vibeservatory backend supports two key sources for AI analysis:
  - Request-scoped header: `X-Anthropic-Api-Key` (preferred for BYO usage)
  - Backend env var: `ANTHROPIC_API_KEY` (optional fallback)
- We do not require a shared deployed key. Users can bring their own key per request from the Overview analysis section.
- For local/self-hosted backend usage, exporting `ANTHROPIC_API_KEY` still works.

## Live Smoke Scripts

Fast API-level smoke:

```bash
vibeservatory/scripts/live_api_smoke.sh 7e16ac5f-7fe6-4970-940c-acc2d6c29013
```

Optional env:

- `DASHBOARD_API_BASE_URL` (defaults to deployed API)
- `DASHBOARD_AUTH_TOKEN` or `OBSERVATORY_AUTH_TOKEN` (if not using `~/.metta/config.yaml`)
- `DASHBOARD_ANTHROPIC_API_KEY` (optional BYO key for analysis check)

Full UI smoke with captured auth storage state:

```bash
vibeservatory/scripts/capture_observatory_storage_state.sh
vibeservatory/scripts/live_ui_smoke.sh 7e16ac5f-7fe6-4970-940c-acc2d6c29013
```

Notes:

- `live_ui_smoke.sh` defaults to `https://vibeservatory.softmax-research.net/policy-dashboard` (standalone dashboard).
- Override `DASHBOARD_URL` if you explicitly want to smoke the Observatory embed route.
