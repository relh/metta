---
name: cb.fix-miner-cargo-capacity
description: 'Use when fixing miner cargo-capacity logic or related behavior.'
---

# Miner Cargo Capacity

## Trigger

- Primary: "cg 8ji0 miner bootstraps economy aligner stuck in emergencymine 1m"
- Variant: "cg 8ji0 miner bootstraps economy aligner stuck in emergencymine"
- Variant: "miner cargo capacity"
- Variant: "miner deposit threshold e959ff8 fix increase miner deposit threshold from"

## Workflow

- Reproduce the issue in a focused way (failing test, lint error, traceback, or CI failure).
- Apply the smallest code or test change that resolves the issue.
- Verify with targeted checks first, then broader checks if needed.
- Summarize root cause and the concrete fix made.
