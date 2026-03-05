---
name: pr.fix-conflicts-keep-additions
description: 'Use when fixing conflicts keep additions.'
---

# Fix Conflicts Keep Additions

## Trigger

- Primary: "conflicts keep your new additions"
- Variant: "conflicts with main"
- Variant: "conflicts keeping how main works"
- Variant: "conflicts if needed merge to main with ff only push"
- Variant: "conflicts for our relh hunger agent followup main branch please"
- Variant: "conflicts sensibly keeping main unless it s related to our"
- Variant: "conflicts by taking theirs"
- Variant: "conflicts whenever we merge main we see a big diff"
- Variant: "conflicts while keeping our sweep code"

## Workflow

- Enumerate conflicted files and classify each as feature logic, generated output, or infrastructure/config noise.
- Keep branch additions where they are the intended feature delta; otherwise prefer mainline to avoid accidental
  divergence.
- Re-run focused verification for every touched subsystem (tests/lint/build checks as applicable).
- Summarize per-file resolution rationale so reviewers can quickly validate merge correctness.
