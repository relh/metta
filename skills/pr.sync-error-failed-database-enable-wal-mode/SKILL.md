---
name: pr.sync-error-failed-database-enable-wal-mode
description: 'Use when syncing error failed database enable wal mode.'
---

# Sync Error Failed Database Enable Wal Mode

## Trigger

- Primary: "error failed to open database failed to enable wal mode"
- Variant: "origin main error exit code from github"
- Variant: "error fetching gt metta witness no issue found matching gt"
- Variant: "error resolving mt bgi no issue found matching mt bgi"

## Workflow

- Check branch/divergence state against the target branch.
- Merge or rebase with conflict resolution focused on behavior correctness.
- Run focused verification on touched surfaces.
- Summarize any non-trivial conflict decisions.
