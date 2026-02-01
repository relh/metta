# Season Versions

> **Status:** Implemented **Author:** Nishad **Created:** 2026-01-28

## Summary

Seasons can be versioned to handle game rule changes while preserving identity and historical data.

## Problem

Game rules change frequently during beta (e.g., beta-cogsguard), making results non-comparable across rule changes. We
need to roll seasons to new versions when rules change significantly, while preserving season identity, membership
continuity, and historical data access.

## Solution

Add `version`, `canonical`, and `disabled_at` fields to Season. When rules change, run a roll script that:

1. Disables the old season and removes its canonical flag
2. Creates a new season with incremented version and canonical=true
3. Copies pool structure and active memberships to the new version

Users access seasons by name (resolves to canonical) or `name:vN` syntax for specific versions.

## Goals

- [x] Roll a season to a new version when game rules change
- [x] Preserve season identity (name, membership continuity) across versions
- [x] Keep historical data accessible but clearly separated
- [x] Default to showing "current" version while allowing historical access

## Non-Goals

- Automatic version roll detection based on game config changes
- Capturing game state reference (git SHA, config hash) with each version

## Design

### Data Model

```
Season:
  id: UUID (primary key)
  name: str
  version: int (default 1)
  canonical: bool (default false)
  disabled_at: timestamp | null (default null)

  # unique constraint on (name, version)
  # partial unique index: (name) WHERE canonical = TRUE
```

- `version`: Integer starting at 1, increments on each roll
- `canonical`: Exactly one season per name can be canonical (enforced by partial unique index)
- `disabled_at`: When non-null, prevents new memberships and scheduler skips this season

Pool/Membership schemas unchanged. Data naturally partitions by version through `season_id`.

### Name Resolution

```python
def resolve_season(name: str, version: int | None = None) -> Season:
    if version is not None:
        return get_season(name=name, version=version)
    else:
        return get_season(name=name, canonical=True)
```

- `beta-cogsguard` resolves to canonical version
- `beta-cogsguard:v2` resolves to version 2
- CLI/API layer parses the `:vN` suffix at the boundary

### Roll Script

Location: `app_backend/tournament/scripts/roll_season.py`

1. Find canonical season for the name
2. In a transaction: disable old season, remove canonical flag from old season, create new season with incremented
   version and canonical=true
3. Copy pool structure to new season
4. Copy active memberships to new pools

### API/CLI

- `GET /seasons/{name}` resolves to canonical
- `GET /seasons/{name}:v2` resolves to version 2
- `GET /seasons/{name}/versions` lists all versions
- `cogames leaderboard beta-cogsguard` shows canonical
- `cogames leaderboard beta-cogsguard:v2` shows version 2
- `cogames seasons beta-cogsguard --versions` lists versions

### Migration

1. Add `version` (int, default 1), `canonical` (bool, default false), `disabled_at` (timestamp, nullable)
2. Drop existing unique constraint on `name`
3. Add unique constraint on `(name, version)`
4. Add partial unique index on `(name) WHERE canonical = TRUE`
5. Backfill: set `canonical = TRUE` for all existing seasons
