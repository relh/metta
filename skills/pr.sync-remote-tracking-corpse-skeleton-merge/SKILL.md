---
name: pr.sync-remote-tracking-corpse-skeleton-merge
description: 'Use when syncing remote tracking corpse skeleton merge.'
---

# Sync Remote Tracking Corpse Skeleton Merge

## Trigger

- Primary: "remote tracking branch origin main 5a2077d corpse skeleton 72d7990 merge"
- Variant: "remote tracking branch origin main into richard smart errors 68cba19d42"
- Variant: "syncing remote think rename merged"

## Workflow

- Inspect stack/branch topology first (including dependent branches) before choosing merge vs rebase.
- Resolve conflicts with clear policy: preserve branch intent for owned feature logic, prefer main for unrelated infra
  churn.
- Verify conflict-heavy files with targeted tests/lint in touched packages before pushing.
- Summarize non-trivial resolutions and any follow-up restack steps needed.
