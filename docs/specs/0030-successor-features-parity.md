# Successor-Features vs Dense-Loss Parity (metta4 + metta0)

- Status: In progress (code fixes landed; parity harness running)
- Owner: richard-successorfeatures
- Date: 2026-02-27

## Summary

This branch compares two inventory-prediction framings for CogsGuard:

1. Dense future-attribute loss (`FutureAttributePredictionLoss`, "FAP")
2. Successor-feature style horde loss (`DiffHordeLoss`, "Horde/SF v0")

Goals:

- audit dense-vs-horde implementation differences
- identify and fix runtime bugs/regressions
- run matched parity checks locally and on mettabox (`metta0`/`metta4`)

## Current Status

- Dense loss merged in PR `#6706` (`2e2f38327d`, 2026-02-07, `Al-does`).
- Horde/SF framework merged in PR `#6952` (`aa4ca026c4`, 2026-02-11), plus follow-ups:
  - `3b49517c5b` (baseline init fix)
  - `23e78483e8` (horde variants + env_info defaults)
- ViT FAP vibe-head wiring fix landed on this branch:
  - explicit vibe actor head + `vibe_in_key` wiring in `ViTFutureAttrPredConfig`

## Audit: Framing Differences

- Dense loss path:
  - recipe: `recipes.experiment.cogsguard_fap.train`
  - loss: `metta/rl/loss/future_attribute_prediction.py`
  - target: direct future inventory attribute prediction at horizon `n`
- Successor-feature path:
  - recipe: `recipes.experiment.cogsguard.train` + `horde_variants`
  - loss: `metta/rl/loss/diff_horde.py` + cumulants in `metta/rl/diff_horde/*`
  - target: cumulant/GVF-style predictions with GTD(lambda)
  - parity variants: `horde_variants=["economy_agent","vitals"]`

## Subho Notes: Stability + Next Experiments

### Observed instability

- In SF/horde sweeps, a single prediction vector mixes signals at very different scales.
- Using `gamma=1.0` to approximate horizon-sums can cause cumulative targets to blow up.
- In practice, both value predictions and differential targets can become very large.

### Immediate fixes to try

- Sweep `trainer.losses.diff_horde.gamma` below `1.0` to keep long-horizon credit assignment without unbounded sums.
- Keep/strengthen per-cumulant normalization so both very large and very small stats remain learnable and comparable.
- Evaluate engineered stabilizers (running-mean/scale normalization with clipping) where raw cumulants are heavy-tailed.
- Sweep SF loss balance and target mixes explicitly (not just one fixed setting), including `vf_coef` / `aux_coef` /
  `beta` and multiple cumulant packs.
- Consider Jetstream-style stat handling for some cumulants:
  - track running average first,
  - center to immediate variance (`x - mean`),
  - optionally extend to higher-order residual channels (turbulence/precision-style variants).

### Teacher-first evaluation plan

- Start from a teacher recipe that is already known to train reliably.
- Add SF/diff-horde targets to that same setup and measure whether SF makes results better or worse.
- Use shaped-reward-oriented targets first (including objective-mine-style shaped signals), then compare against
  baseline.
- Run role-focused checks as follow-ups (`miner`-only / `aligner`-only recipe tracks).

### First-pass sweep grid

- Hold constant: teacher config, seeds, and reward variant.
- A/B check: baseline (no SF) vs `diff_horde` enabled on the same recipe.
- Discount sweep: start with `gamma in {0.99, 0.995, 0.9975}` (and optionally `lambda in {0.90, 0.95}`).
- Stabilization sweep: compare `cumulant_centering=none` vs `ema`, and clip ranges for RMS normalization.
- Target sweep:
  - preset packs from `_HORDE_VARIANT_SPECS` (for example `economy_agent+vitals`, then event/flow-heavy packs),
  - objective reward mine shaping via `variants=["milestones_2"]` or `variants=["milestones_2:<factor>"]` paired with SF
    cumulants that track those shaped stats.
- Role-focused follow-up: validate best settings on miner/aligner tracks to verify role-local benefit.
- Success bar: SF run should outperform the matched teacher baseline on the same progress metric.

### Target space notes

- `horde_variants` in CogsGuard (from `_HORDE_VARIANT_SPECS`) is a curated set, not an exhaustive space.
- Additional cumulants can be declared via `diff_horde_cumulants` using:
  - `info_scalar`
  - `env_obs_feature`
  - `td_key`
- Any meaningful TensorDict key added during rollout/policy forward can be a candidate SF cumulant target, including
  world-model-style prediction signals.

## Bugs Found And Fixed

### 1) Missing vibe actor log-prob in FAP recipe (fixed)

Symptom:

- `cogsguard_fap.train` could crash with:
  - `PPOActor[vibe] expected policy_td['vibe_act_log_prob'], but it was missing.`

Root cause:

- vibe actor wiring was missing for some architectures when vibe actions are present.

Fix:

- added explicit vibe actor wiring in `vit_future_attr_pred.py`
- added regression coverage in `tests/rl/test_losses.py`

## Validation (Local)

- `ruff check` on touched files
- `pytest -q tests/rl/test_losses.py -k 'vibe or autowire'`
- previously completed local parity/profiling no-eval runs:
  - `parity_local_generic_fap_noeval`
  - `parity_local_generic_horde_noeval`

## metta0 Sequential Parity Harness (completed)

Runs were executed one-at-a-time with matched config:

Dense (FAP):

```bash
uv run ./tools/run.py recipes.experiment.cogsguard_fap.train \
  run=parity_m0_cpu_fap_v1 \
  system.device=cpu \
  training_env.vectorization=serial training_env.num_workers=1 \
  trainer.bptt_horizon=8 trainer.minibatch_size=4096 trainer.batch_size=32768 \
  trainer.total_timesteps=98304 \
  checkpointer.epoch_interval=1 evaluator.epoch_interval=0 'evaluator.simulations=[]'
```

Horde (SF):

```bash
uv run ./tools/run.py recipes.experiment.cogsguard.train \
  run=parity_m0_cpu_horde_v1 \
  system.device=cpu \
  training_env.vectorization=serial training_env.num_workers=1 \
  trainer.bptt_horizon=8 trainer.minibatch_size=4096 trainer.batch_size=32768 \
  trainer.total_timesteps=98304 \
  checkpointer.epoch_interval=1 evaluator.epoch_interval=0 'evaluator.simulations=[]' \
  'horde_variants=["economy_agent","vitals"]'
```

Observed metta0 parity signal:

- FAP (`parity_m0_cpu_fap_v1`):
  - epoch 1: `1.14 ksps`, `aligned.junction.held=0.000`
  - epoch 2: `1.33 ksps`, `aligned.junction.held=0.000`
  - epoch 3: `1.31 ksps`, `aligned.junction.held=0.000`
- Horde (`parity_m0_cpu_horde_v1`):
  - epoch 1: `2.53 ksps`, `aligned.junction.held=0.000`
  - epoch 2: `4.76 ksps`, `aligned.junction.held=0.000`
  - epoch 3: `4.76 ksps`, `aligned.junction.held=0.000`

Interpretation:

- both framings run end-to-end under a matched metta0 harness
- horde is faster in this setup (smaller parameter count and loss path)
- early-epoch task metric (`aligned.junction.held`) is parity-flat (`0.000`) for both at this short horizon

## metta4 Parity Commands (full-size)

```bash
./devops/mettabox/cli.py run metta4 -- \
  recipes.experiment.cogsguard_fap.train \
  run=parity_m4_fap_dense_v1 \
  trainer.total_timesteps=5000000 \
  'evaluator.simulations=[]'
```

```bash
./devops/mettabox/cli.py run metta4 -- \
  recipes.experiment.cogsguard.train \
  run=parity_m4_horde_sf_v1 \
  trainer.total_timesteps=5000000 \
  'evaluator.simulations=[]' \
  'horde_variants=["economy_agent","vitals"]'
```
