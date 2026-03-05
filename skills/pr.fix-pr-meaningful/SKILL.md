---
name: pr.fix-pr-meaningful
description: 'Use when fixing PR issues with behavior-preserving, meaningful changes.'
---

# Pr Meaningful

## Trigger

- Primary: "pr comment i think we need to bump compat version"
- Variant: "pr comment about bumping compat version"
- Variant: "pr lint failures richard statsuiobs"
- Variant: "pr comment if it s meaningful"
- Variant: "pr merge conflicts richard cogsaligned"
- Variant: "pr python test failures richard bestperf"
- Variant: "pr comments on rename planky to nlanky branch"
- Variant: "pr review comments we have on github"

## Workflow

- Reproduce the issue in a focused way (failing test, lint error, traceback, or CI failure).
- Apply the smallest code or test change that resolves the issue.
- Verify with targeted checks first, then broader checks if needed.
- Summarize root cause and the concrete fix made.
