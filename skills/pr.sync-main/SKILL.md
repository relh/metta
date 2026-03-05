---
name: pr.sync-main
description:
  'Sync the branch with origin/main by fetching and merging or rebasing, then resolve conflicts and summarize changes.
  Use when asked to sync with main.'
---

# Sync Main

## Workflow

- Summarize current `git status` and confirm whether a commit is needed.
- If already in conflict, skip merge/rebase and resolve conflicts directly.
- Fetch origin and merge or rebase from origin/main.
- Resolve conflicts, preserving branch intent and upstream structure.
- Summarize what changed and note that pushing is left to the user.

## Common Request Language

- "sync/rebase/merge this branch with main"
- "resolve merge conflicts while keeping branch intent"
- "fix stale merge/open state before continuing work"
