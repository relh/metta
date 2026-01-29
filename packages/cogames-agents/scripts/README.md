# Benchmark Scripts

Harness for evaluating scripted agents on CogsGuard missions via `cogames scrimmage`.

## Scripts

### `benchmark_agents.sh`

Runs every registered scripted agent through `cogames scrimmage` and saves per-agent JSON results.

```bash
# Run all agents (defaults: 10 episodes, 1000 steps, cogsguard_arena.basic)
./scripts/benchmark_agents.sh

# Custom run
./scripts/benchmark_agents.sh -e 20 -s 2000 -m cogsguard_arena.basic -o ./my_results

# Subset of agents
./scripts/benchmark_agents.sh -a role,pinky,baseline,wombo -e 50
```

**Options:**

| Flag     | Default                 | Description                |
| -------- | ----------------------- | -------------------------- |
| `-e`     | 10                      | Episodes per agent         |
| `-s`     | 1000                    | Max steps per episode      |
| `-m`     | `cogsguard_arena.basic` | Mission                    |
| `-o`     | `./benchmark_results`   | Output directory           |
| `-a`     | all agents              | Comma-separated agent list |
| `--seed` | 42                      | RNG seed                   |

Results are written to `<outdir>/<timestamp>/<agent>.json`.

### `compare_agents.py`

Parses benchmark JSON results and prints a ranked comparison table.

```bash
# Table output (default)
python scripts/compare_agents.py ./benchmark_results/20260128_143000

# CSV for spreadsheets
python scripts/compare_agents.py ./benchmark_results/20260128_143000 --format csv

# JSON for programmatic use
python scripts/compare_agents.py ./benchmark_results/20260128_143000 --format json
```

**Metrics captured:**

| Metric                    | Source                                        | Description                |
| ------------------------- | --------------------------------------------- | -------------------------- |
| `reward`                  | per-episode avg                               | Average agent reward       |
| `heart.gained`            | `env_agent/heart.gained`                      | Hearts collected           |
| `heart.lost`              | `env_agent/heart.lost`                        | Hearts consumed            |
| `aligned.junction.held`   | `env_collective/cogs/aligned.junction.held`   | Junctions held             |
| `aligned.junction.gained` | `env_collective/cogs/aligned.junction.gained` | Junctions aligned          |
| `action_timeouts`         | policy summary                                | Action generation timeouts |

### `quick_eval.sh`

Fast single-agent eval for development iteration (3 episodes, 500 steps by default).

```bash
# Quick table output
./scripts/quick_eval.sh role

# JSON output
./scripts/quick_eval.sh pinky --json

# Open in MettaScope GUI
./scripts/quick_eval.sh baseline --gui

# Custom parameters
./scripts/quick_eval.sh wombo -e 5 -s 1000 --seed 99
```

## Available Agents

Registered scripted agents (from `cogames-agents` package):

| Agent                | Description                     |
| -------------------- | ------------------------------- |
| `role`               | Multi-role Nim CogsGuard policy |
| `role_py`            | Python multi-role CogsGuard     |
| `pinky`              | Alternative role ordering       |
| `planky`             | Plank-focused strategy          |
| `wombo`              | Alternative multi-role          |
| `baseline`           | Standard baseline               |
| `tiny_baseline`      | Minimal baseline                |
| `cogsguard_v2`       | CogsGuard v2                    |
| `cogsguard_control`  | Control-focused variant         |
| `cogsguard_targeted` | Targeted behavior               |
| `miner`              | Single-role: miner              |
| `scout`              | Single-role: scout              |
| `aligner`            | Single-role: aligner            |
| `scrambler`          | Single-role: scrambler          |
| `teacher`            | Teacher wrapper                 |
| `ladybug_py`         | Ladybug Python                  |
| `thinky`             | High-cognition Nim              |
| `nim_random`         | Nim random                      |
| `race_car`           | Race car Nim                    |
| `ladybug`            | Ladybug Nim                     |
| `alignall`           | All-aligner Nim                 |
