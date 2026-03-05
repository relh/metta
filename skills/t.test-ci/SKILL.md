---
name: t.test-ci
description: 'Use when testing CI.'
---

# Test Ci

## Trigger

- Primary: "ci again"
- Variant: "ci for any more failing issues on any branch of"
- Variant: "ci checks on all of those prs to see what"
- Variant: "ci etc for our branch to make sure it s"
- Variant: "ci failures for all the prs that have failing ci"
- Variant: "if ci is fixed now"
- Variant: "ci again to make sure things are sensibly resolved"
- Variant: "ci once more if you can"

## Workflow

- Identify the exact behavior that needs validation.
- Run the smallest relevant test command first.
- If failures appear, isolate root cause before broad reruns.
- Report pass/fail status and any follow-up risks.
