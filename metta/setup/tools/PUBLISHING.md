# Publishing Packages

This document describes how `metta publish` works for the two publishable packages: mettagrid and cogames.

## Version Scheme

Both packages use a `{compat}.{patch}` version format (e.g., `0.4.2`). The compat portion is a shared compatibility
string stored in the `COMPAT_VERSION` file at repo root (e.g., `0.4`). The patch is auto-incremented per package.

- `compat` -- bumped manually for breaking changes (e.g., `0.4` → `0.5`)
- `patch` -- auto-bumped by `metta publish` from the latest `{package}-v{compat}.*` tag

Tag format: `{package}-v{compat}.{patch}` (e.g., `cogames-v0.4.2`).

## Dependency Chain

```
cogames → mettagrid
```

Each package pins its dependencies to exact versions (`==X.Y.Z`) at publish time. When publishing cogames, mettagrid is
pinned to its latest patch for the current compat version (resolved independently from mettagrid's own tags).

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

Fetches tags from origin, reads `COMPAT_VERSION`, finds the latest `cogames-v{compat}.*` tag, and bumps the patch (e.g.,
`0.4.1` → `0.4.2`). Prints a release summary.

### 2. Orchestration prompt

```
Also publish mettagrid first (and update cogames' mettagrid pin)? [Y/n]:
```

If **no**: skips to step 4, publishes cogames with mettagrid pinned to mettagrid's latest patch for the current compat
version.

### 3. Publish mettagrid

Recursively calls `_publish(Package.METTAGRID)`:

- Bumps the mettagrid version tag (e.g., `0.4.1` → `0.4.2`)
- Creates and pushes git tag `mettagrid-v0.4.2` to origin
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
- Creates and pushes git tag `cogames-v0.4.2` on the pin branch (so the tagged version includes the correct dependency)
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

## Episode Runner Images

After cogames is published, `.github/workflows/build-episode-runner-image.yml` builds and pushes the episode runner
Docker image with three tags:

- `episode-runner:cogames-{version}` -- immutable, for auditability (e.g., `cogames-0.4.2`)
- `episode-runner:compat-v{compat}` -- mutable, retagged on each patch (e.g., `compat-v0.4`)
- `episode-runner:latest` -- mutable, always points to the newest build

Tournament seasons record their `compat_version` and dispatch jobs using the `compat-v{compat}` image tag. This allows
concurrent seasons on different compat versions. Seasons with no compat version fall back to `EPISODE_RUNNER_IMAGE` env
var (typically `latest`).

## Breaking Changes

To introduce a breaking change:

1. Bump `COMPAT_VERSION` (e.g., `0.4` → `0.5`)
2. Publish both packages -- they'll get `0.5.0` versions
3. New seasons created after the publish will record `compat_version=0.5`
4. Old seasons continue running on `compat-v0.4` images

## Key Files

| File                                               | Purpose                                      |
| -------------------------------------------------- | -------------------------------------------- |
| `COMPAT_VERSION`                                   | Shared compat version string (e.g., `0.4`)   |
| `common/src/metta/common/compat_version.py`        | Shared version parsing helpers               |
| `metta/setup/tools/publish.py`                     | CLI tool: versioning, tagging, orchestration |
| `.github/workflows/release-mettagrid.yml`          | CI: multi-platform build + PyPI publish      |
| `.github/workflows/release-cogames.yml`            | CI: build, wait for mettagrid, test, publish |
| `.github/workflows/build-episode-runner-image.yml` | CI: build + push episode runner Docker image |
| `devops/git/push_child_repo.py`                    | Syncs filtered git history to child repos    |
| `packages/{package}/pyproject.toml`                | Package metadata, setuptools_scm config      |
