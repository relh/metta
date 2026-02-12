# Public API

> **Status:** Draft **Author:** Nishad **Created:** 2025-02-11

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

### Per-Episode Outputs

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
- [ ] Add docs for things we don't yet document: job logs, agent stats, game stats
- [ ] Update existing TournamentClient and StatsClient
- [ ] Update cogames repo to reference the docs
- [ ] Include field-level descriptions (agent stats, game stats)
- [ ] Gate non-public endpoints behind is-softmax auth, enforced by route-level auth test
- [ ] Remove `/stats/` prefix: deploy both old and new paths, migrate frontends/clients to new paths, then remove old
      paths
