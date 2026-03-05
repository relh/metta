---
name: t.test-tests-pass
description: Verify that tests pass on main or the current branch, then report concrete pass/fail status.
---

# Test Tests Pass

## Trigger

- Primary: "Verify that tests pass on main or the current branch, then report concrete pass/fail status."
- Variant: "no go tests or go not applicable"
- Variant: "tests test cogsguard roles"
- Variant: "tests domain regicide"
- Variant: "summary info tests python run python tests"
- Variant: "tests running uv r"
- Variant: "tests rl test supervised scripted actions"

## Workflow

- Identify the exact behavior that needs validation.
- Run the smallest relevant test command first.
- If failures appear, isolate root cause before broad reruns.
- Report pass/fail status and any follow-up risks.
