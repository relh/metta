---
name: t.fix-run-pytest-packages-mettagrid-tests-test-weighted-territory
description: 'Use when fixing run pytest packages mettagrid tests test weighted territory.'
---

# Fix Run Pytest Packages Mettagrid Tests Test Weighted Territory

## Trigger

- Primary: "fixing run pytest packages mettagrid tests test weighted territory"

## Workflow

- Run the exact failing mettagrid test first (weighted territory) and capture deterministic repro details.
- Trace root cause to engine/test-contract mismatch; do not mask failures by weakening assertions.
- Apply the minimal fix and add a regression that locks the intended territory-weight behavior.
- Re-run the failing test and nearby mettagrid territory/AOE tests to confirm no local regressions.
