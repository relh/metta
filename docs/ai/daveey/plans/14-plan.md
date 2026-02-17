# PR 14: Handler: drop TagIndex\*, add move semantics

## Summary

Simplify Handler constructor to not take TagIndex\*, add move semantics, assert non-empty name.

## Spec Items

- **#39**: Handler constructor simplified — drop TagIndex\*
- **#40**: Handler gains move semantics, loses copy
- **#41**: Handler constructor asserts non-empty name

## Files to Modify

- `packages/mettagrid/cpp/include/mettagrid/handler/handler.hpp` — Remove TagIndex\* param, add move/delete copy, add
  assert
- `packages/mettagrid/cpp/src/mettagrid/handler/handler.cpp` — Update constructor
- All handler construction sites — Remove TagIndex\* argument

## Key Implementation Details

- Handler(const HandlerConfig&, TagIndex\*) -> Handler(const HandlerConfig&)
- Tag lookups moved to runtime via HandlerContext
- Add Handler(Handler&&) = default, operator=(Handler&&) = default
- Delete copy constructor and copy assignment
- Add assert(!\_name.empty()) in constructor

## Tests

- C++ tests updated for new constructor

## Dependencies

- PR 13 (HandlerContext with query_system for runtime tag lookups)
