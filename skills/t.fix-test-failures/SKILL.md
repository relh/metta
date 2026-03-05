---
name: t.fix-test-failures
description: 'Use when fixing failing tests uncovered in local or CI runs.'
---

# Test Failures

## Trigger

- Primary: "update test cogas role distribution tests to match num agents"
- Variant: "test add modules to fakepolicy for reset consistent dropout compat"
- Variant: "update test assertions for plankyagentsmultipolicy nlankyagentsmultipolicy"
- Variant: "test update emergencyminegoal guardrail test to match glanky v11 thresholds"
- Variant: "test environment issue"
- Variant: "test failures"
- Variant: "test needs at least tasks to properly verify that progress"
- Variant: "test to match how we re doing things now"
- Variant: "test run tool ci flake origin akshay fix test run"
- Variant: "test should trigger the actual code path that uploads for"

## Workflow

- Reproduce the issue in a focused way (failing test, lint error, traceback, or CI failure).
- Apply the smallest code or test change that resolves the issue.
- Verify with targeted checks first, then broader checks if needed.
- Summarize root cause and the concrete fix made.
