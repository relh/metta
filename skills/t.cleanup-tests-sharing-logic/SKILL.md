---
name: t.cleanup-tests-sharing-logic
description: 'Use when cleaning up tests sharing logic.'
---

# Cleanup Tests Sharing Logic

## Trigger

- Primary: "tests by sharing logic"
- Variant: "tests from our branch"
- Variant: "tests to first create the checkpoint"

## Workflow

- Locate redundant code paths, dead branches, or unnecessary indirection.
- Simplify without changing behavior.
- Run lint and focused tests for touched areas.
- Document what was removed or simplified.
