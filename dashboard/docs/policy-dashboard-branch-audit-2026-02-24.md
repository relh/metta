# Policy Dashboard Branch + Doc Audit (2026-02-24)

Branch: `richard-statspage224`  
Base: `origin/main`  
PR: https://github.com/Metta-AI/metta/pull/7962

## 1) Branch Hygiene Audit

Merge-base diff vs `origin/main`:

- `dashboard/docs/policy-dashboard-how-to-run.md`
- `dashboard/docs/policy-dashboard-test-report-2026-02-24.md`
- `dashboard/scripts/live_ui_smoke.sh`
- `dashboard/scripts/capture_observatory_storage_state.sh`
- `dashboard/README.md`

Scope assessment:

- The branch remains focused on dashboard documentation, verification, and smoke-test usability.
- No unrelated runtime or product logic changes were introduced.
- Refactor changes are limited to smoke-script defaults + docs alignment.

## 2) Doc Audit

Checked docs for command accuracy and consistency with code:

- Runbook commands align with:
  - `dashboard/backend/dashboard_backend/main.py`
  - `dashboard/frontend/package.json`
  - `skills/cg.policy-dashboard/generate.py --help`
  - `uv run cogames diagnose --help`
- Test report matches executed commands and observed outcomes.
- `dashboard/README.md` now explicitly documents standalone dashboard smoke default and embed override.

## 3) Cool/Cleanup Refactor Applied

Problem found:

- `dashboard/scripts/live_ui_smoke.sh` defaulted to Observatory embed URL, while selector checks were designed for
  standalone dashboard content.
- This caused false-negative tab failures in some runs.

Refactor performed:

- `dashboard/scripts/live_ui_smoke.sh`
  - default `DASHBOARD_URL` changed to `https://policy-dashboard.softmax-research.net`
- `dashboard/scripts/capture_observatory_storage_state.sh`
  - default capture URL changed to `https://policy-dashboard.softmax-research.net`
- `dashboard/README.md`
  - updated notes to reflect standalone default and embed override behavior

Why safe:

- Change only affects default script targets; users can still override via `DASHBOARD_URL`.
- No backend/frontend app behavior changed.

## 4) Non-Pass Outcomes and Investigation Plans

### A) Earlier UI smoke failures (all tabs timed out)

Observed:

- Tabs initially failed waiting for selectors while page showed loading state.

Likely cause:

- URL/default-mode mismatch (embed route vs standalone selectors) and/or delayed authenticated load path.

Improvement:

- Implemented default-target refactor above.
- Verified full pass after refactor:
  - `failures=0 warnings=0` in final UI smoke run.

Follow-up investigation:

1. Add explicit `--mode standalone|embed` behavior to `live_ui_smoke.sh` with selector sets per mode.
2. Persist HAR on failures for all tabs to make mode/auth diagnosis immediate.

### B) Intermittent `503 Login service unreachable: ReadTimeout` in early API smoke runs

Observed:

- Some earlier runs returned transient auth-validation timeouts from deployed API paths.
- Later repeated runs were stable.

Follow-up investigation:

1. Add latency/timeout telemetry around `validate_token_via_login_service` in dashboard auth.
2. Track timeout rate by endpoint (`/data`, `/role-percentiles`, `/analysis`) in live smoke history.
3. Consider retry/backoff strategy for token validation transport errors if failure rate is non-trivial.

### C) `diagnose runs` warning (`runs=0`)

Observed:

- API smoke reports no diagnose artifacts in that environment.

Interpretation:

- Not a functional failure for dashboard rendering; indicates absent diagnose artifact inventory.

Follow-up investigation:

1. Validate deployed `DASHBOARD_COGAMES_DIAGNOSE_ROOT` configuration.
2. Optionally add a synthetic/sample run in non-prod for dashboard smoke coverage of diagnose listing.

### D) Analysis endpoint warning without Anthropic key

Observed:

- `analysis` returns expected no-key error in no-key scope.

Interpretation:

- Expected for this test scope.

Follow-up investigation:

1. Keep treating this as WARN in no-key smoke mode.
2. Add a separate optional keyed smoke profile for teams that want full analysis endpoint verification.
