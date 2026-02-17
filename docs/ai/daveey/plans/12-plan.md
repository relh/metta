# PR 12: Add DEBUG_HANDLERS environment variable

## Summary

Add handler tracing via DEBUG_HANDLERS=1 environment variable for debugging handler execution.

## Spec Items

- **#15**: DEBUG_HANDLERS environment variable

## Files to Modify

- `packages/mettagrid/cpp/src/mettagrid/handler/handler.cpp` — Add log_handler_result() that logs handler name,
  actor/target, success/fail
- `packages/mettagrid/cpp/src/mettagrid/handler/handler_context.cpp` — Add append_entity_debug_format() helper

## Key Implementation Details

- Check DEBUG_HANDLERS env var at startup, store as static bool
- log_handler_result(): prints handler name, actor identity (type:name(id)), target identity, and pass/fail
- append_entity_debug_format(): formats entity as "type:name(id)"
- Only active when DEBUG_HANDLERS=1, zero overhead otherwise

## Tests

- Manual testing (debug feature)

## Dependencies

- None (independent feature)
