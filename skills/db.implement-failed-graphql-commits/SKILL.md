---
name: db.implement-failed-graphql-commits
description: 'Use when implementing fixes after failed GraphQL or related commit-time checks.'
---

# Failed Graphql Commits

## Trigger

- Primary: "failed cmd runtimeerror mettascope build failed nim c bindings bindings"
- Variant: "failed cmd runtimeerror mettascope build failed nim c bindings"
- Variant: "failed args runtimeerror build failed nim c skipprojcfg on b"
- Variant: "failed graphql no commits between main"
- Variant: "failed move backoff"

## Workflow

- Clarify expected behavior and constraints from existing context.
- Implement incrementally with minimal surface-area changes.
- Add or update tests that lock in the new behavior.
- Verify lint and tests before submission.
