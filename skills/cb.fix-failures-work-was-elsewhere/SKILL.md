---
name: cb.fix-failures-work-was-elsewhere
description: 'Use when fixing failures whose root cause is outside the initially suspected area.'
---

# Failures Work Was Elsewhere

## Trigger

- Primary: "failures no molecule attached hooked bead still triggers autonomous work"
- Variant: "failures no molecule attached hooked bead still triggers"
- Variant: "failures p2 hooked owner mayor assignee tribal village crew bugfixer"
- Variant: "failures this work was completed elsewhere"

## Workflow

- Reproduce the issue in a focused way (failing test, lint error, traceback, or CI failure).
- Apply the smallest code or test change that resolves the issue.
- Verify with targeted checks first, then broader checks if needed.
- Summarize root cause and the concrete fix made.
