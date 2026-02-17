# PR 03: Add SharedTagPrefixFilter (C++)

## Summary

Add SharedTagPrefixFilter C++ implementation for filtering based on shared tag prefixes between actor and target. Only
SharedTagPrefixFilter — no SharedTagFilter or SharedTagCondition. Just checks for any intersection.

## Files to Create/Modify

**Create:**

- `packages/mettagrid/cpp/include/mettagrid/handler/filters/shared_tag_filter.hpp` — SharedTagPrefixFilter class using
  bitset operations on tag_bits

**Modify:**

- `packages/mettagrid/cpp/include/mettagrid/core/filter_config.hpp` — Add SharedTagPrefixFilterConfig to FilterConfig
  variant
- `packages/mettagrid/cpp/src/mettagrid/handler/filters/filter_factory.cpp` — Add factory case for SharedTagPrefixFilter
- `packages/mettagrid/cpp/include/mettagrid/handler/handler_bindings.hpp` — Pybind for SharedTagPrefixFilterConfig
- `packages/mettagrid/python/src/mettagrid/mettagrid_c.pyi` — Stub for SharedTagPrefixFilterConfig

## Key Implementation Details

- SharedTagPrefixFilter: resolve tag prefix to bitmask at config time, check actor/target share any tag with that prefix
- Uses bitset intersection for O(1) checking
- No condition enum — just checks `(actor_masked & target_masked).any()`
