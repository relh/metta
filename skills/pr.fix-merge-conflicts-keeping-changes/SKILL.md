---
name: pr.fix-merge-conflicts-keeping-changes
description: Use when resolving merge conflicts and intentionally keeping specific upstream/downstream changes.
---

# Fix Merge Conflicts Keeping Changes

## Trigger

- Primary: "Use when resolving merge conflicts and intentionally keeping specific upstream/downstream changes."
- Variant: "merge conlicts first"
- Variant: "merge merge sync branch back to main branch m message"

## Workflow

- Reproduce the issue in a focused way (failing test, lint error, traceback, or CI failure).
- Apply the smallest code or test change that resolves the issue.
- Verify with targeted checks first, then broader checks if needed.
- Summarize root cause and the concrete fix made.
