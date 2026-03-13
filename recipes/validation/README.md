# Recipe Validation

### Two-Tier Testing System

**CI Suite** (`ci_suite.py`) - Fast smoke tests

- **Purpose**: Verify recipes don't crash, not performance
- **Runs**: On every commit (will run on GitHub pre-merge soon)
- **Characteristics**: 10k timesteps, 5-minute timeouts, runs locally
- **Run with**: `metta ci recipe-tests`

**Stable Suite** (`stable_suite.py`) - Performance validation

- **Purpose**: Track end-to-end performance (SPS, learning outcomes)
- **Runs**: During releases on remote infrastructure
- **Characteristics**: 100M-2B timesteps, multi-GPU (1-16), acceptance criteria for metrics
- **Run with**: Part of release automation (or manually via job runner tools)

### Training Compat Baselines

Stable training SPS gates are sourced from `TRAINING_COMPAT_VERSION` plus
`common/src/metta/common/training_compat.py`.

Each training compat entry records:

- the known-good training commit
- the env compat version it was audited against
- the expected SPS floor for each audited stable training job

PRs that touch training or env compat code without bumping `TRAINING_COMPAT_VERSION` get a reminder from
`.github/workflows/training-compat-version-reminder.yml`.

If training performance changes intentionally, bump the training compat version and update that baseline in the same
change.

### When Adding a Prod Recipe

Add **both** test types to your recipe:

1. **CI test** in `ci_suite.py`: Minimal smoke test (just verify it runs)
2. **Stable test** in `stable_suite.py`: Full training run with performance criteria

### Quick Commands

```bash
metta ci recipe-tests

# Run stable suite validation (performance tests on remote infrastructure)
python devops/stable/stable.py validate

# Run stable validation with job filtering
python devops/stable/stable.py validate --job "arena*"
```
