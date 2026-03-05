---
name: pr.sync-high-priority-bug-fix-branches
description: 'Use when syncing high-priority bug fix branches.'
---

# Sync High Priority Bug Fix Branches

## Trigger

- Primary: "syncing high priority bug fix branches"
- Variant: "syncing high priority bug fixes branches warning"
- Variant: "syncing refinery merge high priority bug fixes branches install"

## Workflow

- Check branch/divergence state against the target branch.
- Merge or rebase with conflict resolution focused on behavior correctness.
- Run focused verification on touched surfaces.
- Summarize any non-trivial conflict decisions.
