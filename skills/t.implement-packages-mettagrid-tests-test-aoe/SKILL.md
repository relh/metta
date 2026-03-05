---
name: t.implement-packages-mettagrid-tests-test-aoe
description: 'Use when implementing packages mettagrid tests test AOE.'
---

# Implement Packages Mettagrid Tests Test Aoe

## Trigger

- Primary: "implementing packages mettagrid tests test AOE"

## Workflow

- Specify the exact AOE contract under test (order, radius, inclusion/exclusion, and tick timing).
- Build deterministic test fixtures (seed/map/setup) so failures are reproducible and debuggable.
- Add focused assertions for both positive and negative AOE cases to prevent over-broad matches.
- Run targeted mettagrid AOE tests (and adjacent affected modules) before broader test runs.
