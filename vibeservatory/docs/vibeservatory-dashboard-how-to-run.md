# Vibeservatory Dashboard: How To Run

This doc captures the current ways to run the Vibeservatory dashboard and related diagnose tooling in `metta`.

## 1) Full State Page (Standalone Dashboard)

Start backend:

```bash
export STATS_DB_READ_ONLY_URI='postgresql://postgres:password@127.0.0.1:5432/metta'
export DASHBOARD_DEV_AUTH_BYPASS=true
uv run python -m vibeservatory.backend.dashboard_backend.main
```

Start frontend:

```bash
cd dashboard/frontend
pnpm install
NEXT_PUBLIC_DASHBOARD_API_BASE_URL=http://127.0.0.1:8010 pnpm dev
```

Open:

- `http://127.0.0.1:5174`

## 2) Embedded In Observatory

```bash
OBSERVATORY_POLICY_DASHBOARD_URL=http://127.0.0.1:5174 metta dev softmax-com --backend local
```

Then open Observatory at `/observatory/policy-dashboard?policyVersionId=<uuid>`.

## 3) Offline HTML Artifact (Skill Generator)

Tournament mode:

```bash
uv run python skills/cg.policy-dashboard/generate.py --policy <name:vN> --season beta-cvc --limit 100
```

Local JSON mode:

```bash
uv run python skills/cg.policy-dashboard/generate.py --local-results <dir> --policy-name <name>
```

## 4) Generate Diagnose Artifacts

```bash
uv run cogames diagnose "metta://policy/<name>:v<version>" --mission-set cogsguard_evals
```
