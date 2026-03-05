---
name: t.test-failure-emergencyminegoal
description: 'Use when testing or debugging failures related to EmergencyMineGoal behavior.'
---

# Failure Emergencyminegoal

## Trigger

- Primary: "if failure is due to agent collision temporary vs wall"
- Variant: "failure test cogas integration imports missing modules p2 hooked owner"
- Variant: "failure emergencyminegoal"
- Variant: "failure fish spawn only on water test fails p1 hooked"
- Variant: "failure overflowdefect in findnearestthingspatial p2 hooked owner tribal"
- Variant: "failure test policy server manager mock signature mismatch"
- Variant: "failure test default role counts expects miners gets"
- Variant: "failure ai scout behavior tests failing"
- Variant: "failure spatial index overflow in task hearts test p0 hooked"
- Variant: "failure that was already fixed in commit d3b061e"

## Workflow

- Identify the exact behavior that needs validation.
- Run the smallest relevant test command first.
- If failures appear, isolate root cause before broad reruns.
- Report pass/fail status and any follow-up risks.
