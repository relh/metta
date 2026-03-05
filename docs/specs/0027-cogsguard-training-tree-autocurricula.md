# Cogsguard Training Tree and Join-Based Autocurricula

> **Status:** Draft **Author:** Richard + Codex **Created:** 2026-02-19

## Summary

Define and implement a canonical Cogsguard training tree in `richard-shards`, where atomic mechanics (mining, aligning,
scrambling, scouting, role selection/switching) are trained and evaluated independently, then joined into combinatorial
mechanics through explicit prerequisites. Ship this as an Observatory-facing dashboard and API so we can answer, per
policy version, "what is learned, what is not, and what joins are reliable."

## Tracking Update (2026-02-19)

Dashboard follow-up requested for this branch:

- Add new tabs to policy performance dashboard:
  - `Eval Tree`
  - `Train Tree`
- Start with the eval-centric version:
  - for each skill/mechanic (for example mining), show whether policy has been tested and demonstrated it
  - allow mock statuses when no explicit Cogames diagnose test exists yet
- Populate the skill tree with:
  - all Cogames diagnose diagnostics
  - dashboard diagnostics/signals where available
- Present diagnostics in a semantically sensible dendrogram (single tree view of "everything we measure")
- Initial scope is UI-first (minimal hookups, "things we measure" first), then later split/strengthen:
  - eval-centric evidence in one tab
  - training-curriculum-exists-and-works in another tab

## Migration Update (2026-02-19)

Branch integration context:

- `richard-standalonedashboard` introduces a standalone package under `dashboard/`:
  - `vibeservatory/backend` serves dashboard API outside `app_backend` route ownership
  - `dashboard/frontend` is the new dashboard UI surface
- `richard-observatory-read-replica` introduces infra-managed readonly DB URI secret for dashboard usage:
  - secret name default: `observatory/dashboard/readonly-db-uri`
  - intent: dashboard reads from read-replica endpoint with non-writer credentials

Compatibility work added in `richard-shards`:

- Keep Observatory as a pointer to standalone dashboard per policy version.
- Port tree UI concepts into standalone frontend:
  - add standalone `Eval Tree` and `Train Tree` tabs
  - add standalone dendrogram + coverage matrix scaffolding
  - include dashboard + diagnose + training node catalogs and missing-node queue
- Align standalone backend config with readonly naming:
  - prefer `DASHBOARD_READONLY_DB_URI`
  - remove `DASHBOARD_DB_URI` fallback to avoid writer-URI ambiguity
  - reject writer username (`metta`) at startup

## Problem

We currently have strong pieces (role recipes, diagnose, eval suites, policy dashboard), but no canonical structure
that:

1. Defines atomic skills and join skills in one tree.
2. Ties each node to both training curricula and eval criteria.
3. Supports robust variant coverage (clips on/off, cogs counts, uneven team sizes, sparse/prevalent resources).
4. Exposes mechanic-by-mechanic readiness in Observatory for policy-level decision making.
5. Automatically routes training toward newly introduced mechanics without catastrophic forgetting.

The result is fragmented progress: policies can be strong on isolated behaviors but we cannot reliably tell if they are
ready across the full game composition.

## Solution

Implement a versioned `training_tree` system with:

- A canonical tree definition (atomic nodes + join nodes + prerequisites).
- Node-level training shards and node-level eval suites.
- Join curricula that combine mechanics in time and/or space.
- Autocurricula sampling that prioritizes not-yet-mastered nodes while preserving mastered nodes.
- Observatory UI/API that renders the tree, readiness, evidence, and diagnostic coverage.

## Goals

- [ ] Create a canonical Cogsguard training tree rooted at `cogsguard` with leaves for atomic mechanics and internal
      join nodes.
- [ ] Every node has:
  - [ ] training curricula definition
  - [ ] eval definition
  - [ ] pass criteria and readiness scoring
- [ ] Add canonical mining subgame v1/v2 with robust variants and 256-step slices.
- [ ] Support variants across:
  - [ ] clips on/off
  - [ ] cogs in `{1,2,3,4,5,7,8}`
  - [ ] balanced and uneven team sizes
  - [ ] sparse vs prevalent resources
- [ ] Add join curricula for at least:
  - [ ] scout + miner (find -> gear -> mine loop)
  - [ ] mining + aligning tradeoff
  - [ ] role pick vs role choose vs role switch chains
- [ ] Add policy readiness dashboard in Observatory with canonical tree visualization and node evidence links.
- [ ] Ensure new mechanics become first-class shards so autocurricula actively samples them.

## Non-Goals

- Replacing all current diagnose logic in one step.
- Solving full meta-game strategy in the first tree version.
- Reworking all historical eval suites; we will map/alias incrementally.

## Current-State Audit

### Training/Curriculum Surfaces

- `metta/cogworks/curriculum/task_generator.py` supports `SingleTaskGenerator`, `BucketedTaskGenerator`,
  `TaskGeneratorSet`, and `CyclicTaskGeneratorSet`.
- `metta/cogworks/curriculum/curriculum.py` supports active-task pools + pluggable algorithms, but has no prerequisite
  DAG semantics.
- `metta/cogworks/curriculum/learning_progress_algorithm.py` and
  `metta/cogworks/curriculum/prioritized_regret_algorithm.py` provide adaptive sampling but are task-id based, not
  tree-node aware.
- `recipes/experiment/cogsguard.py` already merges many task generators and variants via `make_curriculum(...)`, but
  this is a flat merged set, not a canonical prerequisite tree.

### Existing Cogsguard Role/Mechanic Coverage

- `recipes/experiment/cogsguard.py` provides dedicated `miner`, `aligner`, and `scout` training helpers, but no explicit
  scrambler helper and no join curricula abstraction.
- `packages/cogames/src/cogames/cogs_vs_clips/evals/cogsguard_evals.py` has broad environment eval maps;
  `diagnostic_evals.py` has focused diagnostics; `spanning_evals.py` has stress variants.
- Existing eval suites are useful primitives but not organized as atomic-vs-join tree nodes.

### Diagnose and Observatory

- `packages/cogames/src/cogames/diagnose.py` has a stage-gated pack (`COGSGUARD_STAGE1_PACK_V1`) based on axis-level
  diagnostics (stability/efficiency/control/social), not explicit mechanic node readiness.
- `web/observatory/src/components/cogames-diagnose/SkillTree.tsx` renders diagnose artifacts from `doctor_note.json`
  under `outputs/cogames-diagnose/*` and is local-artifact oriented.
- `app_backend/src/metta/app_backend/routes/dashboard_routes.py` + `web/observatory/.../dashboard` provide aggregate
  policy KPIs, but no training-tree readiness model.

### Gap Summary

The codebase has most technical building blocks (mission variants, curriculum samplers, eval tooling, UI surfaces), but
no canonical training-tree schema binding training, eval, and readiness into one system.

## Design

### 1. Canonical Tree Data Model

Add a versioned tree definition in `packages/cogames/src/cogames/cogs_vs_clips/training_tree/`:

- `tree.v1.yaml` (or JSON):
  - `tree_id`, `tree_version`
  - `root_node_id: cogsguard`
  - node list:
    - `node_id`
    - `kind` (`atomic` | `join` | `composite`)
    - `mechanic_family` (`mining`, `aligning`, `scrambling`, `scouting`, `role`, `integrated`)
    - `prerequisites: list[node_id]`
    - `training_shards: list[shard_id]`
    - `eval_suite_id`
    - `readiness_metric`
    - `pass_threshold`
    - `variant_axes` (clips, cogs, team-size, resource-density, phase-window)

Add typed models in Python and TS to keep schema aligned:

- Python: `packages/cogames/src/cogames/cogs_vs_clips/training_tree/types.py`
- TS: `web/observatory/src/lib/cogsguard-training-tree/types.ts`

### 2. Node Taxonomy (v1)

Atomic nodes (initial minimum set):

- `mining.v1.extract.stationary_bandit`
- `mining.v1.extract.sparse`
- `mining.v1.deposit.loop`
- `scouting.v1.resource_discovery`
- `aligning.v1.capture_neutral`
- `scrambling.v1.neutralize_enemy`
- `role.v1.pick_role`
- `role.v1.switch_role`

Join nodes:

- `join.v1.scout_plus_miner_find_then_mine`
- `join.v1.mining_plus_aligning_tradeoff`
- `join.v1.mine_align_scramble_rotation`
- `join.v1.role_switch_chain_k{1,2,4,8}`

Composite nodes:

- `integrated.v1.mining_subgame`
- `integrated.v1.core_everything_subgame`

### 3. Canonical Mining Subgame v1/v2

#### Mining v1

- 256-step mini-game.
- Multi-armed-bandit extractor quality (stationary values across episode).
- Extractor requires repeated interaction to fully load cargo (not one-action drain).
- Include prevalent and sparse resource layouts.
- Teammates include aligner/scrambler/scout baselines for realistic context.

#### Mining v2

- Same as v1 plus non-stationary drift in extractor quality over time.
- Explicit exploration-exploitation pressure (periodic re-sampling needed).

#### Variant matrix required for both

- `clips`: on/off
- `cogs`: `{1,2,3,4,5,7,8}`
- `team_size`: balanced and uneven (for example `4v4`, `5v3`, `7v1`)
- `resource_density`: prevalent/sparse
- `phase_window`: early/mid/late starts inside 256-step slices

### 4. Join and Autocurricula Strategy

#### Join semantics

- **Join in time:** sequential skill chains (for example scout -> gear -> mine -> deposit).
- **Join in space:** concurrent role interactions across map regions.

#### Autocurricula mechanism

- Introduce a tree-aware sampler:
  - inputs: node readiness, confidence, recency, forgetting risk
  - outputs: shard sampling distribution
- Default policy:
  - prioritize unmet prerequisite leaves first
  - unlock join nodes only when prerequisites pass
  - maintain a replay budget on mastered leaves to prevent regression
- New mechanic onboarding:
  - every new node must register at least one training shard + one eval shard
  - sampler automatically allocates minimum quota to newly added nodes until confidence target is reached

### 5. Eval Design Per Node

For each node define:

- Eval mission set(s)
- Metric(s)
- Pass threshold
- Minimum seed/team-size coverage

Examples:

- `mining.v1.extract.stationary_bandit`:
  - metric: best-arm revisit ratio + cargo throughput
  - pass: revisit ratio >= X and throughput >= Y across sparse+prevalent cases
- `join.v1.scout_plus_miner_find_then_mine`:
  - metric: time-to-first-high-value-mine and sustained mining yield
  - pass: both above threshold with clips on and off
- `role.v1.switch_role`:
  - metric: successful switch count with no collapse in objective reward
  - pass: chain depth success for k in `{1,2,4,8}`

### 6. Diagnostics and Readiness Model

Add a readiness layer that maps directly to tree nodes:

- Node readiness score (0-1) + pass/fail + confidence.
- Pairwise lattice view (2x2) for paired skills.
- 3-skill cube and N-skill hypercube coverage summaries for combinatorial reliability.
- Policy readiness verdict:
  - `not_ready`, `partially_ready`, `tree_ready_v1`.

This augments (not replaces initially) axis-based diagnose outputs.

### 7. Observatory Dashboard Plan

#### Backend/API

Add API endpoints for training-tree results under policy versions, e.g.:

- `GET /stats/policies/versions/{policy_version_id}/training-tree?tree_version=v1`
- `GET /stats/policies/versions/{policy_version_id}/training-tree/{node_id}/evidence`

Response includes:

- tree metadata
- per-node readiness + thresholds + metrics
- links to supporting episodes/replays/artifacts
- unresolved prerequisites

#### Frontend

Add pages/components:

- `web/observatory/src/app/(main)/policies/versions/[policyVersionId]/training-tree/page.tsx`
- `web/observatory/src/components/cogsguard-training-tree/TrainingTree.tsx`
- `web/observatory/src/components/cogsguard-training-tree/NodePanel.tsx`

UI capabilities:

- canonical tree render (expand/collapse by depth)
- filter by mechanic family, clips mode, cogs count, team-size mode
- node drill-down to eval evidence
- "Policy ABC readiness" style summary card

### 8. Implementation Phases

#### Phase 1: Schema + Mining v1

- Land tree schema/models + tree.v1 with mining/scout/aligner/scrambler/role leaves.
- Implement mining v1 train+eval shards.
- Emit node-level result artifacts from eval runs.

#### Phase 2: Mining v2 + Join nodes

- Add drift mechanics for mining v2.
- Add scout+miner and mining+aligning join nodes.
- Add role-switch chain evals (`k=1,2,4,8`).

#### Phase 3: Autocurricula + Dashboard

- Land tree-aware sampler and shard routing.
- Add backend training-tree endpoints.
- Add Observatory training-tree pages and policy-version integration.

#### Phase 4: Hardening

- Coverage expansion across full variant matrix.
- Regression gating in CI for tree schema and readiness computation.
- Documentation and operator runbooks.

### 9. Testing Plan

- Unit tests:
  - tree schema validation
  - prerequisite unlock logic
  - readiness aggregation and hypercube coverage math
- Integration tests:
  - node eval pipelines produce expected artifact schema
  - API contract tests for training-tree endpoints
  - Observatory render tests for tree and node drill-down
- Smoke e2e:
  - run one policy through leaf + join evals
  - verify readiness appears in Observatory

### 10. Migration and Compatibility

- Keep existing `cogames diagnose` axis outputs during rollout.
- Introduce tree artifacts as additive (`training_tree.json`, `training_tree_node_results.json`).
- Add compatibility checks in Observatory for missing tree artifacts.

## Open Questions

1. Should tree readiness become the primary tournament readiness gate, or remain advisory in v1?
2. Do we want scrambler leaf training in phase 1 or phase 2 (given current recipe helpers)?
3. Should mining v2 drift be deterministic per seed (for reproducibility) or partially stochastic across episodes?
4. Which uneven team-size set should be canonical beyond `4v4`?
5. Should tree artifacts be stored only in eval outputs first, or also ingested into app-backend DB tables in phase 1?
