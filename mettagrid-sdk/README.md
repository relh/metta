# mettagrid-sdk

This workspace package contains the semantic SDK for Mettagrid games.

The Python import root is `mettagrid_sdk`.

It owns:

- `mettagrid_sdk.sdk`
  - typed `MettagridSDK` contracts
  - state, actions, helpers, memory, and log interfaces
- `mettagrid_sdk.runtime`
  - generic observation decoding/runtime helpers for SDK adapters
- `mettagrid_sdk.games`
  - game-specific semantic adapters such as Cogsguard state, events, and skill/prompt surfaces

## Terminology

- `policy`: the uploaded program/package that implements the Mettagrid policy API
- `cog`: one isolated running copy of a policy
- `agent`: any in-episode actor, including cogs and NPCs

This package is per-cog aware but not policy-runtime specific. It defines the semantic surface that higher-level policy
code should target.

Game-specific skill summaries and semantic control-primitives belong here, not in higher-level cyborg runtimes. Those
runtimes should consume this package's surface rather than redefining parallel prompt contracts.

## SDK Contract

Higher-level policy code should target one interface:

```python
def step(sdk):
    sdk.log.write(
        LogRecord(
            level="info",
            message="Enemy appeared on east lane.",
            review=ReviewRequest(trigger_name="enemy_seen", prompt="Re-evaluate lane assignment."),
        )
    )
    return {"target": "junction", "role": sdk.state.self_state.role}
```

The important boundary is the SDK itself:

- `sdk.state`
- `sdk.actions`
- `sdk.helpers`
- `sdk.memory`
- `sdk.log`

`sdk.log.write(LogRecord(..., review=ReviewRequest(...)))` is the canonical way in-episode code escalates a notable
situation for pause-and-review. `sdk.log.request_review(...)` may exist as shorthand, but the runtime should treat
reviews as triggered by logged records.

The rest of the stack should keep domain semantics in code below this boundary and policy improvement, planning, and
memory logic above it.
