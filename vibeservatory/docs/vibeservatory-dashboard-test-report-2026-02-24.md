# Vibeservatory Dashboard Feature Test Report (No Anthropic Key)

Date: 2026-02-24  
Branch: `richard-statspage224`  
PR: https://github.com/Metta-AI/metta/pull/7962

## Scope

Validate Vibeservatory dashboard functionality end-to-end without providing any Anthropic API key.

Included:

- Vibeservatory backend state-page and diagnose backend tests
- Dashboard frontend unit tests and type-check
- Live API smoke checks (deployed API)
- Live UI smoke checks across all dashboard tabs (deployed dashboard frontend)

Excluded:

- Anthropic-backed analysis generation success path (no key intentionally provided)

Policy version used in smoke tests:

- `7e16ac5f-7fe6-4970-940c-acc2d6c29013`

## Commands Run

### Backend tests

```bash
uv run pytest tests/vibeservatory/backend/state_page/test_router.py tests/vibeservatory/backend/state_page/test_diagnostics.py tests/vibeservatory/backend/cogames_diagnose/test_router.py -q
uv run pytest tests/vibeservatory/backend/state_page/test_kpi_math.py tests/vibeservatory/backend/test_role_percentile_queries.py tests/vibeservatory/backend/test_auth.py -q
```

Result:

- `26 passed`
- `14 passed`

### Frontend tests

```bash
cd dashboard/frontend
pnpm test
pnpm type-check
```

Result:

- `vitest`: `1 file, 2 tests passed`
- `tsc --noEmit`: pass

### Live API smoke (no Anthropic key)

```bash
dashboard/scripts/live_api_smoke.sh 7e16ac5f-7fe6-4970-940c-acc2d6c29013
```

Result:

- `data endpoint`: pass
- `role-percentiles`: pass
- `diagnose runs`: warning (`runs=0`, expected when no local diagnose artifacts are present)
- `analysis`: warning (`500 Analysis unavailable: no Anthropic API key configured`, expected for this scope)

Reliability spot check:

- Repeated the API smoke 5 consecutive times.
- `data` and `role-percentiles` were stable (`PASS` each run).
- `analysis` consistently returned expected no-key warning.

### Live UI smoke (all sub-tabs)

```bash
DASHBOARD_URL=https://policy-dashboard.softmax-research.net \
dashboard/scripts/live_ui_smoke.sh 7e16ac5f-7fe6-4970-940c-acc2d6c29013
```

Final run result:

- `failures=0 warnings=0`
- Artifacts: `/tmp/vibeservatory-dashboard-ui-smoke-20260224-074718`

## Sub-Tab Results

From the successful UI smoke run:

- `overview`: PASS
- `episodes`: PASS
- `opponents`: PASS
- `health`: PASS
- `roles`: PASS
- `capabilities`: PASS
- `cogames_diagnose`: PASS
- `analysis`: PASS (tab/rendering path only; no Anthropic generation invoked)

## Notes

- Earlier smoke attempts showed intermittent loading timeouts while hitting deployed endpoints; reruns stabilized and
  completed cleanly.
- No code changes were required for dashboard behavior during this test pass.
