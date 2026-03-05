---
name: pr.sync-merge
description: Use when syncing and merging one branch into another with conflict resolution and post-merge verification.
---

# Sync Merge

## Trigger

- Primary: "syncing and merging one branch into another with conflict resolution and post-merge verification"
- Variant: "syncing/merging branches where status or priority context matters (for example open/blocking branches)"
- Variant: "syncing merge state priority"
- Variant: "syncing csfb merge cocr state priority"
- Variant: "syncing 24x7 merge state priority"

## Workflow

- Check branch/divergence state against the target branch.
- Merge or rebase with conflict resolution focused on behavior correctness.
- Run focused verification on touched surfaces.
- Summarize any non-trivial conflict decisions.
