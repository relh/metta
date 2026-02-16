# Policy Self-Encapsulation

> **Status:** Implemented **Author:** Nishad **Created:** 2026-02-04

## Summary

Make submitted policies fully self-contained so they run without depending on the metta repo or its installed packages.
The runner image becomes a public, minimal container with only `mettagrid` and `torch` pinned from PyPI. Each policy
server gets its own venv with base packages installed from uv's cache (near-instant) and any additional dependencies
installed by the policy's setup script. This decouples policy compatibility from the metta repo's evolution and lets
policy authors validate submissions locally against the exact same runner.

## Problem

Today the policy evaluator image (`Dockerfile.policy_evaluator`) is a full clone of the metta repo with all dependencies
installed. Policies are extracted and loaded in-process, implicitly depending on whatever packages happen to be in the
repo's virtualenv. This causes:

- **Backwards compatibility fragility**: updating the metta repo can break previously-working submissions
- **Opaque dependency surface**: policy authors don't know which packages/versions are available to them
- **Heavyweight runner image**: the image includes private training code, kubectl, and other infrastructure that
  policies don't need
- **No local validation parity**: `cogames validate` runs in the user's local environment, which may differ from
  production

## Solution

Each policy gets its own venv, created by the runner using `uv`. The runner image pre-warms uv's package cache with
`mettagrid` and `torch`, so venv creation + base install is near-instant (just linking from cache). The flow:

1. Runner downloads policy bundle to an isolated `/tmp/policy-<hash>/` directory
2. Runner creates a fresh venv in that directory via `uv venv`
3. Runner installs base packages into the venv: `uv pip install mettagrid==X.Y.Z torch` (resolved from uv's cache -- no
   network needed for base packages)
4. If the policy specifies a `setup_script.py`, it runs inside the venv and can pip-install additional dependencies
5. Runner spawns the policy server inside the venv, using mettagrid's HTTP policy protocol (from
   [0021](0021-policy-process-isolation.md))
6. Game subprocess communicates with policy servers over HTTP as usual

For local validation, `cogames validate` reproduces this flow in a fresh `/tmp` directory without requiring Docker. For
production, the runner image is published to DockerHub so advanced users can also test against the exact production
environment.

## Goals

- [x] Each policy server gets its own venv with mettagrid + torch from uv cache
- [x] Runner image contains only mettagrid + torch (pinned public PyPI versions), no private code
- [x] `cogames validate-bundle` exercises the isolated-env flow locally
- [ ] Runner image published to DockerHub, tagged by mettagrid version

## Non-Goals

- Secrets management (future work -- policies declare needed secrets by name, executor injects as env vars)
- Container-level or VM-level isolation per policy (see [0015](0015-thunderdome-policy-isolation.md))
- OS-level user isolation between policy directories
- Requiring Docker for local validation
- Fast local validation (uv caching helps, but first-run installs of torch etc. will be slow)

## Design

### Runner dependency contract

The runner provides exactly two packages as its base: `mettagrid==X.Y.Z` and `torch`. These are the only packages
policies may assume are available without declaring them. This contract is versioned by the runner image tag.

No `runner-requirements.txt` or growing list of "common" packages -- keeping the base minimal avoids recreating the
original implicit dependency problem at a smaller scale.

### Runner Image

The runner image is built from a checked-in Dockerfile. It installs:

1. `uv` (for creating per-policy venvs and installing packages)
2. `mettagrid==X.Y.Z` and `torch` pre-downloaded into uv's package cache

The image doesn't need its own venv -- it only needs uv and a warm cache. Each policy server process runs inside its own
venv created at runtime.

The image is tagged by mettagrid version (e.g., `metta/policy-runner:mettagrid-1.2.3`) and published to DockerHub.

### Version compatibility

The HTTP policy protocol (from [0021](0021-policy-process-isolation.md)) is the stability boundary. As long as the
protocol is stable, policies built against older mettagrid versions continue to work. If the protocol changes, it should
be versioned (e.g., `policy_v2`).

## Implementation Plan

The current `Dockerfile.policy_evaluator` image serves double duty: it runs the orchestrator (`eval_task_orchestrator`)
and is also used as the episode runner image (`EPISODE_RUNNER_IMAGE`). The orchestrator needs `metta.app_backend` and
stays heavy; the episode runner is what we slim down.

- [x] **PR 1: Per-policy venvs in the policy server manager.** Replace `uv run --no-project --with` with `uv venv` +
      `uv pip install` per policy. Each policy server gets its own venv in `/tmp/policy-<hash>/`. Setup scripts run
      inside the venv. Uses uv's cache so base packages install near-instantly.

- [x] **PR 2: New slim Dockerfile for the episode runner.** Add `Dockerfile.episode_runner` alongside the existing
      `Dockerfile.policy_evaluator`. Base image with uv, mettagrid, and torch pre-cached. Entrypoint runs the episode
      runner module from mettagrid. No kubectl, no metta repo clone. The existing orchestrator Dockerfile stays
      unchanged.

- [x] **PR 3: CI workflow to build and publish the slim image.** New GitHub Actions workflow triggered on mettagrid
      releases (`mettagrid-v*` tags). Builds `Dockerfile.episode_runner`, pushes to ECR as
      `episode-runner:<mettagrid-version>`. Keep pushing to same ECR registries so Helm charts pick it up without infra
      changes.

- [x] **PR 4: Switch episode runner jobs to the slim image.** Update `observatory-backend/values.yaml` to point
      `episodeRunnerImage` at the new slim image tag. The orchestrator deployment continues using the existing heavy
      image. This is the production cutover -- deploy behind a feature flag or canary if possible.

- [ ] **PR 5 (stretch): Publish runner image to DockerHub.** Add a DockerHub push step to the workflow from PR 3. Tag as
      `metta/policy-runner:mettagrid-X.Y.Z`. This lets external users run `docker pull` and test against the exact
      production environment.
