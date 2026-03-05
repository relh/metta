---
name: cb.fix-any-find
description: 'Use when fixing concrete issues discovered during a code audit.'
---

# Fix Any Find

## Trigger

- Primary: "any that you find in our stack"
- Variant: "any of the fixes that seem worth keeping"
- Variant: "any outdated information add missing feature documentation ensure consistenc"

## Workflow

- Reproduce the issue in a focused way (failing test, lint error, traceback, or CI failure).
- Apply the smallest code or test change that resolves the issue.
- Verify with targeted checks first, then broader checks if needed.
- Summarize root cause and the concrete fix made.
