---
name: relh.pr.merge-conflicts
description:
  'Resolve merge conflicts after syncing with main and explain non-trivial resolutions. Use when asked to resolve
  conflicts.'
---

# Merge Conflicts

## Workflow

- Summarize current conflict state from `git status`.
- Inspect conflict markers and resolve by preserving upstream structure while keeping branch intent.
- Call out any non-trivial choices and why they were made.
- Stage resolved files and report remaining conflicts (if any).
- If requested, run targeted tests or provide verification commands.
