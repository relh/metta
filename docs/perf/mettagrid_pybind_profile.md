# MettagGrid/Pybind Performance Profile

Performance investigation of MettagGrid simulation and pybind11 Python bindings.

**Date:** 2026-02-10 **Hardware:** NVIDIA GeForce RTX 5080 Laptop GPU (16GB), Linux 6.17.0 **Profiling Environment:**
`METTAGRID_PROFILING=1`

## Executive Summary

The primary bottleneck in MettagGrid is the **observation computation phase**, consuming 84-89% of C++ step time across
all agent counts. Pybind11 boundary overhead is significant (25-53%) but becomes proportionally smaller as step
complexity increases with more agents.

## Baseline SPS Measurements (Cogsguard-equivalent config)

| Agents | Map Size | Env SPS | Agent SPS | C++ Step Time |
| ------ | -------- | ------- | --------- | ------------- |
| 8      | 40x40    | 41,128  | 329,028   | 11.47 µs      |
| 16     | 60x60    | 41,915  | 670,637   | 14.50 µs      |
| 32     | 80x80    | 24,147  | 772,719   | 31.18 µs      |

## Key Findings

### 1. Pybind Boundary Overhead

| Agents | Python Step | C++ Step | Pybind Overhead  |
| ------ | ----------- | -------- | ---------------- |
| 8      | 24.31 µs    | 11.47 µs | 12.84 µs (52.8%) |
| 16     | 23.86 µs    | 14.50 µs | 9.36 µs (39.2%)  |
| 32     | 41.41 µs    | 31.18 µs | 10.23 µs (24.7%) |

**Analysis:** Pybind overhead is relatively fixed at ~10-13 µs regardless of step complexity. This includes:

- Python function call overhead
- NumPy array buffer access setup
- GIL management (GIL does NOT appear to be released during step)

### 2. MettagGrid.step() Phase Breakdown

**32 Agents (representative production config):**

| Phase        | Time (µs) | % of Step |
| ------------ | --------- | --------- |
| observations | 27.71     | 88.9%     |
| actions      | 2.45      | 7.9%      |
| reset        | 0.33      | 1.0%      |
| aoe          | 0.32      | 1.0%      |
| on_tick      | 0.07      | 0.2%      |
| rewards      | 0.05      | 0.2%      |
| events       | 0.02      | 0.1%      |
| truncation   | 0.02      | 0.1%      |
| collectives  | 0.02      | 0.1%      |
| **total**    | **31.18** | **100%**  |

**Observations scale linearly:** ~0.87 µs per agent

### 3. GIL Contention Analysis

- **GIL Release:** The step() function does NOT release the GIL during execution
- **Impact:** Multi-environment parallelism in Python is limited by GIL contention
- **Vectorized Environments:** Each env.step() call holds the GIL for the entire duration

### 4. Batch Efficiency

Current architecture uses single-step execution. Each step() call:

1. Enters Python from C++
2. Acquires numpy buffer pointers
3. Executes C++ step logic
4. Returns to Python

No true batching exists - N single steps have similar overhead to N sequential calls.

### 5. Top Time Consumers (C++ Internal)

1. **observations (84-89%)**: Token-based observation computation for each agent
   - Iterates over observable grid cells
   - Encodes objects, inventory, positions into tokens
   - Scales linearly with num_agents × observation_window_size

2. **actions (7-8%)**: Action execution with priority ordering
   - Shuffles agent order
   - Executes handlers by priority level
   - Scales with num_agents × num_priority_levels

3. **reset/aoe (~1% each)**: Buffer clearing and area-of-effect processing

## Optimization Recommendations

### Rank 1: Optimize Observation Computation (High Impact)

**Impact:** Could reduce step time by 50-80%

The observation phase dominates at 84-89%. Potential optimizations:

- **Incremental observations**: Only recompute changed cells instead of full window
- **Spatial indexing**: Use grid-based spatial hash for faster object lookups
- **SIMD vectorization**: Token encoding could benefit from AVX2/AVX-512
- **Observation caching**: Cache static parts of observations between steps

### Rank 2: Release GIL During C++ Step (Medium Impact)

**Impact:** Could improve multi-env throughput by 2-4x

Current implementation holds GIL throughout step(). Adding:

```cpp
py::gil_scoped_release release;
```

in the step() binding would allow Python threads to run concurrently.

**Caveat:** Requires careful verification that no Python objects are accessed during step.

### Rank 3: Reduce Pybind Boundary Overhead (Medium Impact)

**Impact:** Could save ~10 µs per step (25-50% of small-agent configs)

Options:

- **Buffer pooling**: Pre-allocate and reuse numpy arrays
- **Batched step API**: Add `step_n(actions, n)` to amortize call overhead
- **Direct memory views**: Expose C++ arrays directly without numpy intermediary

## Profiling Script Location

A reusable profiling script is available at:

```
tests/perf/profile_mettagrid_pybind.py
```

Usage:

```bash
METTAGRID_PROFILING=1 uv run python tests/perf/profile_mettagrid_pybind.py \
    --agents 8 --map-size 40 --steps 10000 --output results.json
```

## Technical Notes

### Architecture Overview

```
Python (MettaGridPufferEnv.step)
    └─> Pybind11 boundary (~10-13 µs fixed overhead)
        └─> MettaGrid::_step() (C++)
            ├── reset phase (3%)
            ├── events phase (<1%)
            ├── actions phase (8%)
            ├── on_tick phase (<1%)
            ├── aoe phase (1%)
            ├── collectives phase (<1%)
            ├── observations phase (84-89%) ◄── BOTTLENECK
            ├── rewards phase (<1%)
            └── truncation phase (<1%)
```

### Key Files

- **C++ Step Implementation**: `packages/mettagrid/cpp/bindings/mettagrid_c.cpp:777-935`
- **Observation Computation**: `packages/mettagrid/cpp/bindings/mettagrid_c.cpp:354-383`
- **Profiling Stats**: `packages/mettagrid/cpp/include/mettagrid/profiling.hpp`
- **Python Wrapper**: `packages/mettagrid/python/src/mettagrid/simulator/simulator.py`

### Cython Clarification

**Note:** The bead description mentioned "Cython hot spots in mettagrid.pyx" but there is no Cython in MettagGrid. The
implementation is pure C++ with pybind11 bindings. All performance analysis focuses on the actual pybind11-based
architecture.
