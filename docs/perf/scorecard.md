# Perf Scorecard

Unified benchmark results across all workload phases. See [0027-perf-benchmarking](../specs/0027-perf-benchmarking.md)
for methodology and statistical context (run-to-run sigma ~3.5-5%, N>=3 recommended for perf claims).

Update via `/tr.perf-scorecard`.

## Env-Only

| PR    | Config                       | Baseline       | Runs              | N   | Delta %        | Status              | Notes                                                       |
| ----- | ---------------------------- | -------------- | ----------------- | --- | -------------- | ------------------- | ----------------------------------------------------------- |
| #6895 | env-only (20a, 40x40)        | main           | 5x5K steps        | 1   | +68% agent SPS | significant (large) | 3.4x obs speedup. 600K validation comparisons, 0 mismatches |
| #7332 | env-only (8-100a, 40x40, 4t) | optimized (1t) | 5-20K x 10 rounds | 10  | +32% to +162%  | significant         | M2 Pro. Opt-in via METTAGRID_OBS_THREADS=auto               |

## Training

| PR    | Config         | Baseline | Epochs | N         | Delta %    | Status             | Notes                                                              |
| ----- | -------------- | -------- | ------ | --------- | ---------- | ------------------ | ------------------------------------------------------------------ |
| #6946 | 1x4090, uv-run | 4eae1ab0 | e2-10  | 1         | +0.75%     | noise              | wave2                                                              |
| #6946 | 4xL4, torchrun | -        | e2+3   | 1         | +0.57%     | noise              | Only wave2 PR with DDP data                                        |
| #6899 | 1x4090, uv-run | -        | e1-3   | 1         | +0.76%     | noise              |                                                                    |
| #6899 | 4xL4, torchrun | -        | -      | 0         | -          | not run            |                                                                    |
| #6892 | 1x4090, uv-run | 4eae1ab0 | e2-10  | 1         | +3.97%     | noise (high var)   | Per-epoch range: -6.3% to +13.5%                                   |
| #6892 | 1x4090, uv-run | 0a5ef36c | e2+3   | 1         | +1.24%     | noise              | 3-epoch rerun                                                      |
| #6892 | 4xL4, torchrun | -        | -      | 0         | -          | not run            |                                                                    |
| #6895 | 1x4090, uv-run | 4eae1ab0 | e2-10  | 1         | +3.82%     | noise (high var)   | Per-epoch range: -5% to +14%. C++ env change                       |
| #6895 | 1x4090, uv-run | 91e783f7 | e1     | 1         | +0.1%      | noise              | 1-epoch, cleaner measurement                                       |
| #6890 | 1x4090, uv-run | 90c3a1fa | e1-3   | 1         | +2.25%     | noise              | Pinned CPU staging for GPU->CPU action send                        |
| #6890 | 4xL4, torchrun | -        | -      | 0         | -          | not run            |                                                                    |
| #6896 | 1x4090, uv-run | 0a5ef36c | e1-3   | 1         | +9.5%      | likely significant | Reduce obs encoder attn depth 2->1. Needs convergence verification |
| #6896 | 4xL4, torchrun | -        | -      | 0         | -          | not run            |                                                                    |
| #7226 | 1x4090, uv-run | -        | e2-10  | 1         | +1.35%     | noise              |                                                                    |
| #7226 | 4xL4, torchrun | effd2337 | e2-10  | 1/machine | -6.11% avg | regression         | Post-merge. -4.85% and -7.34% on two machines                      |

## Tournament

| PR    | Config                        | Baseline   | N   | Delta %                     | Status      | Notes                                                            |
| ----- | ----------------------------- | ---------- | --- | --------------------------- | ----------- | ---------------------------------------------------------------- |
| #7477 | beta-cvc (8a, 10K steps, WS)  | batch=1 WS | 1   | 8->2 round-trips/step       | significant | Transport batching. Comm overhead ~75% cut. Prerequisite for GPU |
| #7388 | beta-cvc (8a, 10K steps, GPU) | CPU (r6a)  | -   | TBD (estimated 5-20x infer) | not run     | GPU inference benchmark. 186s->13-60s projected per episode      |

## Wave2 PRs (closed without merge)

| PR    | Title                                        | Single-GPU | Multi-GPU DDP | Reason closed      |
| ----- | -------------------------------------------- | ---------- | ------------- | ------------------ |
| #6850 | Speed up CogsGuard training                  | +1.69%     | -4.20%        | divergence         |
| #6893 | Release GIL during mettagrid step            | +4.05%     | -2.70%        | divergence         |
| #6937 | Vecenv blocking worker notification          | +5.25%     | -2.58%        | divergence         |
| #6940 | End-to-end torch.compile                     | +2.20%     | -0.56%        | divergence         |
| #6900 | PPO mixed precision + gradient checkpointing | +1.96%     | -7.99%        | divergence         |
| #6936 | Vecenv async ready-worker scheduling         | -0.90%     | +9.47%        | reverse divergence |
| #6938 | Vecenv double-buffered shared memory         | -3.08%     | +3.49%        | reverse divergence |
| #6941 | Policy token budget pruning                  | +2.79%     | +0.56%        | multi within noise |
| #6889 | Pinned memory for CPU->GPU rollout staging   | -0.30%     | +1.76%        | both within noise  |
| #6945 | Gumbel-max action sampling                   | -1.62%     | -0.59%        | regression on both |
| #6947 | Pinned CPU action staging                    | -0.08%     | -0.33%        | both within noise  |
