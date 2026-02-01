# Publishing Packages

This document describes how `metta publish` works for the three publishable packages: mettagrid, cogames, and
cogames-agents.

## Dependency Chain

```
cogames-agents → cogames → mettagrid
```

Each package pins its dependencies to exact versions (`==X.Y.Z`) at publish time. The publish tool handles this
automatically.

## Quick Reference

```bash
metta publish cogames-agents          # Full flow: mettagrid → cogames → cogames-agents
metta publish cogames                 # Partial flow: mettagrid → cogames
metta publish mettagrid               # Just mettagrid
metta publish cogames-agents --dry-run --force  # Preview without doing anything
```

## Full Flow: `metta publish cogames-agents`

### Prerequisites

- On `main` with a clean working tree (or pass `--force` to bypass)
- Git remote pointing to `Metta-AI/metta`

### 1. Setup

Fetches tags from origin, determines the next version by bumping the last component of the latest `cogames-agents-v*`
tag (e.g., `0.0.0.1` → `0.0.0.2`). Prints a release summary.

### 2. Orchestration prompt

```
Also publish mettagrid and cogames first (and update cogames-agents' dependency pins)? [Y/n]:
```

If **no**: skips to step 5, publishes cogames-agents alone with whatever dependency versions are already in
pyproject.toml.

If **yes**: continues to step 3.

### 3. Publish mettagrid

Recursively calls `_publish(Package.METTAGRID)`:

- Bumps the mettagrid version tag (e.g., `0.2.0.66` → `0.2.0.67`)
- Creates and pushes git tag `mettagrid-v0.2.0.67` to origin
- Posts release announcement to Discord
- Pushes filtered git history to the `Metta-AI/mettagrid` child repo

The tag push triggers `.github/workflows/release-mettagrid.yml`, which builds multi-platform wheels (Linux x86, Linux
ARM, macOS) and publishes to PyPI via OIDC trusted publisher. This takes ~17 minutes due to ARM builds.

### 4. Publish cogames

Recursively calls `_publish(Package.COGAMES, mettagrid_version_to_pin=...)`:

- Since `mettagrid_version_to_pin` is already set, the cogames orchestration block is skipped (no double-publish of
  mettagrid)
- **Pins mettagrid** in cogames: creates branch `chore/update-cogames-mettagrid-to-X.Y.Z`, writes the exact pin to
  `packages/cogames/pyproject.toml`, commits, pushes, creates PR back to main
- Creates and pushes git tag `cogames-v0.3.58` on the pin branch (so the tagged version includes the correct dependency)
- Posts to Discord, pushes to `Metta-AI/cogames` child repo

The tag push triggers `.github/workflows/release-cogames.yml`, which builds the wheel, waits for the pinned mettagrid
version to appear on PyPI (polls every 60s, 25-min timeout), runs smoke tests (`pytest`, `cogames version`,
`cogames missions`), then publishes.

### 5. Publish cogames-agents

Returns to the starting branch (`main`), then:

- **Pins mettagrid** in cogames-agents: creates branch, writes exact pin, commits, pushes, creates PR
- **Pins cogames** in cogames-agents: creates another branch (from the mettagrid pin branch), writes exact pin, commits,
  pushes, creates PR
- Creates and pushes git tag `cogames-agents-v0.0.0.2` on the current HEAD (which has both pins)
- Posts to Discord, pushes to `Metta-AI/cogames-agents` child repo

The tag push triggers `.github/workflows/release-cogames-agents.yml`, which builds multi-platform wheels (Linux x86,
Linux ARM, macOS) -- cogames-agents compiles Nim code into platform-specific binaries -- waits for both pinned mettagrid
and cogames versions to appear on PyPI, then publishes.

## CI Workflows

Each package has a release workflow at `.github/workflows/release-{package}.yml` triggered by tag pushes matching
`{package}-v*`.

| Package        | Build          | Wait gates                  | Tests                      | Publish       |
| -------------- | -------------- | --------------------------- | -------------------------- | ------------- |
| mettagrid      | Multi-platform | None                        | None                       | PyPI via OIDC |
| cogames        | Pure Python    | mettagrid on PyPI (25 min)  | pytest + CLI smoke tests   | PyPI via OIDC |
| cogames-agents | Multi-platform | mettagrid + cogames (25/10) | None (build + twine check) | PyPI via OIDC |

All workflows use PyPI trusted publishers (OIDC) -- no API tokens needed. Each requires two GitHub environments:
`{package}-pypi` and `{package}-testpypi`.

Workflows also support manual dispatch (`workflow_dispatch`) with options to target testpypi for safe testing.

## What You End Up With

After a full `metta publish cogames-agents`:

- 3 new git tags pushed to origin
- 3 CI workflows triggered (running in parallel, with wait gates ensuring correct ordering)
- 2-3 PRs to merge dependency pins back to main
- Packages appear on PyPI in order: mettagrid first (~17 min), cogames next (~5 min after), cogames-agents last (~5 min
  after)

## Partial Flows

### `metta publish cogames`

Asks whether to publish mettagrid first. If yes: publishes mettagrid, pins mettagrid in cogames, tags cogames. Does
**not** touch cogames-agents.

### `metta publish mettagrid`

Publishes mettagrid only. No orchestration, no dependency pinning.

## Key Files

| File                                           | Purpose                                      |
| ---------------------------------------------- | -------------------------------------------- |
| `metta/setup/tools/publish.py`                 | CLI tool: versioning, tagging, orchestration |
| `.github/workflows/release-mettagrid.yml`      | CI: multi-platform build + PyPI publish      |
| `.github/workflows/release-cogames.yml`        | CI: build, wait for mettagrid, test, publish |
| `.github/workflows/release-cogames-agents.yml` | CI: build, wait for dependencies, publish    |
| `devops/git/push_child_repo.py`                | Syncs filtered git history to child repos    |
| `packages/{package}/pyproject.toml`            | Package metadata, setuptools_scm config      |
