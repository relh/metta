---
name: pr.fix-prs
description: 'Use when fixing PRs.'
---

# Fix Prs

## Trigger

- Primary: "fixing PRs"
- Variant: "fixing each PR"
- Variant: "fixing easy prs"
- Variant: "fixing error PR"
- Variant: "fixing full prs"

## Workflow

- Reproduce the issue in a focused way (failing test, lint error, traceback, or CI failure).
- Apply the smallest code or test change that resolves the issue.
- Verify with targeted checks first, then broader checks if needed.
- Summarize root cause and the concrete fix made.
