# Observation Encoding Pipeline Profile

**Date:** 2026-02-10 **Branch:** polecat/scavenger/mt-umte@mlh6b128 **Hardware:** NVIDIA RTX 5080, Intel CPU

## Executive Summary

The observation encoding pipeline converts raw environment observations from MettagGrid (C++) into model input tensors
for the neural network policy. This profile identifies the key bottlenecks and provides optimization recommendations.

**Key Finding:** The Python observation encoding pipeline is **35-50x slower** than the C++ observation generation, with
latent attention being the dominant cost.

## Baseline SPS Measurements

### C++ Environment Step Timing (via profile_multi_config.py)

| Config                | Agents | Agent SPS | Observations % of C++ | Observations us/step |
| --------------------- | ------ | --------- | --------------------- | -------------------- |
| Toy                   | 20     | 653,850   | 89.1%                 | 17.74                |
| Arena (combat)        | 24     | 585,998   | 89.8%                 | 23.19                |
| CogsGuard (machina_1) | 8      | 193,899   | 56.2%                 | 19.42                |

### Python Observation Encoding Timing (via profile_observation_encoding.py)

| Device | Agent SPS | C++ Obs (us) | Python Pipeline (us) | Ratio |
| ------ | --------- | ------------ | -------------------- | ----- |
| CUDA   | 4,690     | 22.20        | 1,108.65             | 49.9x |
| CPU    | 5,266     | 21.00        | 746.59               | 35.6x |

## Pipeline Component Breakdown

### GPU (CUDA) Timing

| Component          | Mean (us)    | % of Pipeline | Description                            |
| ------------------ | ------------ | ------------- | -------------------------------------- |
| obs_shim           | 322.23       | 29.1%         | Padding strip + feature normalization  |
| tokenizer          | 311.18       | 28.1%         | ObsAttrEmbedFourier (Fourier features) |
| latent_attn        | 475.24       | 42.9%         | ObsLatentAttn (cross-attention)        |
| **Pipeline total** | **1,108.65** | 100%          |                                        |

### CPU Timing

| Component          | Mean (us)  | % of Pipeline | Description                            |
| ------------------ | ---------- | ------------- | -------------------------------------- |
| obs_shim           | 122.25     | 16.4%         | Padding strip + feature normalization  |
| tokenizer          | 197.66     | 26.5%         | ObsAttrEmbedFourier (Fourier features) |
| latent_attn        | 426.69     | 57.2%         | ObsLatentAttn (cross-attention)        |
| **Pipeline total** | **746.59** | 100%          |                                        |

### Full Step Breakdown (GPU)

| Component       | Mean (us) | Notes                         |
| --------------- | --------- | ----------------------------- |
| env_step        | 97.23     | Full env.step() including C++ |
| cpp_obs         | 22.20     | C++ observation encoding only |
| numpy_to_tensor | 51.21     | numpy → torch transfer        |
| obs_shim        | 322.23    | Padding + normalization       |
| tokenizer       | 311.18    | Fourier tokenization          |
| latent_attn     | 475.24    | Cross-attention encoding      |
| perceiver       | 410.95    | Alternative to latent_attn    |

## Torch Profiler Analysis (GPU)

Top CUDA operations by time:

| Operation                   | Self CUDA | % of Total | Notes                        |
| --------------------------- | --------- | ---------- | ---------------------------- |
| aten::addmm (linear)        | 27.5ms    | 22.0%      | Linear layers                |
| cutlass SGEMM kernel        | 26.6ms    | 21.3%      | Matrix multiply              |
| efficient_attention_forward | 20.6ms    | 16.5%      | Scaled dot-product attention |
| native_layer_norm           | 18.9ms    | 15.1%      | LayerNorm operations         |
| aten::copy\_                | 13.7ms    | 11.0%      | Memory copies                |
| aten::mm (matmul)           | 13.3ms    | 10.6%      | Matrix multiply              |

## Architecture Details

### Observation Flow

```
MettagGrid (C++) → NumPy array → PyTorch tensor → Model input
       │                │              │               │
       │ 22 us          │  51 us       │  1109 us      │
       └────────────────┴──────────────┴───────────────┘
```

### Pipeline Components

1. **Raw Observation (C++)**: `ObservationEncoder` generates token observations
   - Token format: `[location, feature_id, value]` (3 bytes each)
   - Location: packed (row, col) in nibbles
   - Typically 200 tokens per agent

2. **ObsTokenPadStrip**: Strips padding, remaps features
   - Finds max non-padding length in batch
   - Applies feature ID remapping for portability
   - O(B × M) where B=batch, M=max_tokens

3. **ObsAttrValNorm**: Normalizes attribute values
   - Divides by per-feature normalization factors
   - Simple lookup + division

4. **ObsAttrEmbedFourier**: Tokenization with Fourier features
   - Attribute embeddings: 12-dim learned embeddings
   - Coordinate representation: 24-dim Fourier features (6 frequencies × 4)
   - Output: 37-dim feature vectors per token

5. **ObsLatentAttn**: Cross-attention encoding
   - Learnable query tokens attend to input features
   - Multi-head cross-attention (4 heads, 2 layers)
   - Output: 128-dim encoded representation

## Identified Bottlenecks

### 1. Latent Attention (42.9% of pipeline on GPU)

- Cross-attention scales as O(Q × K) where Q=query tokens, K=input tokens
- Each layer has: Q projection, K projection, V projection, attention, output projection, MLP
- 2 layers × 4 heads × multiple projections = many small kernel launches

### 2. Tokenization (28.1% on GPU)

- Fourier features computed per token: sin/cos for 6 frequencies × 2 coordinates
- Requires multiple tensor operations per token
- Could be fused into a single kernel

### 3. Padding Strip (29.1% on GPU)

- Feature remapping involves indexing operations
- Clone operation for in-place modification
- Argmax for finding flip points

### 4. Memory Copies (numpy→torch 51us)

- Observation data copied from C++ to Python via numpy
- Then copied to GPU (if using CUDA)
- Could potentially be avoided with direct CUDA memory mapping

## Optimization Recommendations

### High Impact

1. **Fused CUDA Kernel for Tokenization**
   - Combine Fourier feature computation + embedding lookup
   - Eliminate intermediate tensor allocations
   - Expected: 50%+ reduction in tokenizer time

2. **Flash Attention for Latent Attention**
   - Currently uses scaled_dot_product_attention with efficient backend
   - Consider xformers memory_efficient_attention for better fusing
   - Expected: 20-30% reduction in attention time

3. **Reduce Attention Layers/Heads**
   - Current: 2 layers, 4 heads, 10 query tokens
   - Experiment with: 1 layer, 2 heads, 8 query tokens
   - Trade accuracy for speed

### Medium Impact

4. **Lazy Feature Remapping**
   - Only remap when features actually differ from training
   - Skip clone() when no remapping needed

5. **Pre-allocated Tensor Buffers**
   - Pool tensors for obs_shim intermediate results
   - Reduce allocation overhead

6. **Direct CUDA Memory Mapping**
   - Map C++ observation buffer directly to CUDA
   - Avoid numpy intermediate copy

### Low Impact / Research

7. **Perceiver Alternative**
   - ObsPerceiverLatent slightly faster than ObsLatentAttn
   - Different architectural tradeoffs (pooled latents vs query tokens)

8. **Quantization**
   - INT8 quantization for inference
   - May require architecture changes

## Profiling Scripts

### Run Environment Profile

```bash
cd packages/mettagrid/benchmarks/perf_optimization
METTAGRID_PROFILING=1 uv run python scripts/profile_multi_config.py
```

### Run Observation Encoding Profile

```bash
uv run python tests/perf/profile_observation_encoding.py --device cuda
uv run python tests/perf/profile_observation_encoding.py --device cpu
uv run python tests/perf/profile_observation_encoding.py --torch-profile
```

### Training SPS Baseline

```bash
uv run ./tools/run.py cogsguard.train trainer.total_timesteps=500000 run=sps_baseline
# Check logs for SPS: train_dir/<run_name>/logs/script.log
```

**Training Configuration Reference:**

- Environment: 1008 parallel envs × 8 agents = 8,064 agents per batch
- Batch size: 504 (target 512)
- Expected training SPS: 50,000-100,000 agent steps/second (GPU)

## Success Criteria

- [x] Baseline SPS recorded (cogsguard, GPU): ~4,700 agent SPS for isolated pipeline
- [x] End-to-end observation pipeline timing documented
- [x] Identified which stage takes most time: latent_attn (42.9%)
- [x] Quantified memory copy overhead: numpy→torch 51 us/step
- [x] 3 optimization recommendations provided

## Next Steps

1. Implement fused CUDA kernel for tokenization
2. Benchmark with reduced attention configuration
3. Profile full training loop to measure end-to-end impact
4. Compare SPS before/after optimizations
