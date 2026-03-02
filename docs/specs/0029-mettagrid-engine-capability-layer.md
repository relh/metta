# Mettagrid Engine Capability Layer

> **Status:** Draft  
> **Author:** Richard + Codex  
> **Created:** 2026-02-26  
> **Scope:** `packages/mettagrid`, `metta/games/*`, policy/replay/mettascope interfaces

## Summary

Move Mettagrid from config-as-runtime-truth to a capability-first runtime boundary:

1. `GameAuthoringConfig` for build-time game definition
2. `EngineManifest` for stable resolved runtime schema
3. `EngineCapabilities` for runtime behavior access

## Problem

Today, `MettaGridConfig`/`GameConfig` serves as authoring format, runtime transport, and consumer contract at once. That
creates high coupling between game config shape and:

- C++ runtime conversion path
- policy schema generation
- replay payload shape
- MettaScope data model assumptions

## Solution

Define a hard runtime boundary around manifest + capability APIs.

- Authoring config is input only.
- Runtime consumers (engine, policy, replay, render) use manifest and capabilities.
- Existing compatibility paths stay temporary and explicit.

## Goals

- [ ] Add `EngineManifest` generated during env construction.
- [ ] Expose `SpatialApi`, `TerritoryApi`, `QueryApi` as initial runtime capabilities.
- [ ] Add policy path `PolicyEnvInterface.from_manifest(...)`.
- [ ] Persist manifest in replay metadata.
- [ ] Migrate MettaScope to manifest-backed schema reads.
- [ ] Remove runtime dependence on raw `mg_config` after migration.

## Non-Goals

- Full rewrite in one PR.
- Immediate conversion of every subsystem.
- Immediate proto migration for manifest.

## Cross-Game Taxonomy

Validated shared mechanics across Hunger and Cogs-vs-Clips:

- Resource/inventory economy:
  - Hunger: `metta/games/hunger/variants/food.py`, `metta/games/hunger/variants/energy.py`
  - CvC: `packages/cogames/src/cogames/cogs_vs_clips/cog.py`, `packages/cogames/src/cogames/cogs_vs_clips/hub.py`
- Timed event systems:
  - Hunger: `metta/games/hunger/variants/seasons.py`, `metta/games/hunger/variants/solar.py`
  - CvC: `packages/cogames/src/cogames/cogs_vs_clips/clips.py`, `packages/cogames/src/cogames/cogs_vs_clips/weather.py`
- Query/tag graph and network mechanics:
  - Hunger: `metta/games/hunger/variants/seasons.py`
  - CvC: `packages/cogames/src/cogames/cogs_vs_clips/team.py`, `packages/cogames/src/cogames/cogs_vs_clips/junction.py`
- Map assembly and placement:
  - Hunger: `metta/games/hunger/game.py`
  - CvC: `packages/cogames/src/cogames/cogs_vs_clips/sites.py`, `packages/cogames/src/cogames/cogs_vs_clips/terrain.py`

Long-term API families:

1. `ResourceApi`
2. `InteractionApi`
3. `TimelineApi`
4. `QueryApi`
5. `TagGraphApi`
6. `SpatialApi`
7. `TerritoryApi`
8. `MapAssemblyApi`
9. `StatsRewardApi`
10. `RenderSchemaApi`

## Design

### Runtime Contracts

#### 1) `GameAuthoringConfig`

Owned by game packages. Defines objects/actions/events/map generation/variants. Not a runtime transport contract.

#### 2) `EngineManifest`

Resolved schema emitted once per env build. Minimum v1 fields:

- `manifest_version`
- object schema (ids, names, tags/categories, inventory constraints)
- action schema (ids, args, costs/cooldowns)
- observation schema (global/object/action mask and tensor metadata)
- stat schema (agent/object/global stat metadata)
- query descriptors
- territory descriptors
- render metadata required by replay/UI consumers

#### 3) `EngineCapabilities`

Typed runtime APIs. Initial set:

- `SpatialApi`
- `TerritoryApi`
- `QueryApi`

Follow-on set:

- `TimelineApi`, `TagGraphApi`, `ResourceApi`, `InteractionApi`, `StatsRewardApi`, `RenderSchemaApi`, `MapAssemblyApi`

### Concrete API Targets (Initial Slice)

Representative signatures:

```cpp
class ISpatialApi {
 public:
  virtual ~ISpatialApi() = default;
  virtual std::vector<int> aoe_cells_for_object(int object_id, int aoe_id) const = 0;
};

class ITerritoryApi {
 public:
  virtual ~ITerritoryApi() = default;
  virtual int territory_owner_at(int row, int col) const = 0;
};

class IQueryApi {
 public:
  virtual ~IQueryApi() = default;
  virtual QueryResult read(int query_id) const = 0;
};
```

Python runtime target:

```python
class EngineRuntime:
    manifest: EngineManifest
    capabilities: EngineCapabilities
```

## Migration Plan

### Phase 1: Capability facades

Files:

- `packages/mettagrid/cpp/bindings/mettagrid_c.hpp`
- `packages/mettagrid/cpp/bindings/mettagrid_c.cpp`
- `packages/mettagrid/cpp/include/mettagrid/core/{aoe_tracker,territory_tracker,query_system}.hpp`

Work:

- Expose read-only facades over existing trackers/systems.

Acceptance:

- Facades return data equivalent to current internal usage.

### Phase 2: Manifest generation + replay plumbing

Files:

- `packages/mettagrid/python/src/mettagrid/config/mettagrid_c_config.py`
- `packages/mettagrid/python/src/mettagrid/simulator/simulator.py`
- `packages/mettagrid/python/src/mettagrid/simulator/replay_log_writer.py`

Work:

- Emit deterministic manifest from resolved env config.
- Persist manifest in replay metadata.

Acceptance:

- Manifest deterministic for identical inputs.
- Episode semantics unchanged.

### Phase 3: Policy migration

Files:

- `packages/mettagrid/python/src/mettagrid/policy/policy_env_interface.py`

Work:

- Add and adopt `PolicyEnvInterface.from_manifest(...)`.
- Keep temporary fallback from raw config.

Acceptance:

- Parity tests pass vs current policy interface behavior.

### Phase 4: MettaScope migration

Files:

- `packages/mettagrid/nim/mettascope/src/mettascope/replays.nim`
- `packages/mettagrid/nim/mettascope/src/mettascope/panels/objectpanel.nim`

Work:

- Read manifest schema in loader/panels.
- Keep temporary legacy fallback.

Acceptance:

- New and old replay formats load during migration window.

### Phase 5: Boundary enforcement

Work:

- Remove raw-config runtime dependencies from policy/render/runtime paths.
- Deprecate legacy replay `mg_config` payload.

Acceptance:

- Runtime consumers no longer require raw `mg_config` shape.

## Compatibility Strategy

- During migration, replay contains both manifest and legacy payload.
- Compatibility path removal requires:
  - policy migrated
  - MettaScope migrated
  - at least one end-to-end game path using capabilities

## Test Plan

1. Unit tests

- capability facade correctness
- manifest determinism

2. Integration tests

- simulator parity before/after capability + manifest plumbing
- policy parity (`from_mg_cfg` vs `from_manifest`)

3. Replay/render tests

- replay manifest emission
- MettaScope manifest parsing
- legacy replay compatibility fixture

## Open Questions

1. JSON-first manifest in replay, then proto later, or proto immediately?
2. Which render metadata lives in core manifest vs UI-specific extension?
3. Exact deprecation window for legacy `mg_config` replay payload?
4. Should capability APIs remain strictly read-only for game logic?

## Initial Milestone

1. Ship `SpatialApi` + `TerritoryApi` + `QueryApi` facades.
2. Emit `EngineManifest` v1 in replay.
3. Use `PolicyEnvInterface.from_manifest(...)` by default.
4. Move one MettaScope panel path to manifest with fallback.

## Expansion Milestone (After Stabilization)

1. `TimelineApi` + `TagGraphApi`
2. `ResourceApi` + `InteractionApi`
3. `StatsRewardApi` + `RenderSchemaApi`
4. `MapAssemblyApi`
