# Season Version Pinning

> **Status:** Draft **Author:** Nishad **Created:** 2026-02-17

## Summary

Pin seasons to a cogames/mettagrid compatibility version so that client submissions and server-side episode runners use
matching game logic. Prevents mid-season behavior drift and gives users clear upgrade guidance.

## Problem

Seasons don't declare what cogames/mettagrid version they require. This causes two problems:

1. **Client-side:** Users with older cogames hit incompatibility with tournament configs designed for newer versions,
   with no error message explaining what's wrong.
2. **Server-side:** The episode runner image (`episode-runner:latest`) gets upgraded mid-season, changing game behavior
   for in-flight seasons.

## Solution

Introduce a shared "compat version" integer for mettagrid and cogames. Seasons record the compat version they were
created with. Clients check compat version on upload/submit. Episode runner images are tagged per compat version so
different seasons can coexist on different game versions.

## Goals

- [ ] Seasons record their compat version at creation time
- [ ] `cogames upload` and `cogames submit` reject mismatched compat versions with actionable error messages.
      `cogames validatate-bundle` fetches image/cogames version specific to the season's compat version.
- [ ] Episode runner images are tagged per compat version, allowing concurrent seasons on different versions
- [ ] Hotfixes (patch bumps) are deployed without season rolls
- [ ] Zero disruption to existing seasons (nullable compat version, graceful fallback)

## Non-Goals

- Automatic compat version bumps based on code changes
- Gating local commands (`cogames play`, `cogames evaluate`)

## Design

### Version Scheme

**Format:** `0.{compat}.{patch}` for both mettagrid and cogames.

- `0` -- fixed prefix, signals pre-1.0. Natural graduation path to `1.x.y` later.
- `compat` -- shared compatibility epoch, checked into repo, bumped manually for breaking changes.
- `patch` -- auto-bumped by `metta publish` (per-package, independent).

**Source of truth:** `COMPAT_VERSION` file at repo root containing a single integer. Starting value: `4` (above existing
`0.2.x`/`0.3.x` tags on PyPI).

**Tag format:** `{package}-v0.{compat}.{patch}` (3-part). Old 4-part tags are ignored by publish logic.

### Season Model

Add `compat_version: int | None` to the `Season` table. `NULL` means pre-compat-versioning (no enforcement).

When `_ensure_season_exists()` creates a season, it records the compat version from the running cogames package.
`CommissionerBase` gets a `compat_version` class attribute derived from the installed cogames version at import time.
Season rolling carries `compat_version` forward unless explicitly changed.

API models (`SeasonResponse`, `SeasonInfo`) expose `compat_version: int | None`.

### Client-Side Enforcement

On `cogames upload` and `cogames submit`: fetch the target season's `compat_version`, compare against the installed
cogames compat version (parsed from `importlib.metadata.version("cogames")` middle component).

Mismatch is an error:

```
Error: Season "beta-cvc" requires cogames compat version 4, but you have 0.3.1 (compat 3).
Run: pip install --upgrade cogames
```

`cogames validate-bundle` gets the appropriate cogames version for that season, and similarly the appropriate episode
runner version from ghcr if using `--validation-mode docker`.

Only fires if the season has a non-null `compat_version`.

### Episode Runner Images

**Image tags:**

- `episode-runner:compat-v{N}` -- mutable tag, what seasons reference. Retagged on hotfix rebuilds.
- `episode-runner:cogames-v0.4.2` -- immutable tag for auditability.

**Dockerfile:** Takes `COGAMES_VERSION` build arg. Uses `pip install cogames==${COGAMES_VERSION}` and sets
`ENV COGAMES_VERSION` so the running container can report it.

**Job dispatch:** Commissioner passes the image tag based on `season.compat_version`:
`episode-runner:compat-v{season.compat_version}`. If NULL, falls back to global `EPISODE_RUNNER_IMAGE` config.
Observatory is updated to accept an input target episode runner image.

### Publishing

1. `metta publish` reads `COMPAT_VERSION` from repo root.
2. Finds latest tag matching `{package}-v0.{compat}.*`, increments patch (starts at 0 for new compat).
3. Tags as `{package}-v0.{compat}.{patch}`.
4. When publishing cogames, pins `mettagrid==0.{compat}.{latest_mettagrid_patch}` -- same compat, but mettagrid's latest
   patch is resolved independently from its own tags (not cogames' patch number).
5. CI builds episode runner with `COGAMES_VERSION=0.{compat}.{patch}`, pushes both image tags.
6. Refuses to publish if `COMPAT_VERSION` doesn't match the compat component being tagged.

Version parsing (extracting compat/patch from tags and installed package versions) is shared between `metta publish` and
`setuptools_scm` config so there's a single implementation for the `{package}-v0.{compat}.{patch}` format.

### Operational Flows

**Hotfix:** Publish patch (e.g., `cogames-v0.4.2`). Rebuild and retag `episode-runner:compat-v4`. All compat-4 seasons
pick up the hotfix on next dispatch. No season roll needed.

**Breaking change:** Bump `COMPAT_VERSION` to 5. Publish `cogames-v0.5.0`. Build `episode-runner:compat-v5`. Create new
seasons with `compat_version=5`. Old seasons keep running on `compat-v4`.

### Migration

- DB migration adds nullable `compat_version` column. NULL = no enforcement.
- Existing `episode-runner:latest` keeps working for NULL-compat seasons.
- Client compat check only fires for non-null `compat_version`.
- Old 4-part tags ignored; `metta publish` only looks at 3-part tags.

### Key Files

| File                                         | Change                                    |
| -------------------------------------------- | ----------------------------------------- |
| `COMPAT_VERSION` (new)                       | Single integer, shared source of truth    |
| `metta/setup/tools/publish.py`               | New version scheme, compat validation     |
| `app_backend/.../models/tournament.py`       | `Season.compat_version` column            |
| `app_backend/.../commissioners/base.py`      | Read compat version, pass to job dispatch |
| `app_backend/.../job_runner/dispatch.py`     | Accept image tag override per job         |
| `packages/cogames/src/cogames/main.py`       | Compat check on upload/submit             |
| `packages/cogames/src/cogames/cli/client.py` | `SeasonInfo.compat_version` field         |
| `packages/cogames/Dockerfile.episode_runner` | `COGAMES_VERSION` build arg + env var     |
| `.github/workflows/release-cogames.yml`      | Build + tag episode runner image          |

## Open Questions

1. Should we enforce compat version on `cogames play` when connecting to a remote season (as opposed to local play)?
2. Should the compat version check warn instead of error for forward-compatible cases (user has newer than season)?
