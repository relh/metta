# PR 13: HandlerContext: GridObject\* actor/target, add query_system

## Summary

Change HandlerContext to use GridObject* instead of HasInventory* for actor/target, add query_system pointer.

## Spec Items

- **#7**: HandlerContext uses GridObject* instead of HasInventory*

## Files to Modify

- `packages/mettagrid/cpp/include/mettagrid/handler/handler_context.hpp` — Change actor/target types, add query_system
  pointer, add skip_on_update_trigger flag
- `packages/mettagrid/cpp/src/mettagrid/handler/handler_context.cpp` — Update constructors
- All files that construct HandlerContext — Update to pass GridObject\* and query_system

## Key Implementation Details

- actor/target: HasInventory* -> GridObject* (enables tag/location/vibe access in filters/mutations)
- Add QuerySystem\* query_system field
- Add bool skip_on_update_trigger flag for recursion prevention
- KEEP collectives pointer for now (removed in PR 35)
- Update all HandlerContext construction sites throughout the codebase

## Tests

- C++ tests updated for new HandlerContext construction
- Existing handler tests should still pass

## Dependencies

- PR 1 (QuerySystem), PR 4 (GridObject tag methods)
