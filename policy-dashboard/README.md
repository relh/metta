# Policy Dashboard Surface

`policy-dashboard` is one of the six Vibeservatory surfaces (embedded by Observatory).
This folder is surface documentation only; the canonical frontend code package is `dashboard/`.

## Canonical Host Path

- `https://vibeservatory.softmax-research.net/policy-dashboard`

## Frontend

- Canonical frontend package: `dashboard/`.
- Main route entrypoint: `dashboard/src/app/page.tsx`.

## Backend (Vibeservatory)

- Canonical API route: `/dashboard/v1/policies/versions/default/data`
- Backend implementation: `vibeservatory/backend/dashboard_backend/state_page/router.py`

## Deployment Model

- No standalone deploy/chart/workflow.
- Served via the shared Vibeservatory frontend deployment.
- `softmax.com/observatory` is a separate service that embeds this surface via iframe.
