---
name: tr.implement-mode-cogames-agents-docs
description:
  Use when implementing or updating CoGames agent documentation for a specific topic (mechanics, architecture,
  leaderboard, role-distribution, or README scope).
---

# Implement Mode Cogames Agents Docs

## Trigger

- Primary: "Use when implementing or updating CoGames agent documentation for a specific topic (mechanics,
  architecture,"
- Variant: "mode agent src metta agent policies puffer default"
- Variant: "mode docs eval cogas vs wombo head to head"

## Workflow

- Clarify expected behavior and constraints from existing context.
- Implement incrementally with minimal surface-area changes.
- Add or update tests that lock in the new behavior.
- Verify lint and tests before submission.
