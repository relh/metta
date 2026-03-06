# Pantheon Surface

`pantheon` is one of the six Vibeservatory surfaces (embedded by Observatory).

## Canonical Host Path

- `https://vibeservatory.softmax-research.net/pantheon/v0`

## Frontend

- Canonical route implementation lives in this folder (`pantheon/`).
- Route entrypoints:
  - `pantheon/src/app/page.tsx`
  - `pantheon/src/app/v0/page.tsx`

## Backend (Vibeservatory)

- Canonical API route: `/dashboard/v1/pantheon/stories`
- Backend implementation: `vibeservatory/backend/dashboard_backend/pantheon/router.py`

## Deployment Model

- No standalone deploy/chart/workflow.
- Built into the shared Vibeservatory frontend image and proxied by `dashboard`.
- `softmax.com/observatory` is a separate service that embeds this surface via iframe.
