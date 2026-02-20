# Observatory Backend

Backend API for https://observatory.softmax-research.net/

## Local Development

```bash
metta observatory --help
```

## Mock Team Tournament (Development)

Use `teams-mock` to exercise tournament stage progression without episode-runner latency.

1. Enable mock seasons:

```bash
export ENABLE_MOCK_TOURNAMENTS=true
```

2. Start the local stack:

```bash
metta observatory up
```

3. Open `teams-mock` in Observatory:

- Season page: `http://localhost:5173/tournament/teams-mock`
- Matches page: `http://localhost:5173/tournament/teams-mock/matches`

Notes:

- `teams-mock` writes real `Match` and `MatchPlayer` rows with synthetic scores.
- These matches have no backing job/episode artifacts.

### Starting a Fresh Mock Run

If a run is already in progress, roll the season to a new canonical version:

```bash
ENABLE_MOCK_TOURNAMENTS=true metta observatory tournament roll-season teams-mock
```

For team seasons, roll creates a clean version with only the entry pool pre-created (it does not copy intermediate stage
pools from the prior version).

To carry active entrants into the new version:

```bash
ENABLE_MOCK_TOURNAMENTS=true metta observatory tournament roll-season teams-mock --migrate-players
```

Version behavior:

- `teams-mock` resolves to the current canonical version.
- Older runs remain available as `teams-mock:vN` (example: `teams-mock:v1`).
- Version list endpoint: `/tournament/seasons/teams-mock/versions`.
- Submissions are only allowed to canonical (`teams-mock`), not `teams-mock:vN`.

## Production

Deployed to EKS via Helm chart at `devops/charts/observatory-backend/`.

- Host: `api.observatory.softmax-research.net`
- Image built by `.github/workflows/deploy-observatory.yml`
- Database: RDS Postgres (credentials in k8s secret `observatory-backend-env`)

## Observability

Tournament job tracing is opt-in via `OTEL_TRACES_ENABLED=true`
