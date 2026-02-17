# GameValueConfig variant refactoring (C++)

# PR 02: GameValueConfig variant refactoring (C++)

## Summary

Replace the enum-based GameValueConfig with a std::variant, and add compute_fn to ResolvedGameValue for dynamic values.

## Spec Items

- **#8**: GameValueConfig refactored from enum-based struct to std::variant
- **#23**: ResolvedGameValue gains std::function<float()> compute_fn

## Files to Modify

- `packages/mettagrid/cpp/include/mettagrid/core/game_value_config.hpp` — Replace GameValueType enum + flat fields with
  variant: InventoryValueConfig, StatValueConfig, TagCountValueConfig, ConstValueConfig, QueryInventoryValueConfig
- `packages/mettagrid/cpp/include/mettagrid/core/resolved_game_value.hpp` — Add compute*fn field, update
  read()/read_delta() to call compute_fn when set, add mutable* flag
- All files using GameValueConfig — Update to use std::visit pattern

## Key Implementation Details

- Remove GameValueType enum entirely
- Each variant arm carries only its relevant fields (e.g., InventoryValueConfig has scope + resource_id)
- QueryInventoryValueConfig has resource_id + shared_ptr<QueryConfig>
- Scope enum reduced to AGENT and GAME (remove COLLECTIVE)
- ResolvedGameValue: if compute_fn is set, read() calls it instead of dereferencing value_ptr
- mutable\_ flag: false for tag counts and query values (read-only)

## Tests

- C++ tests for variant construction and std::visit resolution
- Test compute_fn-based read()
- Test that existing InventoryValue and StatValue still work

## Dependencies

- PR 1 (QueryConfig types needed for QueryInventoryValueConfig)
