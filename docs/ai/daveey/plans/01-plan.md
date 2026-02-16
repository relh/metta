# Add QueryConfig + QuerySystem C++ core

# PR 01: Add QueryConfig + QuerySystem C++ core

## Summary

Add the QuerySystem and QueryConfig C++ types that form the foundation of the new query-based object finding system,
replacing collective membership.

## Spec Items

- **#3**: Add QuerySystem with ClosureQuery — BFS-based transitive closure computation
- **#47**: ClosureQueryConfig gains result_filters

## Files to Create/Modify

**Create:**

- `packages/mettagrid/cpp/include/mettagrid/core/query_config.hpp` — QueryConfig base class, TagQueryConfig,
  ClosureQueryConfig, QueryOrderBy enum, QueryTagConfig
- `packages/mettagrid/cpp/include/mettagrid/core/query_system.hpp` — QuerySystem class with compute_all(), recompute(),
  BFS expansion
- `packages/mettagrid/cpp/src/mettagrid/core/query_system.cpp` — Implementation

**Modify:**

- `packages/mettagrid/cpp/include/mettagrid/core/filter_config.hpp` — Add SharedTagPrefixFilterConfig to variant (if
  needed for ClosureQueryConfig bridge filters)

## Key Implementation Details

- QueryConfig is a polymorphic base class with virtual `evaluate()` method
- TagQueryConfig: finds objects by tag, applies optional filters, supports max_items and order_by
- ClosureQueryConfig: BFS from source tag through bridge-filtered neighbors within Chebyshev radius
- QuerySystem stores vector of QueryTagConfig, materializes tags at init via compute_all()
- recompute(tag_id) re-evaluates a single query tag, fires on_tag_remove for objects losing membership
- apply_limits() handles max_items and random ordering
- matches_max_distance() helper for spatial filtering

## Tests

- Add C++ unit tests for QueryConfig construction, TagQueryConfig evaluation, ClosureQueryConfig BFS
- Test recompute() correctly adds/removes tags
- Test result_filters on ClosureQueryConfig

## Reference

- Branch `daveey/closure`: `packages/mettagrid/cpp/include/mettagrid/core/query_config.hpp`, `query_system.hpp`,
  `cpp/src/mettagrid/core/query_system.cpp`
- New test file on branch: `packages/mettagrid/tests/test_query_system.py` (for reference, the Python integration tests)

## Dependencies

None — this is the first PR in the stack.
