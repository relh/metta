---
name: t.implement-mode-tests-domain
description:
  Use when implementing or updating tests for specific domain suites (for example production, rally, regicide, upgrades,
  or university tech domains).
---

# Implement Mode Tests Domain

## Trigger

- Primary: "Use when implementing or updating tests for specific domain suites (for example production, rally, regicide,
  upgrades,"
- Variant: "mode app backend tests job runner test dispatcher artifact uris"
- Variant: "mode app backend tests job runner test dispatcher artifact"
- Variant: "mode cogames agents tests test cogas"
- Variant: "mode common tests tool test recipe type hints failures"
- Variant: "mode internal cmd role boot test"
- Variant: "mode recipes tests test arena"

## Workflow

- Clarify expected behavior and constraints from existing context.
- Implement incrementally with minimal surface-area changes.
- Add or update tests that lock in the new behavior.
- Verify lint and tests before submission.
