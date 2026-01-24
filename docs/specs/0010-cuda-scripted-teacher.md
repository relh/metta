# CUDA Scripted Teacher (Thinky)

> **Status:** Draft **Author:** relh **Created:** 2026-01-20

## Summary

Move scripted teacher inference out of env processes into a CUDA batch in the trainer. This lets us generate actions for
all agents without the current SPS penalty.

Thinky is our in-repo scripted policy (Nim) and the default teacher:

- Core logic: `packages/cogames-agents/src/cogames_agents/policy/nim_agents/thinky_agents.nim`
- Python wrapper + short name `thinky`: `packages/cogames-agents/src/cogames_agents/policy/nim_agents/agents.py`

## Getting started (example commands)

### Thinky teacher (behavioral cloning)

```
uv run ./tools/run.py recipes.experiment.machina_1.train \
  run=relh.machina1_cloner.120.teacherbc.1 \
  teacher.policy_uri=metta://policy/thinky \
  teacher.mode=sliced_cloner \
```

### PPO only (no teacher)

```
uv run ./tools/run.py recipes.experiment.machina_1.train \
  run=relh.machina1_ppo_only.120 \
```

## Problem

We currently use **thinky** as a behavioral cloning teacher via the env-side supervisor path. This drops SPS to ~20k vs
100k+ for PPO-only runs.

Why this is slow:

- The supervisor policy runs **inside every env process** on each step.
- With multiprocessing vectorization, that means many policy instances.
- Scripted policies are CPU-heavy (branchy logic, pathfinding, map bookkeeping), so they don’t scale with the number of
  parallel envs.

For the exact machina_1 command above (defaults for `machina_1.train`), the environment math is:

```
target_batch_size = forward_pass_minibatch_target_size / num_agents
batch_size = floor(target_batch_size / num_workers) * num_workers
num_envs = batch_size * async_factor
```

With defaults (`num_cogs=4` ⇒ `num_agents=4`, `forward_pass_minibatch_target_size=4096`, `async_factor=2`), this
becomes: `target_batch_size=1024`, `batch_size=floor(1024 / num_workers) * num_workers`, `num_envs=2 * batch_size`.

Examples (deterministic given `num_workers`):

- If `num_workers=1` (serial): `batch_size=1024`, `num_envs=2048`
- If `num_workers=8`: `batch_size=1024`, `num_envs=2048`
- If `num_workers=24`: `batch_size=1008`, `num_envs=2016`

Total agent slots per step is `num_envs * num_agents`, so for the above:

- `2048 * 4 = 8192` agents (num_workers=1 or 8)
- `2016 * 4 = 8064` agents (num_workers=24)

This is the scale at which the scripted teacher runs each step in the current env-side supervisor path.

## Solution

Refactor teacher supervision into a **pluggable teacher action provider** that supports both:

- **Legacy env-side supervision** (current path via `supervisor_policy_uri`)
- **Trainer-side CUDA supervision** (new path, single GPU batch across all envs)

This makes the supervision mechanism explicit, testable, and extensible, while keeping existing teacher losses
unchanged.

Key changes:

1. Add a teacher action provider interface (env-side + trainer-side).
2. Keep the legacy env-side path unchanged.
3. Add a CUDA teacher runner and wire it into rollout so `teacher_actions` is filled without touching env processes.

## Goals

- [ ] Teacher actions computed in a single GPU batch per rollout step.
- [ ] Works across all parallel envs and agents in training.
- [ ] No changes required in teacher loss implementations.
- [ ] Clear opt-in flag to use trainer-side CUDA teacher vs env-side supervisor.

## Non-Goals

- Rewriting Thinky’s internal logic in this spec (only the integration).
- Tuning or redesigning training recipes beyond the teacher wiring.

## Design

### Current wiring (env-side supervisor)

1. `TeacherConfig` sets `training_env.supervisor_policy_uri` (`metta/rl/training/teacher.py`).
2. `TrainTool` resolves the policy URI into a `PolicySpec` (`metta/tools/train.py`).
3. `VectorizedTrainingEnvironment` creates `MettaGridPufferEnv` with a `supervisor_policy_spec` (`metta/rl/vecenv.py`).
4. `MettaGridPufferEnv` calls `supervisor.step_batch(raw_observations, teacher_actions)` every step
   (`packages/mettagrid/python/src/mettagrid/envs/mettagrid_puffer_env.py`).

### Proposed wiring (pluggable teacher action providers)

Introduce a small interface that returns `teacher_actions` from raw observations, with two implementations:

1. **EnvSupervisorProvider** (legacy)
   - Uses `supervisor_policy_uri` and the existing env-side path.
   - No behavior change; this remains the default.

2. **CudaTeacherProvider** (new)
   - Runs in the trainer process.
   - Executes a CUDA scripted policy over the full rollout batch.

**New module (suggestion):**

- `metta/rl/training/cuda_teacher.py`

**API shape (example):**

We already have a `step_batch` fast-path on `MultiAgentPolicy` (`mettagrid/policy/policy.py`) that the env-side
supervisor uses today. The CUDA teacher should align with that interface rather than inventing a new `step_batch_torch`
entry point.

**Inputs/outputs:**

- `raw_observations`: `uint8` tokens (shape `[N, num_tokens, token_dim]`)
- `raw_actions`: `int64/long` actions (shape `[N]`, filled in-place)

**Rollout integration:**

In `metta/rl/training/core.py` (rollout), delegate to the active provider. For the CUDA provider, the rollout loop
should populate a raw action buffer and call `step_batch` on the teacher policy, mirroring the existing supervisor path.

Everything else (losses, logging) remains unchanged.

### Early testing path (not for throughput)

For early validation of a CUDA implementation, you can implement `thinky_cuda` as a `MultiAgentPolicy` and wire it as
`supervisor_policy_uri` (keeping the existing supervisor wiring unchanged).

This is risky because:

- Every worker process loads a CUDA policy.
- CPU<->GPU transfers happen in each process.
- GPU contention increases with the number of workers.

This only works well if:

- `vectorization="serial"` and `num_workers=1`, or
- you shard workers across multiple GPUs.

## Open Questions

1. What is the exact URI for the thinky policy (`metta://policy/thinky` or versioned)?
2. Do we want a config flag under `TeacherConfig` or under `TrainingEnvironmentConfig` to enable trainer-side CUDA
   teacher?
3. Which implementation path should be preferred: CUDA extension, Triton, or both (for fast iteration vs. performance)?
