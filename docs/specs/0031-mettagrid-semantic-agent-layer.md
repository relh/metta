# Mettagrid Semantic Agent Layer

> Status: In Review
> Author: Richard + Codex
> Created: 2026-03-07
> Scope: `mettagrid_sdk`, `cog_cyborg`

## Summary

Add a semantic, code-first agent layer for Mettagrid games with one stable LLM-facing interface:

1. `MettagridSDK` is the single interface higher-level policy code targets.
2. `MettagridState`, `MettagridActions`, and deterministic helpers are the core SDK surfaces.
3. Per-cog player bundles plus structured traces become the canonical in-cog code-update loop on top of that SDK.
4. Memory, reflection, planning, and evaluation sit above the SDK instead of replacing it.

Cogsguard is the first implementation target, but the architecture is Mettagrid-level by design so the same boundary
can support additional games.

## Terminology

- `policy`: the uploaded program that implements the Mettagrid policy interface
- `cog`: one isolated running copy of a policy
- `agent`: any in-episode actor, including cogs and NPCs

This architecture is per-cog. A policy may be copied into many cogs, but each cog gets isolated runtime state,
artifacts, memory, and code updates. Team behavior must emerge from observed game state and in-game signaling, not
shared files or out-of-band coordination.

Each cog should be representable as a small player bundle:

- executable entrypoint such as `main.py`
- mutable private memory file
- mutable strategic plan file
- append-only experience trace
- append-only decision / review log
- append-only review transcript
- optional helper modules owned by that cog

## Problem

Raw observation tokens and primitive action lists are too low-level to be the primary interface for LLM gameplay.

That creates predictable failure modes:

- game semantics have to be reconstructed from prompt text instead of consumed through code
- action success and failure are often implicit
- domain-specific competence lives in prompt wording rather than reusable runtime logic
- memory retrieval is weak because events, plans, and beliefs are not stored in a structured way
- new games do not fan out cleanly because each one would require another prompt-heavy control surface

## Goals

- Make `MettagridSDK` the single documented LLM-facing interface for Mettagrid games.
- Add a typed `MettagridState` boundary with a first `CogsguardState` implementation.
- Add `MettagridActions` and deterministic helpers with effect-based, testable behavior.
- Define a bounded SDK execution loop for executable player bundles, code updates, and captured logs.
- Add typed memory, retrieval, reflection, and short-horizon planning above the SDK.
- Add evaluation harnesses that catch reasoning regressions before full rollouts.

## Non-Goals

- Replacing the simulator/runtime primitives.
- Building a natural-language-only memory stream.
- Using shell access as the primary policy interface.
- Changing Cogsguard mechanics as part of this architecture.
- Making Cogsguard-specific names the top-level system boundary.

## Architecture

### Canonical Model

The architecture follows an `rs-sdk`-style layering:

1. runtime primitives
2. player transport / process boundary
3. semantic world state
4. high-level porcelain actions
5. deterministic helpers
6. one programmable SDK surface
7. memory, reflection, planning, and evaluation above that SDK

This keeps domain invariants in code and reduces how much the model has to infer from prompt text.

### Package Boundaries

The implementation is split into two top-level workspace packages:

- `mettagrid-sdk/`
  - Python import root: `mettagrid_sdk`
  - generic semantic SDK contracts
  - game adapters such as Cogsguard semantic state and events
- `cog-cyborg/`
  - Python import root: `cog_cyborg`
  - the in-cog hybrid runtime
  - bounded player execution
  - providers, artifacts, memory, reflection, planning, and policy code
Each package should have one clear responsibility. Instrumentation should not live inside the SDK runtime, and generic
SDK types should not be hidden inside Cogsguard-specific policy code.

### Singular Interface

Higher-level policy code should interact with one surface only:

```python
class MettagridSDK:
    state: MettagridState
    actions: MettagridActions
    helpers: MettagridHelpers
    memory: MemoryView
    log: LogSink
```

Meaning:

- `state`: what is true right now
- `actions`: what meaningful game action can be attempted
- `helpers`: deterministic selection, routing, and filtering utilities
- `memory`: relevant events, beliefs, plans, prior runs, and mutable private scratch state
- `log`: structured execution feedback, review triggers, and pause-worthy events

Everything below this surface is runtime implementation detail. Everything above it is policy improvement and
decision-making.

### `MettagridState`

`MettagridState` is the semantic view of the current step. It should expose:

- self state
  - position
  - role / equipped gear
  - inventory
  - readiness state such as heart, hp, and energy
- visible entities
  - agents
  - hubs
  - junctions
  - extractors
  - stations
- team summary
  - teammates
  - shared inventory/objective summary when available
- known world
  - explored regions
  - frontier regions
  - contested regions
- recent semantic events

Cogsguard is the first concrete adapter, but the type boundary remains Mettagrid-wide.

### `MettagridActions`

`MettagridActions` sits above primitive simulator actions and exposes effect-based verbs with typed outcomes.

Representative Cogsguard actions:

- `acquire_role_gear(role)`
- `collect_from_extractor(resource_kind)`
- `deposit_resources()`
- `pickup_heart()`
- `capture_neutral_junction(junction_id)`
- `neutralize_enemy_junction(junction_id)`
- `explore_frontier(region_id)`
- `recover_in_safe_territory()`

Each action should own:

- preconditions
- movement/adjacency management where needed
- success detection
- retry behavior for deterministic failure cases
- stable typed failure reasons

### Deterministic Helpers

Helpers cover logic the model should not have to rediscover in prompt space, such as:

- target resolution
- route and reachability checks
- frontier selection
- teammate ranking
- safe fallback site selection
- action success detectors

The policy should rarely need to reason about raw cardinal movement or infer whether a semantic action probably worked.

### Executable Players and Bounded SDK Execution

The canonical execution unit is a per-cog executable player bundle whose `main.py` targets the SDK, not raw internals.

That execution path should be:

- bounded
- game-scoped
- typed
- log-capturing
- isolated from arbitrary host access
- able to block for a review / rewrite before the next environment step

Representative execution shape:

```python
def step(sdk: MettagridSDK):
    if not sdk.state.self_state.inventory.get("heart"):
        return sdk.actions.pickup_heart()
    target = sdk.helpers.select_best_visible_junction()
    if target is None:
        return sdk.actions.explore_frontier("nearest")
    return sdk.actions.capture_neutral_junction(target.entity_id)
```

This is the canonical higher-level loop for in-cog symbolic policy updates, whether the code is running in-process or
behind a socket-backed player process.

Runtime-owned artifacts should include:

- `main.py` and optional helper modules
- a mutable memory scratchpad
- an append-only experience trace of observations / semantic summaries
- an append-only decision log containing policy logs, review decisions, and accepted updates

Code Mode principles for these bundles:

- the environment runs an executable `main.py` directly or talks to an equivalent socket-backed player process
- `main.py` is the stable policy entrypoint and may call a small helper library rather than re-deriving tactics in prompt text
- `memory.md` and `plan.md` are editable working files, not append-only logs
- `experience_trace.jsonl` and `decision_log.jsonl` are append-only traces owned by the runtime
- `review_transcript.log` is the append-only model transcript showing what was logged up for review and what came back
- each cog has isolated files, ids, memory, and review triggers
- the model-facing SDK should stay compact and stable so prompts can progressively reveal capabilities instead of dumping raw internals
- `sdk.log.write(LogRecord(...))` is the canonical in-episode path for escalating notable situations to the reviewer
- `sdk.log.register_review_trigger(...)` declares which logged situations are pause-worthy for this cog
- `sdk.log.request_review(...)` may exist as shorthand, but it is not the primary contract; the runtime should treat reviews as triggered by logged records

Directive semantics should stay narrow and explicit so the low-level policy and the reviewer are talking about the same
control primitives:

- `role` selects the semantic baseline behavior family such as miner, aligner, or scrambler
- `objective` selects the current strategic phase such as `resource_coverage`, `economy_bootstrap`, or `aligner_pressure`
- `target_entity_id` is the strongest focus primitive; use it when the policy should pin one exact extractor, junction,
  or other known entity
- `target_region` is a broader lane or area bias for cases where the policy should steer west/east/frontier without
  committing to one exact entity yet
- `resource_bias` is only a resource-type preference among otherwise viable extractor choices; it is not a hard lock on
  one extractor and should not be described as one

Cogsguard-specific prompt adapters and tactical skill libraries should teach these distinctions directly so code-mode
policies do not have to infer them from raw behavior traces.

The runtime should allow a player to register pause-worthy triggers such as:

- first enemy sighting in a lane
- repeated path failures
- low heart economy
- an emitted `sdk.log.write(LogRecord(..., data={"trigger": ...}))` from the current policy code

When a trigger fires, the episode may pause while a backend edits memory, helper modules, or `main.py`.

This architecture has three layers of self:

1. the locked-down in-episode self, where `main.py` uses the SDK, updates `memory.md`, and emits decisive logs
2. the post-episode reflection self, which reads archived traces and summarizes mistakes, wins, and candidate rewrites
3. the open-ended offline research self, which can search, test variants, invent tools, and promote improvements back into the runtime bundle

### Memory

Memory should be typed and retrieval-friendly. At minimum it should store:

- events
- plans
- beliefs
- a mutable per-cog scratchpad / working memory file

Each record should include:

- game
- step
- location or region
- role context
- importance
- summary
- evidence ids where applicable

Retrieval should score using:

- relevance
- recency
- importance

### Reflection

Reflection should synthesize repeated important events into tactical beliefs.

Examples:

- repeated path failures in one region -> `region_path_risky`
- repeated enemy presence on one lane -> `lane_contested`
- repeated heartless alignment failures -> `aligner_requires_heart_before_commit`

Reflection output should be typed and evidence-backed, not free-form diary text.

Post-episode reflection should also be able to read archived `experience_trace.jsonl`, `decision_log.jsonl`, and
`review_transcript.log` files across many episodes and produce compact "learn from experience" summaries.

### Planning

Planning should be short-horizon and reactive, not full-episode and stateless.

The runtime should support:

- an agenda for the next tactical window
- a current subtask with typed success/failure conditions
- continue-vs-react gating based on explicit triggers

Representative triggers:

- heart acquired or lost
- gear acquired or lost
- enemy appeared nearby
- junction ownership changed
- path blocked
- subtask completed
- subtask invalidated

These plans are per-cog. They are not a shared team planner and should not depend on out-of-band shared files.

### Evaluation and Instrumentation

The rollout and replay instrumentation layer should provide:

- replay-aligned policy-intent instrumentation
- generic metrics and motifs
- game-specific trajectory analysis
- interview-style probes over state, memory, and planner output
- archived experience summaries that can drive offline promotion / rollback decisions

This layer exists to explain policy behavior and expose the motifs that matter, not just aggregate scores.

## Cogsguard V1

Cogsguard is the first proving ground for this architecture.

V1 should include:

- semantic Cogsguard state extraction
- semantic event extraction
- a Cogsguard baseline policy running through the new runtime
- trajectory analysis tied to replay and policy intent

The important architectural rule is that Cogsguard is the first implementation, not the top-level product name.

## Rollout

### Phase 1

- SDK contracts
- semantic state
- Cogsguard semantic state/events

### Phase 2

- semantic actions
- deterministic helpers

### Phase 3

- bounded SDK execution
- artifacts and structured logs
- `set_policy` integration

### Phase 4

- typed memory and retrieval

### Phase 5

- reflection

### Phase 6

- hierarchical planning and reaction gating

### Phase 7

- evaluation harnesses and probe workflows

## Acceptance Criteria

- LLM-facing gameplay code can target `MettagridSDK` without reading raw observation tokens directly.
- Cogsguard works through the semantic state/action/runtime boundary.
- Memory, reflection, and planning operate on structured records rather than prompt-only prose.
- Replay instrumentation captures enough policy intent to explain policy behavior.
- The package boundaries are semantically clear: SDK, in-cog runtime, and probe tooling each own one job.

## Open Questions

1. Which SDK types should be hard-common across all games, and which should stay game-specific extensions?
2. How much teammate state should be directly exposed versus inferred from observation plus memory?
3. What is the smallest initial action/helper surface that materially reduces prompt burden?
4. Should retrieval remain heuristic-first, or should later phases add embedding-based relevance?
5. Which policy update name is best long-term: keep `set_policy`, or move to a more explicit SDK-execution term?
