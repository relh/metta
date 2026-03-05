---
name: db.fix-failing-ci
description: 'Use when fixing failing CI.'
---

# Fix Failing Ci

## Trigger

- Primary: "failing ci"
- Variant: "failing ci with real fixes including metta lint fix resolve"
- Variant: "fixing failing required checks meaningfully"
- Variant: "fixing why CI failing"
- Variant: "fixing why web replays matches failing cogsguard"

## Workflow

- Reproduce the issue in a focused way (failing test, lint error, traceback, or CI failure).
- Apply the smallest code or test change that resolves the issue.
- Verify with targeted checks first, then broader checks if needed.
- Summarize root cause and the concrete fix made.
