---
name: pr.cleanup-conflict-resolution
description: 'Use when cleaning up conflict resolution.'
---

# Cleanup Conflict Resolution

## Trigger

- Primary: "cleaning up conflict resolution"

## Workflow

- Review past conflict-resolution commits and identify repeated/manual conflict artifacts.
- Remove stale conflict scaffolding while preserving intended branch behavior.
- Re-run focused verification on files repeatedly involved in merges.
- Document what was cleaned and how it reduces future merge churn.
