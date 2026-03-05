# Standalone Dashboard Package

This folder intentionally contains both dashboard backend and frontend code in one place.

## Layout

- `backend/`: FastAPI service for dashboard data/analysis
- `frontend/`: Next.js standalone dashboard web app

## Backend

### What it does

- Serves dashboard endpoints from `dashboard/backend/dashboard_backend/state_page/router.py`
- Also mounts role-stats endpoints from `metta.app_backend.routes.role_stats_routes`
- Exposes internal docs at `http://127.0.0.1:8010/internal/docs`
- Hides public docs (`/docs` is disabled)
- Forces read-only DB usage for all dashboard queries in this process
- Blocks write SQL statements via a statement guard

### Run

```bash
uv run python -m dashboard.backend.dashboard_backend.main
```

### Environment

- `STATS_DB_READ_ONLY_URI` (required runtime URI; aligned with `observatory/readonly-db-uri`)
- `DASHBOARD_HOST` (default `127.0.0.1`)
- `DASHBOARD_PORT` (default `8010`)
- `DASHBOARD_CORS_ORIGINS` (default `*`)
- `DASHBOARD_AUTH_SECRET` (optional)
- `DASHBOARD_LOGIN_SERVICE_URL` (default `https://softmax.com`)
- `DASHBOARD_DEV_AUTH_BYPASS` (default `true`; bypass applies only for localhost requests)
- `ANTHROPIC_API_KEY` (optional, for analysis endpoint)

## Frontend

### What it does

- Standalone dashboard UI that fetches from dashboard backend directly
- Loads dashboard data by policy-version UUID
- Tabs in the UI:
  - `Overview`: policy metadata, KPI snapshot, diagnostics, quality gates, rollout actions, and AI analysis
  - `Performance`: per-episode filters/export, replay links, health KPIs, failure/crash summaries, and tag inventory
  - `Coordination`: teammate-pairing diagnosis, teammate/composition slice tables, and role-percentile parses
  - `Capabilities`: unified capability tree plus diagnose run selector, stage gates, probes, symptoms, and prescriptions

### Run

```bash
cd dashboard/frontend
pnpm install
pnpm dev
```

### Environment

- `NEXT_PUBLIC_DASHBOARD_API_BASE_URL` (default `http://127.0.0.1:8010`)

## Local development

Production uses a private RDS read replica (`main-pg-ro...`) that is not directly reachable from laptops in many
environments (private subnets + security group ingress from EKS only).

Recommended local mode (one command):

### Quickstart (one command)

Run backend + frontend together against the production read-only DB via EKS tunnel:

```bash
dashboard/scripts/dev_local.sh
```

This starts:

- Dashboard backend at `http://127.0.0.1:8010`
- Dashboard frontend at `http://127.0.0.1:5174`
- Frontend API base set to local backend (`NEXT_PUBLIC_DASHBOARD_API_BASE_URL=http://127.0.0.1:8010`)

### Manual Alternative A: local snapshot

Best for day-to-day development. You run dashboard against local Postgres seeded from production.

1. Start local Postgres:

```bash
metta dev postgres up -d
```

2. Seed local DB from production (first run):

```bash
bash app_backend/scripts/seed_local_db.sh
```

Optional: reuse cached dump

```bash
bash app_backend/scripts/seed_local_db.sh --skip-download
```

3. Start dashboard backend (read-only URI pointed at local Postgres):

```bash
export STATS_DB_READ_ONLY_URI='postgresql://postgres:password@127.0.0.1:5432/metta'
export DASHBOARD_DEV_AUTH_BYPASS=true
export DASHBOARD_HOST=127.0.0.1
export DASHBOARD_PORT=8010
uv run python -m dashboard.backend.dashboard_backend.main
```

4. In another terminal, start dashboard frontend:

```bash
cd dashboard/frontend
pnpm install
NEXT_PUBLIC_DASHBOARD_API_BASE_URL=http://127.0.0.1:8010 pnpm dev
```

5. Open:

- Frontend: `http://127.0.0.1:5174`
- Backend docs: `http://127.0.0.1:8010/internal/docs`

### Manual Alternative B: live production read-replica via EKS tunnel

Use this only when you need live read-replica data locally.

Prereqs:

- AWS auth for account `751442549699`
- `kubectl` access to cluster `main` / namespace `observatory`

1. Read the read-only URI from AWS Secrets Manager:

```bash
export RO_URI="$(aws secretsmanager get-secret-value --secret-id observatory/readonly-db-uri --query SecretString --output text)"
```

2. Start an in-cluster TCP proxy pod to the read replica:

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

3. Port-forward the proxy to your machine (keep this terminal open):

```bash
kubectl -n observatory port-forward pod/ro-db-proxy 15432:5432
```

4. In another terminal, rewrite URI to local forwarded port and run backend:

```bash
export STATS_DB_READ_ONLY_URI="$(python - <<'PY' "$RO_URI"
import sys
from urllib.parse import urlparse, urlunparse
u = urlparse(sys.argv[1])
print(urlunparse(u._replace(netloc=f"{u.username}:{u.password}@127.0.0.1:15432")))
PY
)"
export DASHBOARD_DEV_AUTH_BYPASS=true
uv run python -m dashboard.backend.dashboard_backend.main
```

5. Start frontend the same as Mode A.

6. Cleanup when done:

```bash
kubectl -n observatory delete pod ro-db-proxy --ignore-not-found=true
```

## Production deployment

- Frontend workflow: `.github/workflows/build-vibeservatory-image.yml`
  - Deploys Helm chart: `devops/charts/dashboard/`
  - Host: `https://policy-dashboard.vibeservatory.softmax-research.net`
- Backend workflow: `.github/workflows/deploy-dashboard-backend.yml`
  - Deploys Helm chart: `devops/charts/dashboard-backend/`
  - Host: `https://api.policy-dashboard.vibeservatory.softmax-research.net`

Backend requires `STATS_DB_READ_ONLY_URI`, provisioned as the `dashboard-backend-env` k8s secret from Terraform. The
source URI currently comes from `observatory/readonly-db-uri` in AWS Secrets Manager (temporarily managed outside
Terraform per `devops/tf/observatory/readonly_db.tf`), and runtime startup checks enforce non-writer + read-replica
invariants.

## Analysis Key Strategy (BYO)

- The dashboard backend supports two key sources for AI Analysis:
  - Request-scoped header: `X-Anthropic-Api-Key` (preferred for BYO usage)
  - Backend env var: `ANTHROPIC_API_KEY` (optional fallback)
- We do not require a shared deployed key. Users can bring their own key per request from the Overview analysis section.
- For local/self-hosted backend usage, exporting `ANTHROPIC_API_KEY` still works.

## Live Smoke Scripts

- Fast API-level smoke:

```bash
dashboard/scripts/live_api_smoke.sh 7e16ac5f-7fe6-4970-940c-acc2d6c29013
```

Optional env:

- `DASHBOARD_API_BASE_URL` (defaults to deployed API)
- `DASHBOARD_AUTH_TOKEN` or `OBSERVATORY_AUTH_TOKEN` (if not using `~/.metta/config.yaml`)
- `DASHBOARD_ANTHROPIC_API_KEY` (optional BYO key for analysis check)

- Full UI smoke with captured auth storage state:

```bash
dashboard/scripts/capture_observatory_storage_state.sh
dashboard/scripts/live_ui_smoke.sh 7e16ac5f-7fe6-4970-940c-acc2d6c29013
```

Notes:

- `live_ui_smoke.sh` defaults to `https://policy-dashboard.vibeservatory.softmax-research.net` (standalone dashboard).
- Override `DASHBOARD_URL` if you explicitly want to smoke the Observatory embed route.
