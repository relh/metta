# Branch + Doc Audit: `richard-trained224` (2026-02-24)

## Branch hygiene (vs `origin/main`)

- Merge-base with `origin/main`: `7b935d9f2cd170d8adfa7ed6389f69bb40a13de7`
- Commits ahead of `origin/main` at audit start: 3 (`5eaaa9ace0`, `71f4e10b14`, `3475381309`)
- Scope is now committed and pushed on `richard-trained224`.

### Changed files in scope

- `packages/cogames/src/cogames/games/cogs_vs_clips/missions.py`
- `packages/cogames/tests/test_cli.py`
- `recipes/experiment/cogsguard.py`
- `packages/mettagrid/python/src/mettagrid/runner/policy_server/manager.py`
- `packages/mettagrid/python/src/mettagrid/runner/episode_runner.py`
- `packages/mettagrid/tests/runner/test_episode_runner.py`
- `docs/experiments/cogsguard_role_specialists_runbook_2026-02-24.md`
- `docs/ai/cogsguard-role-specialists-pr-update-2026-02-24.md`
- `docs/ai/cogsguard-role-specialists-branch-audit-2026-02-24.md`

## Cool/cleanup refactor results

### 1) Duplicate role-training setup removed

`recipes/experiment/cogsguard.py` had repeated role setup blocks across `miner/scout/aligner/scrambler` (teacher
normalization, curriculum/buckets, tool wiring, scheduler wiring).

Refactor landed:

- `_resolve_role_teacher(...)`
- `_make_role_train_tool(...)`

This removes duplicated wiring while preserving role-specific mission/env logic and metrics.

### 2) Root-cause scout training gap fixed

Real scout smoke run exposed runtime failure:

- `ValueError: Expected action column 1, but action shape is (64, 1)`

Fix landed:

- In scout role setup, disable `change_vibe` during Phase 1 isolation (consistent with miner/aligner).

### 3) Mission registration gap fixed

- `scrambler_tutorial` now registered in core missions and visible in `cogames missions`.

### 4) Regression coverage added

- `packages/cogames/tests/test_cli.py` now asserts `cogsguard_arena.scrambler_tutorial` appears for site mission
  listing.

### 5) Episode runner gap closed (where possible)

`run_episode_isolated` previously expanded to one local policy server per agent, which inflated process count and caused
unstable/slow local eval behavior under isolated policy-server mode.

Fix landed:

- Compact mapping now launches one server per referenced policy index (preserving assignment semantics).
- Per-agent policy-log artifacts remain compatible by copying compacted server logs back out per agent index.
- Added runner tests for compact remapping semantics and validation:
  - `packages/mettagrid/tests/runner/test_episode_runner.py`

## Doc audit results

### Added/updated docs

- New runbook with branch-validated commands:
  - `docs/experiments/cogsguard_role_specialists_runbook_2026-02-24.md`
- PR body/update draft:
  - `docs/ai/cogsguard-role-specialists-pr-update-2026-02-24.md`

### Duplication findings

- No duplicate role tutorial mission definitions found in `cogames/games/cogs_vs_clips`.
- Role tutorial mission source-of-truth is singular per role.

### Command quality findings

- Existing docs were updated to avoid unsupported argument examples (notably replay with `max_steps`).
- Local checkpoint eval has environment bootstrap caveats documented.

## Command audit matrix

### Passed

- `./tools/run.py cogsguard --list`
- `uv run cogames missions cogsguard_arena`
- `uv run cogames describe cogsguard_arena.scrambler_tutorial`
- Dry-runs for `cogsguard.miner/scout/aligner/scrambler`
- Dry-runs for `cogsguard.evaluate` role and mixed-assignment shapes
- `uv run pytest packages/cogames/tests/test_cli.py -q` (`12 passed`)
- Real small smoke trains (CPU, reduced batch/timesteps): miner/scout/aligner/scrambler

### Remaining risk / open issue

- Isolated local eval no longer fans out policy servers per agent, but cold-start venv setup remains expensive.
- For faster local iteration, `EPISODE_RUNNER_USE_ISOLATED_VENVS=0` is still a practical speed optimization.

## PR linkage status

- PR created: <https://github.com/Metta-AI/metta/pull/7966>
