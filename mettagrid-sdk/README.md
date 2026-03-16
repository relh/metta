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

## Two Layers

`mettagrid-sdk` is the plumbing layer for semantic game state, memory, logs, and helper queries.

Higher-level cyborg runtimes are the porcelain layer. They can:

- generate or revise `step(sdk)` code
- maintain `memory.md` and `plan.md`
- translate high-level directives into lower-level scripted behavior

Game-specific skill summaries, helper guidance, and semantic control primitives belong here so every runtime can share
one agent-facing contract instead of drifting into parallel prompt surfaces.

## Agent Contract

Higher-level policy code should target one interface:

```python
def step(sdk):
    target = sdk.helpers.nearest_visible_entity(entity_type="junction", label="neutral")
    if target is not None:
        sdk.log.write(
            LogRecord(
                level="info",
                message="Neutral junction became the focus target.",
                step=sdk.state.step,
            )
        )
        return {"role": "aligner", "target_entity_id": target.entity_id}
    return {"role": "miner", "objective": "resource_coverage"}
```

The important boundary is the SDK itself:

- `sdk.state`
- `sdk.actions`
- `sdk.helpers`
- `sdk.memory`
- `sdk.log`
- `sdk.plan`

`sdk.log.write(LogRecord(..., review=ReviewRequest(...)))` is the only in-episode way code escalates a notable
situation for pause-and-review. There is no separate review shortcut API; if the LLM should be invoked later, the
policy must emit a log record with a typed `review=ReviewRequest(...)`.

## Helper Surface

The default `StateHelperCatalog` is meant to answer the common questions that model-written policy code repeatedly
needs:

- who am I and where am I (`agent_id()`, `position()`, `self_attribute(...)`)
- what does the team currently know (`shared_inventory()`, `shared_objectives()`, `seen_resources()`,
  `missing_resources()`)
- what is visible right now (`visible_entities(...)`, `visible_entity_ids(...)`, `entity_by_id(...)`,
  `nearest_visible_entity(...)`, `distance_to_entity(...)`)
- what recently changed (`visible_entity_counts()`, `recent_event_types()`)

Prefer these helper queries over open-coding repeated scans of `sdk.state.visible_entities` inside generated `step(sdk)`
code.

## Cogsguard Usage Notes

For Cogsguard, the SDK should help the model stay strategic:

- use `target_entity_id` when one exact extractor or junction should stay pinned
- use `target_region` when lane pressure should stay broad
- use `resource_bias` only as a preference over viable extractor choices
- use `shared_inventory()` and `recent_event_types()` as progress signals before changing phases
- keep `step(sdk)` focused on directive choice and logging, not low-level movement or mining loops
