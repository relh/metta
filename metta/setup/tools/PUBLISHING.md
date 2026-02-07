# Publishing Packages

This document describes how `metta publish` works for the two publishable packages: mettagrid and cogames.

## Dependency Chain

```
cogames → mettagrid
```

Each package pins its dependencies to exact versions (`==X.Y.Z`) at publish time. The publish tool handles this
automatically.

## Quick Reference

```bash
metta publish cogames                 # Full flow: mettagrid → cogames
metta publish mettagrid               # Just mettagrid
metta publish cogames --dry-run --force  # Preview without doing anything
```

## Full Flow: `metta publish cogames`

### Prerequisites

- On `main` with a clean working tree (or pass `--force` to bypass)
- Git remote pointing to `Metta-AI/metta`

### 1. Setup

Fetches tags from origin, determines the next version by bumping the last component of the latest `cogames-v*` tag
(e.g., `0.0.0.1` → `0.0.0.2`). Prints a release summary.

### 2. Orchestration prompt

```
Also publish mettagrid first (and update cogames' mettagrid pin)? [Y/n]:
```

If **no**: skips to step 4, publishes cogames alone with whatever dependency version is already pinned in
`packages/cogames/pyproject.toml`.

### 3. Publish mettagrid

Recursively calls `_publish(Package.METTAGRID)`:

- Bumps the mettagrid version tag (e.g., `0.2.0.66` → `0.2.0.67`)
- Creates and pushes git tag `mettagrid-v0.2.0.67` to origin
- Posts release announcement to Discord
- Pushes filtered git history to the `Metta-AI/mettagrid` child repo

The tag push triggers `.github/workflows/release-mettagrid.yml`, which builds multi-platform wheels (Linux x86, Linux
ARM, macOS) and publishes to PyPI via OIDC trusted publisher.

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

## CI Workflows

Each package has a release workflow at `.github/workflows/release-{package}.yml` triggered by tag pushes matching
`{package}-v*`.

| Package   | Build          | Wait gates                 | Tests                    | Publish       |
| --------- | -------------- | -------------------------- | ------------------------ | ------------- |
| mettagrid | Multi-platform | None                       | None                     | PyPI via OIDC |
| cogames   | Pure Python    | mettagrid on PyPI (40 min) | pytest + CLI smoke tests | PyPI via OIDC |

All workflows use PyPI trusted publishers (OIDC) -- no API tokens needed. Each requires two GitHub environments:
`{package}-pypi` and `{package}-testpypi`.

Workflows also support manual dispatch (`workflow_dispatch`) with options to target testpypi for safe testing.

## Discord Notifications

Two Discord messages are sent per package:

1. **"releasing..."** -- sent by `publish.py` when the tag is pushed (before CI runs). Uses the webhook URL from AWS
   Secrets Manager (`discord/channel-webhook/updates`).
2. **"published to PyPI"** -- sent by the CI workflow after successful publish. Uses the `DISCORD_WEBHOOK_URL` GitHub
   Actions secret (must be configured in the repo).

## What You End Up With

After a full `metta publish cogames`:

- 2 new git tags pushed to origin
- 2 CI workflows triggered (running in parallel, with wait gates ensuring correct ordering)
- 1 PR to merge the mettagrid pin back to main (if you opted into pinning)
- Packages appear on PyPI in order: mettagrid first, then cogames (cogames waits for mettagrid)

### `metta publish mettagrid`

Publishes mettagrid only. No orchestration, no dependency pinning.

## Key Files

| File                                      | Purpose                                      |
| ----------------------------------------- | -------------------------------------------- |
| `metta/setup/tools/publish.py`            | CLI tool: versioning, tagging, orchestration |
| `.github/workflows/release-mettagrid.yml` | CI: multi-platform build + PyPI publish      |
| `.github/workflows/release-cogames.yml`   | CI: build, wait for mettagrid, test, publish |
| `devops/git/push_child_repo.py`           | Syncs filtered git history to child repos    |
| `packages/{package}/pyproject.toml`       | Package metadata, setuptools_scm config      |
