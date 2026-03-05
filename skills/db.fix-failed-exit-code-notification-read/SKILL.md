---
name: db.fix-failed-exit-code-notification-read
description: 'Use when fixing failed exit code notification read.'
---

# Fix Failed Exit Code Notification Read

## Trigger

- Primary: "failed with exit code summary task notification read the"
- Variant: "failed to fetch replay for episode s s episode id"
- Variant: "failed to parse assignment tags for agent index resolution return"

## Workflow

- Reproduce the issue in a focused way (failing test, lint error, traceback, or CI failure).
- Apply the smallest code or test change that resolves the issue.
- Verify with targeted checks first, then broader checks if needed.
- Summarize root cause and the concrete fix made.
