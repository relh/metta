---
name: relh.cb.branch-hygiene
description:
  'Audit the branch vs origin/main for unintended changes, redundant code, or missing tests. Use when asked for branch
  hygiene.'
---

# Branch Hygiene

## Workflow

- Confirm base branch (default origin/main) and any focus paths.
- Fetch origin if needed, then compute merge base: `base=$(git merge-base HEAD origin/main)`.
- Review `git diff --stat $base` and key diffs (limit to focus paths if provided).
- Call out unintended changes, redundant code, risky modifications, and missing tests.
- Provide cleanup recommendations and suggested follow-up checks.
