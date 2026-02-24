# CogsGuard Role Specialists Runbook (branch: `richard-trained224`)

This runbook documents the reproducible command loop for Phase 1 (isolated role training) and Phase 2 transfer checks
for `miner`, `scout`, `aligner`, and `scrambler`.

## What this branch now has

- `tools/run.py` role tools: `cogsguard.miner`, `cogsguard.scout`, `cogsguard.aligner`, `cogsguard.scrambler`,
  `cogsguard.evaluate`, `cogsguard.play`, `cogsguard.replay`.
- Scrambler tutorial mission is registered in the core mission list and discoverable via `cogames missions`.
- Scout role isolation now also disables `change_vibe` (matching miner/aligner role-isolation assumptions).
- Mixed-policy eval supports fixed `assignments` for role lineup tests.
- No duplicate role tutorial mission definitions were found; each role tutorial resolves to a single mission source.

## Quickstart demo (validated on this branch)

```bash
./tools/run.py cogsguard --list
uv run cogames missions cogsguard_arena
uv run cogames describe cogsguard_arena.scrambler_tutorial
```

### Phase 1 train command per role (repro contract)

Use one command per role from a clean checkout:

```bash
./tools/run.py cogsguard.miner run=rs_miner_v1 trainer.total_timesteps=100000000 system.device=cuda
./tools/run.py cogsguard.scout run=rs_scout_v1 trainer.total_timesteps=100000000 system.device=cuda
./tools/run.py cogsguard.aligner run=rs_aligner_v1 trainer.total_timesteps=100000000 system.device=cuda
./tools/run.py cogsguard.scrambler run=rs_scrambler_v1 trainer.total_timesteps=100000000 system.device=cuda
```

### Phase 1 eval command per role (Track A no-clips)

```bash
./tools/run.py cogsguard.evaluate run=rs_eval_miner_track_a \
  'policy_uris=["file://./train_dir/rs_miner_v1/checkpoints"]' \
  'variants=["no_clips","no_objective","miner"]' layout=machina_1

./tools/run.py cogsguard.evaluate run=rs_eval_scout_track_a \
  'policy_uris=["file://./train_dir/rs_scout_v1/checkpoints"]' \
  'variants=["no_clips","no_objective","scout"]' layout=machina_1

./tools/run.py cogsguard.evaluate run=rs_eval_aligner_track_a \
  'policy_uris=["file://./train_dir/rs_aligner_v1/checkpoints"]' \
  'variants=["no_clips","no_objective","aligner"]' layout=machina_1

./tools/run.py cogsguard.evaluate run=rs_eval_scrambler_track_a \
  'policy_uris=["file://./train_dir/rs_scrambler_v1/checkpoints"]' \
  'variants=["no_clips","no_objective","scrambler"]' layout=machina_1
```

### Phase 2 transfer check (Track B, mixed team with clips enabled)

```bash
./tools/run.py cogsguard.evaluate run=rs_eval_transfer_v1 \
  'policy_uris=["file://./train_dir/rs_miner_v1/checkpoints","file://./train_dir/rs_scout_v1/checkpoints","file://./train_dir/rs_aligner_v1/checkpoints","file://./train_dir/rs_scrambler_v1/checkpoints"]' \
  'assignments=[0,0,1,1,2,2,3,3]' \
  shuffle_assignments=false \
  layout=machina_1
```

## Scripted + trained combinability demo

```bash
./tools/run.py cogsguard.play policy_uri=metta://policy/role layout=machina_1
./tools/run.py cogsguard.replay policy_uri=metta://policy/role layout=machina_1
```

For mixed teams, use `cogsguard.evaluate` with multiple `policy_uris` and either fixed `assignments` or `proportions`.

For local checkpoint eval on this branch, isolated policy-server mode is now stable with compact policy-server mapping
(one server per referenced policy index, not per agent). For faster local iteration, you can still disable isolated
venvs:

```bash
EPISODE_RUNNER_USE_ISOLATED_VENVS=0 ./tools/run.py cogsguard.evaluate \
  'policy_uris=["file://./train_dir/rs_miner_v1/checkpoints"]' \
  max_workers=1 system.device=cpu
```

Reason: isolated policy-server venv bootstrapping is still expensive; disabling isolated venvs speeds local iteration.

## Platform notes

- WSL2 (Windows, RTX 2080/5080): use `system.device=cuda` and run from Linux shell in WSL2.
- 4090 (Marty): same commands as above, set run IDs with a machine suffix (for example `rs_miner_v1_marty4090`).
- Conda: create env, install `uv`, then run the same commands.
- Mac long-run: use `system.device=mps` (or `cpu` if needed) and launch in `tmux`/`screen`.

Example conda setup:

```bash
conda create -n metta python=3.11 -y
conda activate metta
pip install uv
uv sync
```

Example mac long-run wrapper:

```bash
tmux new -s rs_miner
./tools/run.py cogsguard.miner run=rs_miner_v1_mac trainer.total_timesteps=100000000 system.device=mps
```

## Validation commands used for this doc

These were run on this branch to confirm command surfaces are valid:

```bash
./tools/run.py cogsguard.miner --dry-run run=rs_doc_check_miner trainer.total_timesteps=100000 wandb.enabled=false system.device=cpu
./tools/run.py cogsguard.scout --dry-run run=rs_doc_check_scout trainer.total_timesteps=100000 wandb.enabled=false system.device=cpu
./tools/run.py cogsguard.aligner --dry-run run=rs_doc_check_aligner trainer.total_timesteps=100000 wandb.enabled=false system.device=cpu
./tools/run.py cogsguard.scrambler --dry-run run=rs_doc_check_scrambler trainer.total_timesteps=100000 wandb.enabled=false system.device=cpu
./tools/run.py cogsguard.evaluate --dry-run 'policy_uris=["file://./train_dir/rs_miner/checkpoints","file://./train_dir/rs_scout/checkpoints","file://./train_dir/rs_aligner/checkpoints","file://./train_dir/rs_scrambler/checkpoints"]' 'assignments=[0,0,1,1,2,2,3,3]' shuffle_assignments=false layout=machina_1
```

## Known remaining gaps

- No CI lane yet for WSL2-specific validation.
- No repo-managed conda environment file yet; conda flow is documented but not CI-enforced.
- Long-running stability on macOS needs a dedicated soak run and artifact log.
- Isolated local eval now avoids per-agent policy-server process explosion; remaining cost is cold-start venv setup
  time.
