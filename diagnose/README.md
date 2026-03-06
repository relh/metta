# Diagnose Surface

`diagnose` is one of the six Vibeservatory surfaces (embedded by Observatory).

## Canonical Host Path

- `https://vibeservatory.softmax-research.net/diagnose`

## Frontend

- Canonical route implementation lives in this folder (`diagnose/`).
- Route entrypoints:
  - `diagnose/src/app/page.tsx`
  - `diagnose/src/app/[runId]/page.tsx`

## Backend (Vibeservatory)

- Canonical API route: `/dashboard/v1/cogames-diagnose/runs`
- Backend implementation: `vibeservatory/backend/dashboard_backend/cogames_diagnose/router.py`

## Deployment Model

- No standalone deploy/chart/workflow.
- Built into the shared Vibeservatory frontend image and proxied by `dashboard`.
- `softmax.com/observatory` is a separate service that embeds this surface via iframe.
