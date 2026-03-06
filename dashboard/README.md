# Dashboard Frontend

This directory contains the standalone dashboard frontend (`dashboard`) only.

Route ownership in this frontend:

- `/policy-dashboard` (policy dashboard)
- `/bardo` proxy (to top-level `bardo/` app in local dev and shared frontend deploy)
- `/pantheon` and `/pantheon/v0` proxy (to top-level `pantheon/` app in shared frontend deploy)
- `/diagnose` and `/diagnose/:runId` proxy (to top-level `diagnose/` app in shared frontend deploy)

Canonical Vibeservatory dashboard/backend documentation now lives in:

- `vibeservatory/README.md`
- `vibeservatory/docs/`
- `vibeservatory/scripts/`
