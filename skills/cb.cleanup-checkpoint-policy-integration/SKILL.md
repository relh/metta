---
name: cb.cleanup-checkpoint-policy-integration
description: 'Use when cleaning up checkpoint-policy integration code and references.'
---

# Checkpoint Policy Integration

## Trigger

- Primary: "checkpoint io to checkpointpolicy policy spec dirs open relh wants"
- Variant: "checkpoint io to checkpointpolicy policy spec dirs open relh"
- Variant: "checkpoint latest branch"
- Variant: "checkpoint policy integration v1 branch"

## Workflow

- Locate redundant code paths, dead branches, or unnecessary indirection.
- Simplify without changing behavior.
- Run lint and focused tests for touched areas.
- Document what was removed or simplified.
