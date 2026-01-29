# Debugging MPS + Multiprocessing on macOS

This branch enables MPS device selection for training, but macOS currently forces **serial** environment stepping in a
few places. If you want to try multiprocessing on MPS and debug the bottleneck, this guide summarizes where the guards
live and how to experiment safely.

## Where serial is forced today

### Cogames CLI path

`packages/cogames/src/cogames/train.py`

- macOS always forces `pvector.Serial`:
  - `if platform.system() == "Darwin": ... backend = pvector.Serial`
- Non-CUDA devices force serial:
  - `if backend is pvector.Multiprocessing and device.type != "cuda": backend = pvector.Serial; num_workers = 1`

This means MPS always uses serial stepping in cogames training today.

### Metta tools path

`metta/rl/system_config.py` and `metta/rl/training/training_environment.py`

- Default vectorization is `serial` on macOS.
- `TrainingEnvironmentConfig.vectorization` defaults to `serial` unless explicitly overridden.

## Sanity checks (MPS availability)

```bash
python - <<'PY'
import torch
mps_backend = getattr(torch.backends, "mps", None)
print("mps built:", mps_backend.is_built() if mps_backend else False)
print("mps available:", mps_backend.is_available() if mps_backend else False)
print("device:", torch.device("mps") if mps_backend and mps_backend.is_available() else "cpu")
PY
```

## Cogames CLI experiment (current behavior)

On this branch, MPS requests use multiprocessing on macOS (CUDA and MPS are allowed). Run with explicit worker/env
counts:

```bash
cogames train -m training_facility_1 --device mps --num-workers 4 --parallel-envs 64
```

If this crashes or hangs, try:

- Fewer envs/workers: `--num-workers 1 --parallel-envs 8`
- Force serial to compare: `--num-workers 1 --parallel-envs 64`

### Timing sanity check (macOS, single run)

Commands (same params, 50k steps):

```bash
/usr/bin/time -p cogames train -m cogsguard_arena.basic \
  --device mps --num-workers 2 --parallel-envs 8 --vector-batch-size 8 \
  --batch-size 256 --minibatch-size 256 --steps 50000

/usr/bin/time -p cogames train -m cogsguard_arena.basic \
  --device cpu --num-workers 2 --parallel-envs 8 --vector-batch-size 8 \
  --batch-size 256 --minibatch-size 256 --steps 50000
```

Observed wall clock (includes startup, single run):

50k steps:

- MPS + multiprocessing: `real 11.60s`
- CPU (serial): `real 6.56s`

1M steps:

- MPS + multiprocessing: `real 105.95s`
- CPU (serial): `real 63.27s`

1M steps @ 1024 envs:

- MPS + multiprocessing: `real 90.29s`
- CPU (serial): `real 98.58s`

10M steps @ 1024 envs:

- MPS + multiprocessing: `real 630.84s`
- CPU (serial): `real 633.04s`

1M steps @ 1024 envs (Machina1 map, 8 cogs):

- MPS + multiprocessing: `real 97.02s`
- CPU (serial): `real 113.81s`

### Fittable env counts (macOS, short run)

Short smoke (200 steps, same flags, `--num-workers 2`, `--vector-batch-size` set to `--parallel-envs`). Both MPS and CPU
completed up through 1024 parallel envs on this machine.

Observed wall clock (single run, includes startup):

| Parallel envs | MPS + multiprocessing | CPU (serial)  |
| ------------- | --------------------- | ------------- |
| 8             | `real 6.49s`          | `real 4.51s`  |
| 32            | `real 7.50s`          | `real 5.87s`  |
| 64            | `real 9.61s`          | `real 7.30s`  |
| 128           | `real 12.61s`         | `real 10.59s` |
| 256           | `real 16.69s`         | `real 17.39s` |
| 512           | `real 27.81s`         | `real 30.79s` |
| 1024          | `real 60.21s`         | `real 62.50s` |

## Metta tools experiment (no code changes)

You can force multiprocessing in the recipe path via overrides:

```bash
./tools/run.py train arena run=mps_mp_debug \
  system.device=mps \
  training_env.vectorization=multiprocessing \
  training_env.auto_workers=false \
  training_env.num_workers=4 \
  training_env.zero_copy=false
```

Notes:

- `training_env.zero_copy=false` can help isolate shared-memory issues.
- If it deadlocks, try `training_env.async_factor=1` and smaller `training_env.num_workers`.

## What tends to break on macOS

- **Spawn vs fork**: macOS defaults to `spawn`. Ensure `multiprocessing.set_start_method("spawn", force=True)` runs
  before any worker processes are created.
- **Pickling**: spawned workers must pickle env factories. Look for non-picklable closures/classes.
- **Shared memory**: `pufferlib.vector.Multiprocessing` uses `multiprocessing.RawArray`; resource tracker warnings or
  hangs can indicate shared memory misuse.

## Useful instrumentation points

If you want more visibility, add temporary logging (and revert afterward):

1. `metta/rl/vecenv.py` — log vectorization, `num_workers`, `num_envs`, `batch_size`.
2. `packages/cogames/src/cogames/train.py` — log chosen backend + device + worker counts.
3. `packages/pufferlib-core/src/pufferlib/vector.py` — log worker start, `RESET/STEP` transitions, and exceptions.

## Reverting

If you edit code locally for debugging, revert with:

```bash
git checkout -- packages/cogames/src/cogames/train.py
```

Or discard local changes via your preferred method.
