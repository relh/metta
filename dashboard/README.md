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
- Renders KPI/diagnostics/episodes and can run AI analysis
- Includes `Roles` tab backed by `/dashboard/v1/policies/versions/{id}/role-percentiles`

### Run

```bash
cd dashboard/frontend
pnpm install
pnpm dev
```

### Environment

- `NEXT_PUBLIC_DASHBOARD_API_BASE_URL` (default `http://127.0.0.1:8010`)

## Dev flow

1. Start backend on `:8010`
2. Start frontend on `:5174`
3. Open `http://127.0.0.1:5174`

## Production deployment

- Frontend workflow: `.github/workflows/build-dashboard-image.yml`
  - Deploys Helm chart: `devops/charts/dashboard/`
  - Host: `https://policy-dashboard.softmax-research.net`
- Backend workflow: `.github/workflows/deploy-dashboard-backend.yml`
  - Deploys Helm chart: `devops/charts/dashboard-backend/`
  - Host: `https://api.policy-dashboard.softmax-research.net`

Backend requires `STATS_DB_READ_ONLY_URI`, provisioned as the `dashboard-backend-env` k8s secret from Terraform. The
source URI currently comes from `observatory/readonly-db-uri` in AWS Secrets Manager (temporarily managed outside
Terraform per `devops/tf/observatory/readonly_db.tf`), and runtime startup checks enforce non-writer + read-replica
invariants.
