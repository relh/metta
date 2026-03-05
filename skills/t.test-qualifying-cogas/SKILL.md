---
name: t.test-qualifying-cogas
description: 'Use when testing qualifying cogas.'
---

# Test Qualifying Cogas

## Trigger

- Primary: "v11 qualifying cogas test v10 qualifying cogas test v9 qualifying"
- Variant: "v11 qualifying cogas test v10 qualifying cogas test v9"
- Variant: "v11 qualifying completed failed pending cogas test v10 qualifying complete"
- Variant: "v11 qualifying retired matches cogas test v10"

## Workflow

- Identify the exact behavior that needs validation.
- Run the smallest relevant test command first.
- If failures appear, isolate root cause before broad reruns.
- Report pass/fail status and any follow-up risks.
