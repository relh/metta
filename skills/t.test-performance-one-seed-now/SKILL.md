---
name: t.test-performance-one-seed-now
description: 'Use when testing performance one seed.'
---

# Test Performance One Seed Now

## Trigger

- Primary: "performance for just one seed for now"
- Variant: "v22 performance one more time completed exit code summary task"
- Variant: "testing performance run packages cogames scripts evaluation"

## Workflow

- Run a single-seed perf smoke with fixed config and fixed environment settings.
- Keep the command comparable to baseline runs so the delta is interpretable.
- Treat single-seed output as provisional; if near threshold, run additional seeds before final claims.
- Report the provisional delta, confidence level, and whether broader perf validation is required.
