---
name: n.add-season
description:
  Use when adding a new tournament season, creating a new commissioner, rolling a season to a new version, updating a
  season's compat version, or setting up new referees for the Observatory tournament system.
---

# Add / Roll Tournament Season

**Announce at start:** "Checking existing seasons, commissioners, and referees."

## Overview

There are two distinct operations people call "adding a season":

1. **Roll an existing season** to a new version (e.g. bump the cogames compat version). This is the most common
   operation -- it keeps the same commissioner/referee logic but creates a new season version.
2. **Create a brand-new season type** with its own commissioner class, pools, and referees. This is for fundamentally
   new tournament formats.

## Rolling an Existing Season (New Version)

Rolling creates a new version of a season (e.g. `beta` v3 -> v4), disables the old version, copies pool structure, and
optionally migrates active players to the new version's entry pool.

### Entrypoints

There are three ways to roll a season:

**1. Web UI** (Softmax team members only):

- Go to the tournament page for the season
- Click **"Make new season"**
- Select the cogames compat version from the dropdown
- Optionally check "Migrate active players" (this kicks off jobs for all migrated players -- be intentional)
- Click "Make new season" to confirm

If the compat version you want isn't in the dropdown, you need to publish cogames first (see below).

**2. CLI** (local dev):

```bash
metta observatory tournament roll-season beta
metta observatory tournament roll-season beta-cogsguard --migrate-players --compat-version "0.16"
```

**3. API** (programmatic):

```
POST /tournament/seasons/{season_id}/roll
Body: {"compat_version": "0.16", "migrate_active_players": false}
```

Requires `SoftmaxUser` auth. Validates that the compat version exists in the episode runner registry.

### Updating Compat Version Without Rolling

To change the compat version on the _current_ season version (no new version created):

- **UI**: Click **"Update compat version"** on the tournament page
- **API**: `POST /tournament/seasons/{season_id}/update-current-season-compat-version` Body:
  `{"compat_version": "0.16"}`

### Publishing a New Compat Version

If the compat version you want isn't available, publish cogames first:

```bash
metta publish cogames
```

This triggers a GitHub Actions workflow that builds an episode runner image tagged `compat-v{version}`. Wait for the
build to complete (updates posted in #auto-notifications). Once built, the new version appears in the UI dropdown and
passes API validation.

Compat versions are resolved from image tags in the episode runner registry (`ghcr.io/metta-ai/episode-runner`) matching
the pattern `compat-v{major}.{minor}`.

### What Happens During a Roll

The core logic lives in `roll_season_version()` in
`app_backend/src/metta/app_backend/tournament/scripts/roll_season.py`:

1. Finds the current canonical season by name
2. Marks the old season as disabled (`disabled_at = now()`, `canonical = False`)
3. Creates a new season with `version = old + 1`, `canonical = True`, and the specified compat version
4. Copies pool structure from the old season (unless `roll_copy_existing_pools = False` on the commissioner)
5. If `migrate_members = True`: collects all active (non-retired) players across all old pools, adds them to the new
   season's entry pool, and records membership changes

## Creating a New Season Type

For a fundamentally new tournament format, you need a new commissioner class.

### Step 1: Choose a Referee Type

Check existing referees in `app_backend/src/metta/app_backend/tournament/referees/`:

| Referee              | Behavior                                     | Use when                 |
| -------------------- | -------------------------------------------- | ------------------------ |
| `SelfPlayReferee`    | Policy plays copies of itself                | Qualifying / solo eval   |
| `PairingReferee`     | All-pairs matchups with agent configurations | Head-to-head competition |
| `CvcSelfPlayReferee` | CvC variant of self-play                     | CvC qualifying           |
| `CvcPairingReferee`  | CvC variant of pairing                       | CvC competition          |

To create a custom referee, extend `RefereeBase` in `referees/base.py` and implement:

- `make_env(seed)` -- return a `MettagridEnvConfig`
- `get_matches_to_schedule(players, match_counts, limit)` -- return `list[MatchRequest]`
- `get_leaderboard(pool_id)` -- return `list[tuple[UUID, float, int]]`

### Step 2: Create the Commissioner

Create a new file in `app_backend/src/metta/app_backend/tournament/commissioners/`:

```python
from metta.app_backend.tournament.commissioners.beta import BetaCommissioner
from metta.app_backend.tournament.referees.selfplay import SelfPlayReferee
from metta.app_backend.tournament.referees.pairing import PairingReferee

class MySeasonCommissioner(BetaCommissioner):
    season_name = "my-season"
    display_name = "My Season"
    entry_pool = "qualifying"
    leaderboard_pool = "competition"
    referees = {
        "qualifying": SelfPlayReferee(),
        "competition": PairingReferee(),
    }
    summary = "Description of what this season does"
    promotion_min_score = 0.1
```

Extending `BetaCommissioner` gives you the standard qualifying-to-competition promotion flow. Override
`get_membership_changes()` or `get_new_submission_membership_changes()` for custom logic.

For version-aware referee configs (different rules per season version), override `get_referees(season_version)`.

### Step 3: Register the Season

Edit `app_backend/src/metta/app_backend/tournament/registry.py`:

```python
from metta.app_backend.tournament.commissioners.my_season import MySeasonCommissioner

_ENABLED_SEASON_COMMISSIONERS: list[type[CommissionerBase]] = [
    # ... existing commissioners ...
    MySeasonCommissioner,
]
```

The `SEASONS` dict is auto-built from this list. Seasons are auto-created in the DB when the tournament commissioner
starts (`_seed_missing_seasons()` in `cli.py`).

### Step 4: Test Locally

```bash
metta observatory up
# Wait for server to be ready, then:
metta observatory tournament run  # Runs all registered commissioners
```

Check that the season and pools were created:

```bash
docker exec app_backend-postgres-1 psql -U postgres -d metta \
  -c "SELECT name, version, canonical FROM seasons ORDER BY name"
docker exec app_backend-postgres-1 psql -U postgres -d metta \
  -c "SELECT p.name, s.name as season FROM pools p JOIN seasons s ON p.season_id = s.id"
```

## Quick Reference

| What                   | Where                                                                           |
| ---------------------- | ------------------------------------------------------------------------------- |
| Commissioner base      | `app_backend/src/metta/app_backend/tournament/commissioners/base.py`            |
| BetaCommissioner       | `app_backend/src/metta/app_backend/tournament/commissioners/beta.py`            |
| Example (CvC)          | `app_backend/src/metta/app_backend/tournament/commissioners/beta_cvc.py`        |
| Registry               | `app_backend/src/metta/app_backend/tournament/registry.py`                      |
| Referee base           | `app_backend/src/metta/app_backend/tournament/referees/base.py`                 |
| Roll season script     | `app_backend/src/metta/app_backend/tournament/scripts/roll_season.py`           |
| Roll season CLI        | `metta/setup/tools/observatory/cli.py` (`tournament roll-season`)               |
| Roll season API        | `POST /tournament/seasons/{season_id}/roll`                                     |
| Update compat API      | `POST /tournament/seasons/{season_id}/update-current-season-compat-version`     |
| UI (Make new season)   | `web/softmax.com/src/app/(observatory)/observatory/tournament/SeasonSelect.tsx` |
| Compat version images  | `app_backend/src/metta/app_backend/episode_runner_images.py`                    |
| Season versioning spec | `docs/specs/0020-season-versions.md`                                            |
| DB models              | `app_backend/src/metta/app_backend/models/tournament.py`                        |
| API routes             | `app_backend/src/metta/app_backend/routes/tournament_routes.py`                 |
| Settings               | `app_backend/src/metta/app_backend/tournament/settings.py`                      |
| Publishing cogames     | `metta/setup/tools/PUBLISHING.md`                                               |

## Integration

**Pairs with:** n.observatory-up (local dev), n.monitor-infra (production monitoring), n.debug-jobs (eval failures)
