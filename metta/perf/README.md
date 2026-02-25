# Training Performance Benchmark Harness

Measures training SPS and per-phase timing breakdowns using MicrobenchReporter. Configures a TrainTool, strips external
services (wandb, eval, checkpoint), injects MicrobenchReporter, runs training via the normal recipe path, then
post-processes the resulting JSON artifact.

For methodology and statistical context, see the [perf benchmarking spec](../../docs/specs/0027-perf-benchmarking.md).
For the env-only (C++ simulation) harness, see
[`packages/mettagrid/benchmarks/perf/README.md`](../../packages/mettagrid/benchmarks/perf/README.md).

## Quick Start

```bash
# Smoke test (CPU-only, verifies harness wiring)
uv run python scripts/training_perf_benchmark.py --preset smoke

# Quick local benchmark (requires GPU, ~5-10 min)
uv run python scripts/training_perf_benchmark.py --preset quick

# Stable measurement with baseline comparison
uv run python scripts/training_perf_benchmark.py --preset standard \
    --phase baseline --output results/baseline.json
uv run python scripts/training_perf_benchmark.py --preset standard \
    --phase opt1 --output results/opt1.json --baseline results/baseline.json

# Generate phase summary from results directory
uv run python scripts/training_perf_benchmark.py --report results/
```

## Presets

| Preset        | Recipe                               | Timesteps | Warmup | Description                        |
| ------------- | ------------------------------------ | --------- | ------ | ---------------------------------- |
| `smoke`       | `recipes.experiment.ci:train`        | 16        | 0      | Serial, CPU-only. Verifies wiring. |
| `quick`       | `arena_basic_easy_shaped:train`      | 2M        | 2      | Single GPU, ~5-10 min.             |
| `standard`    | `arena_basic_easy_shaped:train`      | 10M       | 2      | Single GPU, ~30-60 min.            |
| `prod_single` | `arena_basic_easy_shaped:train_100m` | 100M      | 2      | Full production single-GPU config. |

`smoke` is the only CPU-safe preset. Others use multiprocessing vectorization and require a GPU.

## Custom Recipes

```bash
uv run python scripts/training_perf_benchmark.py \
    --recipe recipes.experiment.cogsguard --recipe-fn train \
    --total-timesteps 2000000
```

## CLI Flags

| Flag                | Default | Description                               |
| ------------------- | ------- | ----------------------------------------- |
| `--preset`          | -       | Use a preset config (see table above)     |
| `--recipe`          | -       | Recipe module path (mutually exclusive)   |
| `--recipe-fn`       | `train` | Recipe function name                      |
| `--run`             | auto    | Run name (default: `training-bench-<ts>`) |
| `--total-timesteps` | preset  | Override total timesteps                  |
| `--warmup-epochs`   | preset  | Warmup epochs excluded from summary       |
| `--vectorization`   | preset  | `serial` or `multiprocessing`             |
| `--num-workers`     | preset  | Number of env workers                     |
| `--print-per-epoch` | off     | Log per-epoch microbench metrics          |
| `--output`          | -       | Save results to JSON                      |
| `--baseline`        | -       | Compare against baseline JSON file(s)     |
| `--phase`           | -       | Label for this optimization phase         |
| `--report`          | -       | Generate summary from results directory   |

**Exit codes:** 0 = success, 1 = unstable measurements (CV > 20%).

## Output

The harness reports:

- **SPS** (mean, median, std, P10-P90) from effective records (post-warmup)
- **CV** (coefficient of variation) with stability assessment (Excellent <5%, Good <10%, Fair <20%, Poor >=20%)
- **Phase timing breakdown** as percentage of epoch wall time:
  - `rollout_inference_time` (typically 44-53%)
  - `train_time` (typically 38-42%)
  - `rollout_env_wait_time` (typically 6-13%)
  - `rollout_td_prep_time` (typically 1-2%)
  - `rollout_send_time` (typically <1%)
  - `stats_time`
- **Scorecard row** ready to paste into `docs/perf/scorecard.md`

## Library API

`metta.perf.training_harness` exposes:

- `configure_for_benchmark(tool, *, run_name, output_path, ...)` — prepare a TrainTool for benchmarking
- `load_preset(name)` — lazy-import a recipe and return a configured TrainTool
- `load_artifact(path)` — load MicrobenchReporter JSON artifact
- `compute_training_statistics(artifact)` — CV, phase breakdown, stability assessment
- `save_results(stats, config, phase, output_path)` — save results as JSON
- `compare_results(baseline_path, current_stats, phase)` — compare against a baseline
- `compare_multiple(baseline_paths, current_stats, phase)` — compare against multiple baselines
