# PR Update: CogsGuard Role Specialist Baselines

## Summary

This update closes the main reproducibility gap for role-specialist workflows and adds a branch runbook with verified
commands.

## Fixes landed

1. Registered `scrambler_tutorial` in the core mission registry.
2. Added a branch-specific runbook with one train command and one eval command per role.
3. Added mixed-team transfer eval command using fixed `assignments` for role composition tests.
4. Corrected replay invocation guidance to match current `cogsguard.replay` args.
5. Audited duplicate mission wiring for role tutorials; no duplicate role mission definitions remain.
6. Refactored duplicated role training setup in `recipes/experiment/cogsguard.py` into shared helpers
   (behavior-preserving cleanup).
7. Fixed scout Phase 1 role-isolation gap by disabling `change_vibe` (resolves real scout smoke-run crash).
8. Hardened isolated policy-server venv dependency install for checkpoint eval (`safetensors`, `packaging`,
   `tensordict`, `torchrl`, `einops`).
9. Closed the remaining runner gap by compacting isolated policy-server launches to one server per referenced policy
   index (instead of one per agent), while preserving per-agent policy-log artifacts.

## Files changed

- `packages/cogames/src/cogames/cogs_vs_clips/missions.py`
- `packages/mettagrid/python/src/mettagrid/runner/episode_runner.py`
- `packages/mettagrid/tests/runner/test_episode_runner.py`
- `docs/experiments/cogsguard_role_specialists_runbook_2026-02-24.md`
- `docs/ai/cogsguard-role-specialists-branch-audit-2026-02-24.md`
- `docs/ai/cogsguard-role-specialists-pr-update-2026-02-24.md`

## Verification run

- `./tools/run.py cogsguard --list` succeeded; role tools present.
- `uv run cogames missions cogsguard_arena` now includes `cogsguard_arena.scrambler_tutorial`.
- `uv run cogames describe cogsguard_arena.scrambler_tutorial` succeeds.
- Dry-run validation succeeded for:
  - `cogsguard.miner`, `cogsguard.scout`, `cogsguard.aligner`, `cogsguard.scrambler`
  - `cogsguard.evaluate` with per-role Track A variants
  - `cogsguard.evaluate` with mixed-policy `assignments=[0,0,1,1,2,2,3,3]`
  - `cogsguard.play` and `cogsguard.replay`
- Real smoke trains succeeded (`trainer.total_timesteps=256`, reduced batch settings) for:
  - `rs_miner_smoke_real_20260224`
  - `rs_scout_smoke_real_fix_20260224` (after scout isolation fix)
  - `rs_aligner_smoke_real_20260224`
  - `rs_scrambler_smoke_real_20260224`

## Remaining gaps (explicit)

- WSL2 (2080/5080) and macOS soak validation are documented but not yet CI-covered.
- Conda setup is documented, but there is no checked-in conda env file yet.
- Isolated local eval now avoids policy-server fanout; remaining limitation is cold-start venv install overhead.
- `EPISODE_RUNNER_USE_ISOLATED_VENVS=0` remains a speed optimization for local iteration, not a correctness workaround.
- PR created: <https://github.com/Metta-AI/metta/pull/7966>
