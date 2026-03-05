---
name: cb.fix-mettagrid-preserve-per-aoe-filter-dependencies-tick-ordering
description: 'Use when fixing mettagrid preserve per AOE filter dependencies tick ordering.'
---

# Fix Mettagrid Preserve Per Aoe Filter Dependencies Tick Ordering

## Trigger

- Primary: "fixing mettagrid preserve per AOE filter dependencies tick ordering"
- Variant: "fixing mettagrid unhashable localpolicyserverhandle timeout diagnostics"

## Workflow

- Reproduce in the smallest mettagrid case possible and capture the seed/map/tick where behavior diverges.
- Treat this as hot-loop C++ work: preserve tick ordering and AOE dependency invariants, and avoid extra per-step
  allocations/lookups.
- Fix the root cause in engine logic first, then add a regression test that fails before and passes after.
- Validate with targeted mettagrid tests plus a quick before/after perf sanity check; report correctness and perf
  impact.
