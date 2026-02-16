# Public API

> **Status:** In progress **Author:** Nishad **Created:** 2025-02-11

## Summary

We serve an API for getting information about the tournament. Our external surface area (softmax.com, Observatory,
cogames CLI) uses this API. Except for signup, a submitter needn't use anything outside the documented API to interact
with our system. Documentation exists for the API (hosted) and CLI (in-package, `cogames -h`), and both are designed to
be easy for LLMs to consume.

## Problem

The API exists but lacks a clear public/private boundary, consistent endpoint naming, generated client types, and
comprehensive documentation describing what the data actually means. External consumers (cogames CLI, third-party
tooling) have no stable contract. Internal frontends don't benefit from the OpenAPI spec for type generation.

## Solution

Establish a formal public API surface with hosted docs, generated types for frontends, and auth-gated access for
non-public endpoints. Define a change policy that prevents accidental drift while allowing intentional evolution.

## Change Policy

- We detect and prevent accidental drift: CI compares the generated OpenAPI spec against a checked-in copy in
  `app_backend/.../generated/`. If they differ, CI fails.
- We are happy to make intentional, non-backwards-incompatible changes without announcement
- We announce breaking changes and aim to minimize them

## What We Serve

### Core

Account status, uploading policies, submitting to pools, checking policy status within a season, leaderboard.

### Game Results

The public API exposes game results through two resource types:

**Match** — the tournament-facing resource. Always exists once scheduled, even if the game fails. Includes season/pool
context, participating policies, assignments, scores, and an error message for failed matches. In list responses,
includes `episode_id`; in detail responses, includes the full inline Episode.

**Episode** — the game data resource. Only created when a game completes successfully. Includes replay URL, game-level
stats, per-policy results (avg reward, avg metrics), and per-agent breakdowns.

Both resources embed `PolicyVersionSummary` (`{id, name, version}`) rather than inlining policy fields. Policy-level
metrics are simple averages of the underlying agent-level metrics.

**Artifacts** are accessible via Match (`GET /matches/{id}/{policy_version_id}/artifacts/{artifact_type}`), auth-gated
to the policy submitter. Currently only `logs` is supported as an artifact type; more may be added later.

**Job** endpoints are internal-only (softmax auth). All useful Job data is surfaced through Match (status, error, logs)
or Episode (stats, replay).

### Visibility

Matches and episodes are public — tournament results are inherently public. Logs are auth-gated to the policy submitter.
Job endpoints are softmax-internal.

## Design Decisions

### Auth enforcement: route-level test

Instead of trying to make FastAPI's `Depends` system enforce auth by default, we add a test that introspects all mounted
routes and asserts each one either has a real auth dependency or explicitly opts out with `_user: AllowAnonUser`.
Forgetting auth on a new endpoint becomes a test failure, not a production incident.

### Public routes with auth-gated params: use separate endpoints

When a route is public but some params are softmax-only, we use separate endpoints rather than branching on auth state
within a single handler. Two endpoints with clear names is more code but less complexity -- the OpenAPI docs stay honest
about what's available, and handlers don't need to reason about partial auth.

## Non-Goals

- Cross-episode querying
- Full OpenAPI codegen for Python (options evaluated, all ugly)
- Formalizing the replay format or applying breaking-change standards to it

## Roadmap

- [x] Go live with API docs
- [x] Frontends (softmax.com, Observatory) consume types from the internal OpenAPI spec
- [x] CI drift detection: compare generated OpenAPI spec against checked-in copy in `app_backend/.../generated/`
- [x] Consolidate and clean endpoints (backwards-incompatible, partial progress in nishad/api-cleanup)
- [x] Add Match and Episode public endpoints with schemas per design doc
- [x] Add `GET /matches/{id}/{policy_version_id}/artifacts/{type}` (auth-gated, `logs` type initially)
- [x] Gate Job endpoints behind is-softmax auth, enforced by route-level auth test
- [x] Include field-level descriptions (agent stats, game stats)
- [x] Update existing TournamentClient and StatsClient to use new Match/Episode endpoints. Update cogames repo to
      reference the docs where they're hosted and give usage suggestions
- [ ] Remove `/stats/` prefix: deploy both old and new paths, migrate frontends/clients to new paths, then remove old
      paths
