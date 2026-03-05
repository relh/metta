---
name: t.test-all-policies
description: 'Use when running tests across all policies for regression coverage.'
---

# Test All Policies

## Trigger

- Primary: "all policies"
- Variant: "all co gas merges landed cleanly on main p1 hooked"
- Variant: "all the key changes by reviewing the modified sections"
- Variant: "all relh branches to see if any are failing"
- Variant: "all slot indices have corresponding policies for idx in range"

## Workflow

- Identify the exact behavior that needs validation.
- Run the smallest relevant test command first.
- If failures appear, isolate root cause before broad reruns.
- Report pass/fail status and any follow-up risks.
