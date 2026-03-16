# Policy Dashboard Surface

`policy-dashboard` is one of the six Vibeservatory surfaces (embedded by Observatory). This folder is surface
documentation only; the canonical frontend code package is `dashboard/`.

## Canonical Host Path

- `https://vibeservatory.softmax-research.net/policy-dashboard`

## Frontend

- Canonical frontend package: `dashboard/`.
- Main route entrypoint: `dashboard/src/app/page.tsx`.

## Backend (Vibeservatory)

- Canonical API route: `/policy-dashboard/v1/policies/versions/default/data`
- Backend implementation: `vibeservatory/backend/dashboard_backend/policy_dashboard/router.py`
- Ownership model: this surface owns its backend namespace as a peer to `bardo`, `pantheon`, `diagnose`, `chatprop`, and
  `trainboard`, rather than living under a generic shared dashboard route bucket.

## Deployment Model

- No standalone deploy/chart/workflow.
- Served via the shared Vibeservatory frontend deployment.
- `softmax.com/observatory` is a separate service that embeds this surface via iframe.
