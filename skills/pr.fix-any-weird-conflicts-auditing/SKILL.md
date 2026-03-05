---
name: pr.fix-any-weird-conflicts-auditing
description: 'Use when fixing unusual PR conflicts discovered during audit.'
---

# Any Weird Conflicts Auditing

## Trigger

- Primary: "any conflicts you will see we do have goblin sprites"
- Variant: "any github comments on the pr meaningfully with fixes that"
- Variant: "any pr comments on it push fixes if necessary"
- Variant: "any weird conflicts by auditing"

## Workflow

- Reproduce the issue in a focused way (failing test, lint error, traceback, or CI failure).
- Apply the smallest code or test change that resolves the issue.
- Verify with targeted checks first, then broader checks if needed.
- Summarize root cause and the concrete fix made.
