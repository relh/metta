---
name: cb.implement-dependencies-common
description: 'Use when implementing or consolidating shared dependency handling.'
---

# Dependencies Common

## Trigger

- Primary: "dependencies started installing build dependencies finished with status done"
- Variant: "dependencies started lines ctrl o to expand this is a"
- Variant: "implementing dependencies common"

## Workflow

- Clarify expected behavior and constraints from existing context.
- Implement incrementally with minimal surface-area changes.
- Add or update tests that lock in the new behavior.
- Verify lint and tests before submission.
