---
name: cb.cleanup-targeted-surface
description: 'Use when cleaning up a targeted surface.'
---

# Cleanup Targeted Surface

## Trigger

- Primary: "cleaning up targeted surface"
- Variant: "cleaning up spawn"
- Variant: "cleaning up allow env"

## Workflow

- Locate redundant code paths, dead branches, or unnecessary indirection.
- Simplify without changing behavior.
- Run lint and focused tests for touched areas.
- Document what was removed or simplified.
