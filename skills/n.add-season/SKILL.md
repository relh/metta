---
name: n.add-season
description:
  Use when adding a new tournament season, creating a new commissioner, or setting up new referees for the Observatory
  tournament system. Also use when asked to roll a season version or change the default season.
---

# Add Tournament Season

**Announce at start:** "Adding a new tournament season. Checking existing commissioners and referees for patterns."

## Overview

A tournament season requires a Commissioner (manages membership/promotion) and Referees (schedule matches and score).
The commissioner auto-creates DB records on first run -- no migrations needed.

## Step 1: Choose a Referee Type

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

## Step 2: Create the Commissioner

Create a new file in `app_backend/src/metta/app_backend/tournament/commissioners/`:

```python
from metta.app_backend.tournament.commissioners.beta import BetaCommissioner
from metta.app_backend.tournament.referees.selfplay import SelfPlayReferee
from metta.app_backend.tournament.referees.pairing import PairingReferee

class MySeasonCommissioner(BetaCommissioner):
    season_name = "my-season"
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

## Step 3: Register the Season

Edit `app_backend/src/metta/app_backend/tournament/registry.py`:

```python
from metta.app_backend.tournament.commissioners.my_season import MySeasonCommissioner

SEASONS["my-season"] = MySeasonCommissioner

# Optional: hide from public listing
HIDDEN_SEASONS.append("my-season")

# Optional: set as default
DEFAULT_SEASON = "my-season"
```

## Step 4: Test Locally

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

| What                   | Where                                                                    |
| ---------------------- | ------------------------------------------------------------------------ |
| Commissioner base      | `app_backend/src/metta/app_backend/tournament/commissioners/base.py`     |
| BetaCommissioner       | `app_backend/src/metta/app_backend/tournament/commissioners/beta.py`     |
| Example (CvC)          | `app_backend/src/metta/app_backend/tournament/commissioners/beta_cvc.py` |
| Registry               | `app_backend/src/metta/app_backend/tournament/registry.py`               |
| Referee base           | `app_backend/src/metta/app_backend/tournament/referees/base.py`          |
| Roll season script     | `app_backend/src/metta/app_backend/tournament/scripts/roll_season.py`    |
| Season versioning spec | `docs/specs/0020-season-versions.md`                                     |
| DB models              | `app_backend/src/metta/app_backend/models/tournament.py`                 |
| API routes             | `app_backend/src/metta/app_backend/routes/tournament_routes.py`          |
| Settings               | `app_backend/src/metta/app_backend/tournament/settings.py`               |

## Integration

**Pairs with:** n.observatory-up (local dev), n.monitor-infra (production monitoring), n.debug-jobs (eval failures)
