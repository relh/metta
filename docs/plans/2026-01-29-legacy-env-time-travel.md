# Legacy Env Time-Travel Investigation (Temporary)

Goal: track when legacy environments/policies broke and what changed.

## Recipe CI timeline (arena_basic_easy_shaped)

- 2025-12-12: `74605ddff4` ("New stable-release and ci recipe runner") adds `@ci_job` hooks to arena CI helpers.
- 2025-12-17: arena CI stopped being run via recipe CI:
  - `47dfa73c8c` removes `@ci_job` from `train_ci` in `recipes/prod/arena_basic_easy_shaped.py`.
  - `f461b0676f` removes `@ci_job` from `evaluate_ci` in `recipes/prod/arena_basic_easy_shaped.py`.
- 2026-01-28: `377b3e7cf8` ("prune legacy recipe CI") switches recipe tests to a minimal smoke job and adds
  `recipes/experiment/ci.py:play_smoke`, which still uses `arena_basic_easy_shaped` via `arena.mettagrid()`.

## Arena breakpoints

- 2026-01-29: `897a489d35` changes reward config to the GameValue system.
  - Old configs using `game.agent.rewards.inventory` / `inventory_max` no longer match the new shape
    (`game.agent.rewards.{item}.weight` / `.max`).

## CvC (pre-cogsguard) breakpoints

- 2026-01-21: `8f622210b5` removes the clipper system and clipping missions/variants.
- 2026-01-22: `80e23d746c` removes `hello_world_unclip` from `DEFAULT_CURRICULUM_MISSIONS`.

## Open questions / follow-ups

- Confirm the exact CI failure that triggered the 2025-12-17 arena CI removal (CI logs or local replay).
- Decide whether a time-travel shim needs to snapshot mettagrid + configs, or adapt old configs into new schemas.

## Suspects around the 2025-12-17 arena CI removal

- 2025-12-17: `17e75c92dd` raises `TrainerConfig.batch_size` default to 2,097,152 and `bptt_horizon` to 256. The old
  `train_ci()` did not override `batch_size` / `minibatch_size`, so this likely made the CI recipe too heavy
  (memory/time) for the 5-minute job timeout and could explain why it was removed.
- 2025-12-16/17: `d33ce10428` refactors minibatch sampling + forward pass into core training loop. Potentially changed
  performance/memory behavior for tiny smoke runs.

## Time-travel CLI wiring (draft)

- Added `--game-version/--game_version` to `tools/run.py` (via `metta.common.tool.run_tool`).
- Added `--game-version/--game_version` to `cogames` CLI (via `packages/cogames/src/cogames/main.py`).
- Accepts either a git commit hash or an alias:
  - `arena_basic_easy_shaped` / `arena_basic_easy_shaped_last_good`
  - `cvc_pre_cogsguard` / `cogs_v_clips_pre_cogsguard`
- Aliases are configured via env vars: `METTA_GAME_VERSION_<ALIAS>` (uppercased, non-alnum -> `_`). Example:
  `METTA_GAME_VERSION_ARENA_BASIC_EASY_SHAPED_LAST_GOOD=deadbeef`.
- Current best-candidate defaults:
  - `arena_basic_easy_shaped_last_good` -> `964e50e1beb6b06afdc295126fcbedacf8a55142`
  - `cvc_pre_cogsguard` -> `dd7179580e82781eba528461db0f0c9b770ac3a1`
