---
name: t.cleanup-test-stopwatch-tests
description: 'Use when cleaning up test stopwatch tests.'
---

# Cleanup Test Stopwatch Tests

## Trigger

- Primary: "test stopwatch tests"
- Variant: "test you added asserting theyre exactly what they are"
- Variant: "test that checks if this is default"
- Variant: "test we were failing"

## Workflow

- Locate redundant code paths, dead branches, or unnecessary indirection.
- Simplify without changing behavior.
- Run lint and focused tests for touched areas.
- Document what was removed or simplified.
