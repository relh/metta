# DDP `run.sh` SPS + Correctness Notes (2026-02-17)

This note captures the outcome of re-running the SPS audit using the **canonical multi-GPU launcher** `devops/run.sh`
(which uses `torchrun`) on the 4xL4 SkyPilot sandboxes.

## Why We Had To Re-Run With `run.sh`

Some earlier SPS comparisons on the sandboxes were single-process runs (world_size=1). For publishable multi-GPU
throughput claims, we need to launch via `torchrun` so that:

- `DistributedHelper` logs `world_size: 4 rank: ...`
- all 4 GPUs are actually used

## Main Breakage Under `run.sh` (Torchrun + uv Python 3.12)

On `origin/main` @ `8f82d02ec9`, multi-GPU launch fails early with:

`RuntimeError: unsupported operation: some elements of the input tensor and the written-to tensor refer to a single memory location`

Traceback root:

- `metta/rl/training/trajectory_isolation.py:717` inside `TrajectoryIsolator.writeback_rollout_tds`
- triggered by `rollout_td[mask] = _pad_slice_td_like(slice_td, rollout_slice_td)`

Cause:

- `_split_rollout_td_per_slice()` uses `base_td.clone(recurse=False)` so slice policy TensorDicts share rollout input
  tensor storage (intentionally, to avoid per-step cloning churn).
- Under the uv-managed environment (Python 3.12 + newer tensordict), masked assignment rejects RHS that aliases LHS
  storage.

## Fix Implemented

Instead of assigning the entire slice TensorDict back into `rollout_td[mask]`, writeback now:

- iterates keys and only writes back values that **do not** alias the rollout buffer (typically policy outputs)
- skips keys whose tensors share storage with the rollout buffer (inputs are already present)
- falls back to a safe padded+cloned TensorDict writeback only for unexpected nested TensorDict values

Files:

- `metta/rl/training/trajectory_isolation.py`
- tests: `tests/rl/test_trajectory_isolation_rollout_writeback.py`
- follow-up infra fix: `devops/run.sh` prepends `${HOME}/.local/bin` to `PATH` so `uv` is found on fresh sandboxes

## Benchmark Protocol (Strict Parity)

Topology:

- `relh-sandbox-1` (4x L4)
- `relh-sandbox-3` (4x L4)

Launcher:

- `NUM_GPUS=4 ./devops/run.sh ...` (torchrun)

Recipe:

- `recipes.experiment.cogsguard.train`

Important: for this config the epoch step size is `8,388,608` agent steps, so 10 epochs requires:

- `trainer.total_timesteps=83,886,080` (10 \* 8,388,608)

Runs:

- `relh-sandbox-1`: `perf_ddp_writebackfix_rs1_10epB_20260217_b`
- `relh-sandbox-3`: `perf_ddp_writebackfix_rs3_10epB_20260217_b`

Results (mean e2-10 ksps from `logs/script.log`):

- `relh-sandbox-1`: `204.60 ksps`
- `relh-sandbox-3`: `207.41 ksps`
- average across hosts: `206.00 ksps`
