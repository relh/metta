---
name: t.fix-any-curriculum-tests-may-failing
description: 'Use when fixing failing curriculum-related tests.'
---

# Fix Any Curriculum Tests May Failing

## Trigger

- Primary: "any curriculum tests that may may not be failing"
- Variant: "any broken tests"
- Variant: "any bugs found test with step scrimmages matching beta cvc"

## Workflow

- Reproduce the issue in a focused way (failing test, lint error, traceback, or CI failure).
- Apply the smallest code or test change that resolves the issue.
- Verify with targeted checks first, then broader checks if needed.
- Summarize root cause and the concrete fix made.
