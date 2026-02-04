# <!--

# HOW TO UPDATE THIS DOCUMENT

This overview should be updated periodically (roughly monthly, or after major refactors) so it stays accurate for new
engineers joining the project.

To update, ask an AI assistant (Claude Code, Codex, etc.) to:

1. Read this file in full.
2. Run the following exploration commands to gather current state:
   - `git log --oneline -50` (recent commits)
   - `git log --diff-filter=A --name-only --since="<last-update-date>" --format="" | head -50` (newly added files since
     last update)
   - `git log --diff-filter=D --name-only --since="<last-update-date>" --format="" | head -50` (deleted files since last
     update)
   - Glob for new top-level directories or packages
   - Read pyproject.toml for new workspace members or dependency changes
   - Read .importlinter for new layer rules
   - Check recipes/prod/ and recipes/experiment/ for new recipes
   - Check packages/ for new or removed packages
   - Check .github/workflows/ for CI changes
   - Check devops/ for infrastructure changes
3. Update each section with accurate information. Pay attention to:
   - New packages, directories, or modules added
   - Packages or systems that were removed or deprecated
   - Changes to dependency graph or import rules
   - New CLI entry points or tools
   - New game mechanics or agent types
   - Infrastructure changes (new Helm charts, Terraform stacks, etc.)
   - Version bumps (Python, Bazel, Nim, etc.)
4. Move the "Active Development Areas" and "Deprecated" sections to reflect current git activity.
5. Append a new entry to the "Update History" section at the bottom with:
   - Date
   - Commit hash at time of update
   - Brief summary of what changed in the codebase since last update
6. Do NOT delete previous update history entries — they form a useful changelog for understanding project evolution.

Suggested prompt for the update:

"Read docs/overview.md and update it to reflect the current state of the codebase. Explore the repo for changes since
the last update date shown in the Update History section. Update all sections, add new ones if needed, and append a new
Update History entry."

============================================================================= -->

# Metta Codebase Overview

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Repository Overview and Structure](#2-repository-overview-and-structure)
3. [Dependency Graph and Import Rules](#3-dependency-graph-and-import-rules)
4. [MettagGrid: The Game Environment (C++/Python/Nim)](#4-mettagrid-the-game-environment-cpythonnim)
5. [CoGames: Game Configurations and Missions](#5-cogames-game-configurations-and-missions)
6. [CoGames-Agents: Scripted and Evolved Policies](#6-cogames-agents-scripted-and-evolved-policies)
7. [Agent Package: Policy Architecture System](#7-agent-package-policy-architecture-system)
8. [Cortex: Neural Memory and Recurrent Backbones](#8-cortex-neural-memory-and-recurrent-backbones)
9. [Metta Core: RL Training Framework](#9-metta-core-rl-training-framework)
10. [The Recipe and Tool System](#10-the-recipe-and-tool-system)
11. [Common Package: Shared Utilities](#11-common-package-shared-utilities)
12. [App Backend: Observatory API Server](#12-app-backend-observatory-api-server)
13. [Tournament System](#13-tournament-system)
14. [Web Frontends](#14-web-frontends)
15. [DevOps and Infrastructure](#15-devops-and-infrastructure)
16. [Skills System: AI Assistant Automation](#16-skills-system-ai-assistant-automation)
17. [Build Systems and Tooling](#17-build-systems-and-tooling)
18. [CI/CD Pipeline](#18-cicd-pipeline)
19. [Active Development Areas](#19-active-development-areas)
20. [Deprecated and Legacy Code](#20-deprecated-and-legacy-code)
21. [Appendix: Entry Points and CLI Commands](#21-appendix-entry-points-and-cli-commands)
22. [Update History](#22-update-history)

---

## 1. Executive Summary

Metta is a **polyglot monorepo** for multi-agent reinforcement learning research, focused on cooperation and alignment
in grid-based game environments. The project is developed by **Softmax** (MIT License) and centers around training AI
agents to cooperate in the "Cogs vs Clips" game within the **Alignment League Benchmark**.

**Scale:** ~174 Python files in core `metta/`, 50+ C++ headers in mettagrid, 108 Nim files for visualization, 36 GitHub
Actions workflows, 46 AI assistant skills, 11 Python workspace members, and 266 test files.

**Languages:** Python (primary), C++ (game engine), Nim (visualization + fast agents), TypeScript (web frontends), Go,
Rust (build tooling).

**Core Loop:** Agents observe a grid environment, process observations through neural networks (with memory via
Cortex/LSTM/Mamba), select actions, receive rewards based on cooperation, resource gathering, and alignment behaviors,
and train via PPO with curriculum learning.

---

## 2. Repository Overview and Structure

```
metta/                          # Root monorepo
├── agent/                      # Policy architecture & neural network components
├── app_backend/                # Observatory REST API (FastAPI + PostgreSQL)
├── cogweb/                     # Backend client library
├── common/                     # Shared utilities (logging, auth, tools framework)
├── devops/                     # Infrastructure: SkyPilot, Terraform, Helm, Docker, Datadog
├── docs/                       # Documentation (specs, AI docs, workflows)
├── gastown/                    # (Minimal/placeholder directory)
├── mcp_servers/                # Model Context Protocol servers (PR similarity)
├── metta/                      # Core RL training framework (private, not published)
├── notebooks/                  # Jupyter notebooks for analysis
├── packages/
│   ├── mettagrid/              # C++/Python grid environment (public package)
│   ├── cogames/                # Game configs, missions, CLI (public package)
│   ├── cogames-agents/         # Scripted/evolved agent policies (public package)
│   ├── cortex/                 # Neural memory cells and stacks (public package)
│   ├── gitta/                  # Git utilities library
│   └── pufferlib-core/         # RL framework core (vectorized envs)
├── proto/                      # Protobuf schemas (policy wire protocol)
├── recipes/
│   ├── prod/                   # Production recipes (CI-validated)
│   └── experiment/             # Work-in-progress experiments
├── scripts/                    # Utility scripts
├── skills/                     # 46 AI assistant skills (Claude/Codex)
├── softmax/                    # Dashboard metrics and AWS secrets
├── tests/                      # Root test directory (59 test files)
├── tools/                      # Training/evaluation CLI (run.py)
├── typings/                    # Type stubs
└── web/
    ├── observatory/            # Next.js dashboard (observatory.softmax-research.net)
    ├── home/                   # Vite + React landing page
    ├── gridworks/              # Grid visualization frontend
    └── softmax.com/            # Next.js company website
```

**Key Configuration Files:**

| File              | Purpose                                                                    |
| ----------------- | -------------------------------------------------------------------------- |
| `pyproject.toml`  | Root Python project, uv workspace definition, 11 workspace members         |
| `.importlinter`   | Enforced dependency layers between packages                                |
| `.ruff.toml`      | Linting (line-length 120, Python 3.12, pycodestyle+pyflakes+bugbear+isort) |
| `flake.nix`       | Nix development environment (Python 3.12.11, Bazel, Nim, pnpm)             |
| `.python-version` | Python 3.12.11                                                             |
| `.bazelversion`   | Bazel 9.0.0                                                                |
| `package.json`    | Node.js: prettier 3.6.2, turbo 2.5.5                                       |

---

## 3. Dependency Graph and Import Rules

The codebase enforces strict layering via `import-linter`:

### Package Dependency Hierarchy

```
metta/ (top-level consumer, nothing depends on it)
  ├── depends on → cogames/
  ├── depends on → mettagrid/
  ├── depends on → cortex/
  ├── depends on → pufferlib-core/
  └── depends on → agent/

cogames/ → mettagrid/
cogames-agents/ → cogames/, mettagrid/
app_backend/ → common/ (ONLY, cannot import metta.*)

mettagrid has NO internal Python dependencies (C++/Python hybrid, standalone)
```

### Internal Layer Contract (within metta/)

```
metta.tools          ← top layer, can import from everything below
  ↓
metta.gridworks
  ↓
metta.setup
  ↓
metta.sim
  ↓
metta.rl
  ↓
metta.sweep
  ↓
metta.cogworks
  ↓
metta.adaptive
  ↓
metta.map
  ↓
metta.common         ← bottom layer, cannot import from anything above
```

**Independence Rules:**

- `cogames` cannot import from `metta`, `cortex`, `gitta`, or `tribal_village`
- `mettagrid` cannot import from any other internal package
- `app_backend` can only import `metta.common`, `metta_alo`, and `mettagrid`
- Enforced by running `uv run lint-imports`

---

## 4. MettagGrid: The Game Environment (C++/Python/Nim)

**Location:** `packages/mettagrid/` | **Build:** Bazel 9.0 + pybind11 | **Version:** Dynamic from git tags
(`mettagrid-v*`)

MettagGrid is the compiled grid-based multi-agent environment where all training happens. The C++ core handles game
logic and observation encoding, exposed to Python via pybind11.

### C++ Core (`cpp/include/mettagrid/`)

```
core/
  Grid.hpp              # 2D grid: vector<vector<GridObject*>>, O(1) spatial lookups
  GridObject.hpp        # Base object: id, location, type_id, tag_ids, handlers
  TagIndex.hpp          # O(1) tag-based object lookup
  AoETracker.hpp        # Area-of-effect radius queries

objects/
  Agent.hpp             # Player-controlled entity with rewards, stats, vibes
  Collective.hpp        # Shared inventory for agent teams (factions)
  Chest.hpp             # Stationary resource storage
  Wall.hpp              # Blocking obstacle
  Alignable.hpp         # Interface for collective membership
  HasInventory.hpp      # Inventory ownership mixin
  HasVibe.hpp           # Vibe state mixin

actions/
  action_handler.hpp    # Base: resource requirements, frozen checks
  move.hpp              # 8-directional movement, swap frozen agents, trigger on-use
  attack.hpp            # Vibe-gated combat: freeze + loot target
  transfer.hpp          # Vibe-gated resource sharing between adjacent agents
  change_vibe.hpp       # Instant vibe switching
  noop.hpp              # No-operation

handler/
  handler.hpp           # Filter → Mutation chains (on_use and per-tick AoE)
  event.hpp             # Timestep-triggered effects via EventScheduler
  filters/              # Conditions: game_value, resource, near, tag, alignment, vibe
  mutations/            # State changes: attack, freeze, align, tag, resource, stats

systems/
  observation_encoder.hpp  # Multi-token observation: {location, feature_id, value}
  reward.hpp               # GameValue-based reward: INVENTORY, STAT, TAG_COUNT scopes
  stats_tracker.hpp        # Dynamic stat tracking (up to 1024 stats per agent)

config/
  MettagridConfig.hpp      # C++ config structures
  observation_features.hpp # Runtime feature ID mapping
```

### Game Loop (Per Timestep)

1. Read actions from NumPy buffer
2. Execute all actions (priority: Attack=1 > Transfer=0 > Move)
3. Check/decrement frozen counters
4. Validate required resources, execute action, consume resources
5. Track success/failure statistics
6. Apply on-tick handlers to all agents
7. Execute scheduled events (timestep-triggered)
8. Update area-of-effect handlers
9. Compute observations for all agents (sparse token encoding)
10. Compute rewards via GameValue system
11. Check episode termination/truncation

### Key Game Mechanics

| Mechanic      | Description                                                                   |
| ------------- | ----------------------------------------------------------------------------- |
| **Vibes**     | Agents switch between behavioral modes (0-N) enabling different action combos |
| **Freezing**  | Attacked agents frozen for N turns; can be swapped but cannot act             |
| **Alignment** | Agents join collectives to share inventory and earn team rewards              |
| **Resources** | Agents carry items with capacity limits modifiable via gear                   |
| **Transfer**  | Resource sharing with adjacent agents (core cooperation mechanic)             |
| **Combat**    | Vibe-gated attack: damage, steal, freeze targets                              |
| **Events**    | Time-triggered mutations applied to tagged objects                            |

### Observation Format (TRIPLET_V1)

Each token is 3 bytes: `{location, feature_id, value}`. Location is row:col packed into nibbles. Features include: agent
group, frozen state, compass, inventory amounts (multi-token base-256), vibe, episode progress, last action/reward.

### Python Layer (`python/src/mettagrid/`)

- `simulator/` - Simulation and Simulator wrapper classes
- `envs/` - PufferMettaGridEnv (PufferLib integration for training)
- `config/` - MettaGridConfig, ObsConfig, ActionConfig, RewardConfig
- `map_builder/` - ASCII, maze, random, perimeter map generation
- `mapgen/` - Procedural map generation
- `renderer/` - Mettascope (Nim), VibeScope, LogRenderer
- `policy/` - Policy loading and registry

### Nim Layer (`nim/`)

- `mettascope/` - Interactive grid visualization (108 .nim files): simulation engine, replay playback, pathfinding,
  heatmap shaders, UI panels
- `vibescope/` - Vibe visualization tool

---

## 5. CoGames: Game Configurations and Missions

**Location:** `packages/cogames/` | **CLI:** `cogames` (typer) | **Primary Game:** Cogs vs Clips (CogsGuard)

CoGames defines game configurations, missions, and evaluation suites for the Alignment League Benchmark.

```
src/cogames/
├── cogs_vs_clips/
│   ├── missions.py      # Mission definitions (CogsGuardBasicMission, Machina1, etc.)
│   ├── sites.py         # Map/arena definitions (CogsGuard, Training Facility)
│   ├── mission.py       # Mission and Site base classes, MissionVariant system
│   ├── cog.py           # Agent (Cog) configuration
│   ├── stations.py      # Game objects: Gear, Junction, Hub, Chest, Extractors
│   ├── variants.py      # Mission variant system
│   ├── procedural.py    # Procedural arena generation (MachinaArena, RandomTransform)
│   └── evals/           # Evaluation missions (diagnostic, difficulty, spanning)
├── cli/                 # CLI: mission listing, policy parsing, submission, leaderboard
├── maps/                # ~40+ pre-built .map files
├── policy/              # Starter agent template, trainable policy template
├── evaluate.py          # Evaluation pipeline
├── train.py             # Training pipeline
├── play.py              # Interactive gameplay
├── game.py              # Mission config loading (YAML, JSON, Python)
└── curricula.py         # Training curriculum management
```

### Cogs vs Clips Game

Teams of agents ("cogs") compete for control of **junctions** (formerly "chargers"), gather resources from
**extractors**, deposit in **hubs**, and use **gear** for upgrades. The game emphasizes cooperation through alignment
and resource-sharing mechanics.

### CLI Commands

```bash
cogames list-missions          # Show available missions
cogames play <mission>         # Interactive play
cogames evaluate <mission>     # Run evaluation suite
cogames submit <policy>        # Submit to leaderboard
cogames leaderboard            # View rankings
```

---

## 6. CoGames-Agents: Scripted and Evolved Policies

**Location:** `packages/cogames-agents/` | **Languages:** Python + compiled Nim

### Python Scripted Agents

```
policy/scripted_agent/
├── cogsguard/
│   ├── control_agent.py    # Base control agent with role assignment
│   ├── miner.py            # Resource gathering specialist
│   ├── aligner.py          # Alignment/cooperation specialist
│   ├── scout.py            # Exploration and reconnaissance
│   └── teacher.py          # Teacher agent for curriculum learning
├── common/
│   ├── roles.py            # Role definitions and assignment
│   ├── geometry.py         # Pathfinding and spatial reasoning
│   └── tag_utils.py        # Tag manipulation utilities
├── baseline_agent.py       # Basic baseline policy
├── demo_policy.py          # Example/template policy
└── unclipping_agent.py     # Counter-clipping mechanics
```

### Nim Agents (high-performance compiled)

```
policy/nim_agents/
├── nim_agents.nim           # Main agent framework
├── cogsguard_agents.nim     # CogsGuard-specific agents
├── random_agents.nim        # Random baselines
├── racecar_agents.nim       # Racing game agents
├── thinky_agents.nim        # Thinking/planning agents
├── ladybug_agent.nim        # Ladybug agent
└── agents.py                # Python wrapper for Nim bindings
```

### Evolution System

`policy/evolution/` - Evolutionary training for developing agent policies.

### Agent Registry

| Name               | Type       | Purpose                     |
| ------------------ | ---------- | --------------------------- |
| `baseline`         | Python     | Basic baseline              |
| `thinky`           | Nim        | Planning agent              |
| `race_car`         | Nim        | Speed-optimized             |
| `ladybug`          | Nim        | Ladybug behavior            |
| `role` / `role_py` | Nim/Python | Role-based CogsGuard        |
| `wombo`            | Nim        | Mixed-role agent            |
| `miner`            | Python     | Resource gathering          |
| `scout`            | Python     | Exploration                 |
| `aligner`          | Python     | Cooperation                 |
| `teacher`          | Python     | Curriculum learning         |
| `pinky`            | Python     | Alignment-focused           |
| `planky`           | Python/Nim | Navigation/gear acquisition |

---

## 7. Agent Package: Policy Architecture System

**Location:** `agent/` | **Purpose:** Modular, config-driven neural network policies

### Core Design

Policies are built by composing components sequentially via `TensorDictSequential`. Each component reads/writes to a
shared `TensorDict`, enabling clean data flow without tight coupling.

### Policy Classes

```python
class PolicyArchitecture(Config):
    class_path: str                     # Path to policy class
    components: List[ComponentConfig]   # Sequential component pipeline
    action_probs_config: ComponentConfig
    critic_quantiles: Optional[int]

class Policy(MultiAgentPolicy, nn.Module):
    # Abstract: forward(td: TensorDict, action: Optional[Tensor]) -> TensorDict
    # State: reset_memory(), initial_agent_state(), load/dump_agent_state()

class PolicyAutoBuilder(Policy):
    # Builds from config: components -> TensorDictSequential -> forward()

class CheckpointPolicy:    # Wraps safetensors checkpoint bundles
class DistributedPolicy:   # DDP wrapper for distributed training
class ExternalPolicyWrapper: # Evaluation-only wrapper for external policies
```

### Forward Pass Pipeline (Observation to Action)

```
Raw env_obs (bytes)
    |
ObsShim (ObsShimTokens / ObsShimBox)        # Parse and normalize observations
    |
ObsTokenizer (ObsAttrEmbedFourier)           # Embed features + Fourier coordinates
    | [B, T, feat_dim] where feat_dim = attr_embed_dim + 4*num_freqs + 1
ObsEncoder (ObsLatentAttn / ObsPerceiverLatent)  # Cross-attention to latent space
    | [B, latent_dim]
Core (CortexTD / Mamba / LSTM / HRM)         # Recurrent/memory processing
    | [B, core_out_features]
Actor MLP -> ActorQuery -> ActorKey           # Action logits [B, num_actions]
Critic MLP                                    # Value estimation [B, 1]
ActionProbs                                   # Sample/evaluate actions
    | actions, log_probs, entropy
```

### Components

| Component           | File                | Purpose                                          |
| ------------------- | ------------------- | ------------------------------------------------ |
| ObsShimTokens       | `obs_shim.py`       | Token observation parsing                        |
| ObsShimBox          | `obs_shim.py`       | Box observation normalization                    |
| ObsAttrEmbedFourier | `obs_tokenizers.py` | Fourier coordinate + attribute embedding         |
| ObsAttrCoordEmbed   | `obs_tokenizers.py` | Learnable coordinate embedding                   |
| ObsLatentAttn       | `obs_enc.py`        | Cross-attention perceiver encoder                |
| CortexTD            | `cortex.py`         | Cortex stack wrapper (xLSTM architecture)        |
| HRM                 | `hrm.py`            | Hierarchical Reasoning Module (RMSNorm + SwiGLU) |
| Mamba               | `mamba/`            | Mamba2 SSM with optional attention               |
| MLP                 | `misc.py`           | Variable-depth feedforward                       |
| ActionEmbedding     | `action.py`         | Action name to embedding mapping                 |
| ActorQuery/ActorKey | `action.py`         | Query-key action scoring                         |
| ActionProbs         | `actor.py`          | Action sampling with masking                     |
| CNNEncoder          | `cnn_encoder.py`    | CNN for fixed-size spatial inputs                |
| SwinEncoder         | `swin_encoder.py`   | Shifted window attention                         |

### Policy Architecture Variants

| Variant              | Core                   | Notes                                               |
| -------------------- | ---------------------- | --------------------------------------------------- |
| `ViTDefaultConfig`   | CortexTD (Axon blocks) | Default architecture, configurable latent_dim/heads |
| `CortexBaseConfig`   | CortexStack            | Flexible Cortex stack configuration                 |
| `MemoryFreeConfig`   | None (MLP only)        | Speed-optimized, no recurrence                      |
| `FastConfig`         | CNN + CortexTD         | Alternative construction (not PolicyAutoBuilder)    |
| `DramaPolicyConfig`  | Mamba2                 | Dynamic Reasoning Architecture                      |
| `MambaSlidingConfig` | Mamba + sliding window | Windowed context for long episodes                  |
| `TrXLConfig`         | Transformer-XL         | Attention-based memory                              |
| `ViTGRPOConfig`      | ViT + GRPO             | Group Relative Policy Optimization                  |
| `ViTQuantileConfig`  | ViT + distributional   | Quantile-based value estimation                     |
| `AgaLiteConfig`      | Lightweight            | Reduced parameter count                             |

---

## 8. Cortex: Neural Memory and Recurrent Backbones

**Location:** `packages/cortex/` | **Type:** PyTorch + Triton kernels

Modular library for composable recurrent neural network stacks:

```
CortexStack
  +-- [Block, Block, Block, ...]    # Sequential blocks with skip connections

Block Types:
  BaseBlock        # Base interface
  PreUpBlock       # Input projection before cell
  PostUpBlock      # Output projection after cell
  ColumnBlock      # Mixture of Experts (MoE)
  AdapterBlock     # Adapter layers
  PassthroughBlock # Identity pass-through

Memory Cells:
  LSTMCell         # Standard LSTM
  mLSTMCell        # Matrix LSTM (extended state)
  sLSTMCell        # Scalar LSTM (simplified)
  AxonCell         # Custom Axon-based recurrence
  CausalConv1D     # 1D causal convolution
```

**Key Features:**

- **Composable stacks**: Mix different cell types in a single stack
- **GPU-optimized**: Custom Triton kernels for Linux GPU training
- **HuggingFace parity**: Tests verify output matches HuggingFace Llama
- **Configurable precision**: float32, float16, bfloat16 storage
- **MoE support**: Column blocks enable mixture-of-experts patterns

---

## 9. Metta Core: RL Training Framework

**Location:** `metta/` | **Type:** Private (not published separately) | **Size:** ~174 files, ~29,641 lines

### Module Organization

```
metta/
├── rl/                 # Core RL training system
│   ├── trainer.py      # Main Trainer class (facade for all training)
│   ├── trainer_config.py # TrainerConfig (batch=2M, lr=0.00737, etc.)
│   ├── training/       # 24 files: core loop, experience, components
│   ├── loss/           # 24 files: PPO, GRPO, contrastive, kickstarters
│   ├── advantage.py    # GAE/V-trace with CUDA kernel
│   ├── checkpoint_manager.py
│   └── system_config.py
├── tools/              # CLI tools: train, eval, play, sweep, replay
├── sim/                # Simulation runner, remote eval, policy serving
├── cogworks/           # Curriculum learning framework
│   └── curriculum/     # Task generator, learning progress, regret tracking
├── adaptive/           # Adaptive experiment controller
├── gridworks/          # FastAPI server for grid config
├── map/                # Terrain generation
├── sweep/              # Hyperparameter optimization
├── setup/              # CLI, installation, project setup
└── protobuf/           # Protobuf definitions
```

### Training System

**Trainer** (`metta/rl/trainer.py`): Main facade managing the training lifecycle.

**Training Loop:**

1. **Initialize**: Policy to device, losses, experience buffer, optimizer, components
2. **Main loop** while `agent_step < total_timesteps`:
   - **Rollout Phase**: Collect experience from vectorized environments
   - **Training Phase**: Sample minibatches, compute losses + advantages, backprop
   - **Epoch callbacks**: Checkpointing, evaluation, stats reporting, wandb logging

### Default Hyperparameters

| Parameter            | Value                 |
| -------------------- | --------------------- |
| Batch size           | 2,097,152 agent steps |
| Minibatch size       | 16,384                |
| BPTT horizon         | 256 steps             |
| Update epochs        | 1                     |
| Total timesteps      | 10 billion            |
| Learning rate        | 0.00737503357231617   |
| GAE lambda           | 0.95                  |
| Discount gamma       | 1.0                   |
| PPO clip coefficient | 0.22                  |
| Entropy coefficient  | 0.01                  |
| Optimizer            | AdamW ScheduleFree    |

### Loss Functions (24+)

**Core PPO:**

- `ppo_actor.py` - PPO actor loss with clipping, entropy bonus, advantage normalization
- `ppo_critic.py` - PPO critic loss with value clipping

**Advanced:**

- `grpo.py` - Group Relative Policy Optimization
- `cmpo.py` - Contrastive Multi-Policy Optimization
- `contrastive.py` - Contrastive learning loss
- `quantile_ppo_critic.py` - Distributional value estimation
- `stable_latent.py` - Latent state regularization
- `future_latent_ema.py` - EMA-based future prediction
- `vit_reconstruction.py` - Vision transformer reconstruction

**Imitation/Kickstarter:**

- `kickstarter.py` - Supervised learning warm-start
- `sliced_kickstarter.py` - Sliced student/teacher/PPO
- `logit_kickstarter.py` - Action logit imitation
- `eer_kickstarter.py` / `eer_cloner.py` - Expert-enabled regret
- `sliced_scripted_cloner.py` - Scripted policy cloning
- `action_supervised.py` - Action supervision

### Training Components

| Component                  | Purpose                                             |
| -------------------------- | --------------------------------------------------- |
| Checkpointer               | Policy checkpoint saving (safetensors format)       |
| ContextCheckpointer        | Full trainer state checkpointing                    |
| Evaluator                  | Policy evaluation on separate tasks during training |
| StatsReporter              | Metrics to wandb and stats server                   |
| ProgressLogger             | Training progress tracking                          |
| WandbLogger / WandbAborter | W&B integration and abort detection                 |
| Heartbeat                  | Periodic health signals                             |
| GradientReporter           | Gradient statistics                                 |
| TorchProfiler              | PyTorch profiling                                   |
| UpdateEpochAutoTuner       | Auto-tune epochs based on KL/clipfrac               |
| LossScheduler              | Loss gating and scheduling over training            |

### Curriculum Learning (`metta/cogworks/curriculum/`)

Dynamic task selection based on learning progress:

```
CurriculumConfig
  ├── task_generator: AnyTaskGeneratorConfig   # How to create tasks
  ├── num_active_tasks: 64                      # Concurrent tasks
  ├── min_presentations_for_eviction: 5         # Min samples before removing
  └── algorithm_config:
      ├── DiscreteRandomConfig                  # Uniform random
      ├── LearningProgressConfig                # Progress-based (default)
      ├── PrioritizedRegretConfig               # Regret minimization
      └── RegretLearningProgressConfig          # Hybrid
```

**Bucketed Task Generation**: Define axes of variation (e.g., reward weights from 0 to 1.0) and the curriculum explores
the parameter space automatically.

### Advantage Computation

- `compute_advantage()`: Main function with CUDA/CPU/MPS fallback
- Custom CUDA kernel: `td_lambda_reverse_scan_cuda()` for V-trace
- Distributed advantage normalization across workers
- PufferLib integration for high-performance computation

---

## 10. The Recipe and Tool System

**Locations:** `recipes/`, `common/src/metta/common/tool/`, `tools/run.py`

Recipes are Python modules that define **tool makers** -- functions returning configured tool instances. They bundle
environment, curriculum, and evaluation configs into coherent experiment packages.

### Recipe Structure

```python
# recipes/experiment/arena.py

def mettagrid(num_agents=24) -> MettaGridConfig:
    """Shared environment config"""
    return eb.make_arena(num_agents=num_agents)

def make_curriculum(...) -> CurriculumConfig:
    """Curriculum setup with bucketed exploration"""

def simulations(...) -> list[SimulationConfig]:
    """Evaluation simulations (same env for consistency)"""

def train(...) -> TrainTool:
    """Main training tool maker"""
    return TrainTool(
        trainer=TrainerConfig(...),
        training_env=TrainingEnvironmentConfig(curriculum=make_curriculum()),
        evaluator=EvaluatorConfig(simulations=simulations()),
    )

def evaluate(policy_uris) -> EvaluateTool:
    """Evaluation tool maker"""

def play(policy_uri) -> PlayTool:
    """Interactive play tool maker"""
```

### CLI Invocation

```bash
# Two-token form (most common)
./tools/run.py train arena run=test trainer.total_timesteps=100000

# Dotted form
./tools/run.py arena.train run=test

# Full qualified path
./tools/run.py recipes.experiment.arena.train run=test

# Listing and help
./tools/run.py arena --list          # Show tools in arena recipe
./tools/run.py train --list          # Show recipes with train tool
./tools/run.py arena.train --dry-run # Validate config without running
```

### Recipe Organization

- **Production** (`recipes/prod/`): CI-validated, stable recipes
  - `arena_basic_easy_shaped.py` - Default shaped-reward arena
  - `cvc/` - Cogs vs Clips production recipes
- **Experiment** (`recipes/experiment/`): Work-in-progress
  - `arena.py`, `navigation.py`, `cogsguard.py`, `machina_1.py`
  - `losses/` - Loss function experiments (adamw, grpo, cmpo, schedulefree)
  - `user/` - Per-user experimental recipes
  - `scratchpad/` - Templates and sandbox

### Tool Types

| Tool       | Class          | Purpose                                |
| ---------- | -------------- | -------------------------------------- |
| `train`    | `TrainTool`    | Full training loop with curriculum     |
| `evaluate` | `EvaluateTool` | Policy evaluation on simulation suites |
| `play`     | `PlayTool`     | Interactive visualization              |
| `replay`   | `ReplayTool`   | Replay recorded episodes               |
| `sweep`    | `SweepTool`    | Hyperparameter sweep                   |

---

## 11. Common Package: Shared Utilities

**Location:** `common/`

```
common/src/metta/common/
├── tool/              # Tool execution framework (run_tool.py, recipe.py, registry)
├── util/              # Utilities: git, logging, memoization, profiling
├── auth/              # Authentication configuration
├── otel/              # OpenTelemetry tracing
├── datadog/           # Datadog metrics integration
├── tests_support/     # Test utilities and fixtures
└── __init__.py        # suppress_noisy_logs(), package setup
```

**Dependencies:** cogames, wandb, opentelemetry, tenacity

---

## 12. App Backend: Observatory API Server

**Location:** `app_backend/` | **Framework:** FastAPI + PostgreSQL | **URL:** `api.observatory.softmax-research.net`

The Observatory backend manages policies, episodes, evaluation tasks, jobs, and tournaments for the Alignment League
Benchmark platform.

### API Routes (52+ endpoints across 7 routers)

| Router                 | Endpoints | Purpose                                         |
| ---------------------- | --------- | ----------------------------------------------- |
| `stats_routes.py`      | 8         | Policy CRUD, episode bulk upload                |
| `eval_task_routes.py`  | 5         | Evaluation task lifecycle (create/claim/finish) |
| `job_routes.py`        | 5         | Job orchestration (create/status/update)        |
| `tournament_routes.py` | 5         | Tournament submit, leaderboard, matches         |
| `sweep_routes.py`      | 3         | W&B sweep management                            |
| `sql_routes.py`        | 1         | DuckDB query interface against S3 data          |
| `smart_plug_routes.py` | ~3        | Infrastructure control                          |

### Database Schema (8 migrations)

**Core Tables:**

- `policies` - Policy metadata (UUID PK)
- `policy_versions` - Variants with S3 paths, git hashes, JSONB spec
- `episodes` - Recordings with replay_url, thumbnail_url
- `episode_tags` / `episode_policies` / `episode_policy_metrics` - Episode metadata
- `eval_tasks` / `task_attempts` - Evaluation task lifecycle
- `job_requests` - K8s job specs (pending -> dispatched -> running -> completed/failed)
- `sweeps` - W&B sweep tracking

**Tournament Tables (Migration 4+):**

- `seasons`, `pools`, `pool_players`, `matches`, `match_players`, `membership_changes`

### Job Dispatch System

```
app_backend/src/metta/app_backend/job_runner/
├── dispatcher.py           # K8s batch job creation with S3 presigned URLs
├── tournament_cluster.py   # EKS auth via cross-account IAM STS
├── watcher.py              # Job status reconciliation
├── episode_recording.py    # Episode capture
└── config.py               # S3 buckets, presigned URL config
```

### Observability

- **OpenTelemetry**: Job state transitions, stage durations, running/outstanding counts
- **Datadog**: OTLP metrics export with Delta aggregation
- **Logging**: Performance loggers for dashboard, DB, routes

---

## 13. Tournament System

**Location:** `app_backend/src/metta/app_backend/tournament/`

```
Commissioners (decide membership):
  ├── beta.py              # Default commissioner
  ├── beta_cvc.py          # CvC-specific
  └── beta_cogsguard.py    # CogsGuard-specific

Referees (schedule and score matches):
  ├── base.py              # Base referee with scheduling
  ├── selfplay.py          # Self-play evaluation
  ├── cvc.py               # Curriculum-based
  └── cogsguard.py         # Guard/baseline evaluation

Infrastructure:
  ├── registry.py          # Season/tournament configuration
  ├── pairing.py           # Match pairing logic
  └── envs.py              # Environment configuration
```

### Tournament Flow

1. Policies submitted to pools via API
2. Commissioner tracks membership changes (add/remove)
3. Referee schedules matches based on membership and pairing rules
4. Matches dispatched as K8s jobs on tournament cluster
5. Results collected, scores synchronized to database
6. Leaderboard updated

---

## 14. Web Frontends

| App                              | Framework                 | Purpose                                                     |
| -------------------------------- | ------------------------- | ----------------------------------------------------------- |
| Observatory (`web/observatory/`) | Next.js (App Router)      | Dashboard: episodes, policies, tournaments, SQL queries     |
| Home (`web/home/`)               | Vite + React + TypeScript | Landing page                                                |
| Gridworks (`web/gridworks/`)     | Frontend                  | Grid visualization (connects to `metta/gridworks/` FastAPI) |
| Softmax.com (`web/softmax.com/`) | Next.js                   | Company website                                             |

---

## 15. DevOps and Infrastructure

**Location:** `devops/`

### Cloud Infrastructure

| Component               | Technology                     | Purpose                                |
| ----------------------- | ------------------------------ | -------------------------------------- |
| **Compute**             | AWS EKS (auto mode)            | Kubernetes cluster for jobs            |
| **IaC**                 | OpenTofu/Terraform + Spacelift | Infrastructure automation              |
| **GPU Training**        | SkyPilot                       | Cloud GPU job launching (L4 instances) |
| **Local GPU**           | Mettabox (metta0-metta4)       | Docker containers on GPU machines      |
| **Monitoring**          | Datadog + OpenTelemetry        | Metrics, tracing, monitors             |
| **Experiment Tracking** | Weights & Biases               | Training runs, sweeps, artifacts       |
| **Storage**             | AWS S3 + EFS                   | Policies, episodes, shared files       |
| **Database**            | RDS PostgreSQL                 | Observatory backend                    |
| **Container Registry**  | AWS ECR                        | Docker images                          |
| **SSL**                 | cert-manager                   | Certificate management                 |

### SkyPilot (`devops/skypilot/`)

Cloud job launching for GPU training:

- `launch.py` - Launch training jobs (multi-GPU support)
- `sandbox.py` - Persistent GPU dev environments (48h auto-stop)
- `cost.py` - Cost monitoring (~$0.70-7.20/hr for L4 instances)
- Dashboard: `skypilot-api.softmax-research.net`

### Mettabox (`devops/mettabox/`)

Remote machine orchestration for GPU cluster:

- `run` - Execute training jobs with tmux
- `exec` - Arbitrary commands in Docker containers
- `instrument` - Monitor logs with GPU snapshots
- `profile` - CPU/GPU profiling
- `audit` - System resource inspection

### Terraform Stacks (`devops/tf/`)

| Stack          | Purpose                                                     |
| -------------- | ----------------------------------------------------------- |
| `eks/`         | EKS cluster (VPC 10.0.0.0/16, 3 AZs, EBS CSI, Pod Identity) |
| `observatory/` | Observatory Helm deployment                                 |
| `softmax.com/` | Website deployment with OAuth2 proxy                        |
| `tournament/`  | Tournament infrastructure                                   |
| `monitoring/`  | Datadog/observability stack                                 |
| `shared-efs/`  | EFS provisioning                                            |
| `s3-public/`   | Public S3 bucket                                            |
| `spacelift/`   | Self-managing CI/CD                                         |
| `ecr/`         | Docker registry                                             |

### Helm Charts (`devops/charts/`)

16 charts: observatory, observatory-backend, softmax-com, home, orchestrator, tournament, cronjob, system, cert-manager,
and more.

### Docker

- **Main image** (`devops/docker/Dockerfile`): CUDA 12.8.1, Ubuntu 24.04, Bazel, Nim, Python 3.12
- **App backend** (`app_backend/Dockerfile`): Ubuntu 22.04, uv-managed Python
- **Dev container** (`.devcontainer/Dockerfile`): Full dev environment with all toolchains

---

## 16. Skills System: AI Assistant Automation

**Location:** `skills/` (46 skills) | **Consumers:** Claude Code (`.claude/skills` symlink), Codex (`.codex/skills`
symlink)

| Prefix                  | Count | Purpose                                             |
| ----------------------- | ----- | --------------------------------------------------- |
| `cb.*`                  | 6     | Code quality: cleanup, lint, review, simplify       |
| `pr.*`                  | 9     | PR management: submit, fix CI, address review, sync |
| `st.*`                  | 8     | Graphite stack: create, split, extract, fix         |
| `db.*` / `t.*`          | 4     | Debugging and testing                               |
| `sk.*`                  | 5     | Skill management: create, update, sync              |
| `tr.*`                  | 5     | Training: cogames commands, checkpoints, recipes    |
| `do.*`                  | 2     | DevOps: mettabox, worktrunk                         |
| `n.*`                   | 2     | Infrastructure: debug jobs, observatory             |
| `cf.*` / `wt.*` / `r.*` | 3     | Control flow, cleanup, packaging                    |
| `relh.*`                | 3     | Branch hygiene, merge conflicts, run recipes        |

### Key Skills

- `pr.submit` - Lint, submit to Graphite, run tests in parallel with CI, fix and re-submit on failure
- `st.issue-to-stack` - Work in a worktree branch, then split into a Graphite PR stack
- `tr.cogames-command` - Craft cogames commands for train/play/eval
- `do.mettabox-ops` - Manage GPU container operations
- `t.run-tests` - Progressive test running: failed -> pytest -> metta ci

---

## 17. Build Systems and Tooling

### Python: uv + setuptools

- **Package manager:** uv (Astral) for fast dependency resolution
- **Build backend:** setuptools for all packages
- **Workspace:** 11 members in `pyproject.toml`
- **Lock file:** `uv.lock`
- **Python version:** 3.12.11 (pinned in `.python-version`)

### C++: Bazel 9.0

- **Used by:** mettagrid C++ core
- **Module system:** Bzlmod (modern Bazel)
- **Bindings:** pybind11 for Python interop
- **Compiler:** C++20 required
- **Custom backend:** `bazel_build.py` for Python wheel building

### Nim

- **Used by:** Mettascope visualization, fast agent implementations
- **Build:** nimble (Nim package manager)
- **Version:** Nim >= 2.2.4
- **Output:** Compiled shared libraries (.so/.dylib/.dll) with Python ctypes bindings

### JavaScript/TypeScript: pnpm + turbo

- **Package manager:** pnpm 10.11.0
- **Build orchestrator:** turbo 2.5.5 (for monorepo builds)
- **Formatter:** prettier 3.6.2 (with sh and toml plugins)

### Nix

- **Purpose:** Reproducible development environment
- **Config:** `flake.nix` targeting x86_64-linux
- **Provides:** Python, Bazel, Nim, pnpm, Node.js 22, Go 1.23.5, Rust, emscripten
- **GPU support:** ROCm 6.4 for AMD GPUs

---

## 18. CI/CD Pipeline

**Location:** `.github/workflows/` (36 workflow files)

### Core Workflows

| Workflow                    | Purpose                                             |
| --------------------------- | --------------------------------------------------- |
| `checks.yml`                | Main lint + test gate (ruff, import-linter, pytest) |
| `_build-and-deploy.yml`     | Main build and deployment pipeline                  |
| `claude.yml`                | Claude AI code review (30KB config)                 |
| `dependency-validation.yml` | Dependency compatibility checks                     |
| `validate-pyproject.yml`    | Project configuration validation                    |

### Release Workflows

| Workflow                     | Package                     |
| ---------------------------- | --------------------------- |
| `release-mettagrid.yml`      | mettagrid PyPI release      |
| `release-cogames.yml`        | cogames PyPI release        |
| `release-cortexcore.yml`     | cortex PyPI release         |
| `release-pufferlib-core.yml` | pufferlib-core PyPI release |
| `stable-release.yml`         | Stable release coordination |

### Build Workflows

| Workflow                      | Purpose                |
| ----------------------------- | ---------------------- |
| `build-image.yml`             | Main Docker image      |
| `build-app-backend-image.yml` | Backend API image      |
| `build-*-image.yml`           | Various service images |
| `build-pages.yml`             | Documentation site     |

### AI Review Workflows

| Workflow                     | Focus                  |
| ---------------------------- | ---------------------- |
| `claude-review-base.yml`     | General code review    |
| `claude-review-comments.yml` | PR comment review      |
| `claude-review-einops.yml`   | Einops usage review    |
| `claude-review-style.yml`    | Style guide compliance |
| `claude-review-types.yml`    | Type safety review     |

### Custom Actions (`.github/actions/`)

10 reusable actions: cleanup-cancelled-runs, detect-external-pr, discord-webhook, docker-build, eks-configure,
fetch-artifacts, helm-deploy, pr-assignment, pr-digest, setup-environment.

---

## 19. Active Development Areas

Based on git history analysis as of January 2026:

### Highly Active

1. **CogsGuard Game System** - Continuous balancing, new agent types (Pinky, Planky, Wombo), mission variants, reward
   presets, role-cycle policies. The primary game under development.

2. **Tournament/Leaderboard Infrastructure** - Memory optimization, Datadog monitoring, K8s event storage, season
   management, referee scheduling.

3. **Agent Architecture** - New policy variants (Drama/Mamba, quantile, GRPO), Cortex stack improvements, observation
   encoding refinements.

4. **Mettagrid Environment** - Major reward system overhaul (AgentRewards to GameValue), event scheduler, new object
   types (extractors, collectives), coordinate system fixes.

5. **Skills System** - New skills (wt.cleanup, st.issue-to-stack), auto-cleanup for worktree operations, skill sync
   infrastructure.

### Moderately Active

6. **Observatory Backend** - Next.js rewrite, new API endpoints, SQL query interface, tournament routes.

7. **Training Infrastructure** - macOS MPS support, torch profiling, startup optimization, distributed training
   improvements.

8. **DevOps** - Helm/helmfile migration, tournament cluster setup, Karpenter NodePool, cost monitoring.

### Areas of Recent Progress

- **Reward System Overhaul**: Moved from hardcoded `AgentRewards` to flexible `GameValue` system with scope awareness
- **Coordinate System Fix**: Multi-commit fix swapping row/col ordering across the entire codebase
- **Collective/Faction System**: Team-based mechanics with shared inventories and alignment tracking
- **Curriculum Learning**: Bucketed task generation with learning progress algorithms
- **Event Scheduler**: Time-triggered effects for dynamic game environments
- **Nimby version consolidation**: Unified `.nimby-version` file

---

## 20. Deprecated and Legacy Code

### Confirmed Removed

| Item                           | Reference   | Replacement                    |
| ------------------------------ | ----------- | ------------------------------ |
| **Assembler System**           | PR #5908    | Removed entirely               |
| **Codebot**                    | PR #5117    | None (separate project)        |
| **Legacy Machina Game**        | PR #5719    | CogsGuard                      |
| **Old Tournament Code**        | PR #4674    | Season-based tournament system |
| **Old Observatory Pages**      | Various PRs | New Next.js Observatory        |
| **PolicyCache/Metadata/Store** | PR #2366    | URI-based checkpoints          |
| **Old Job Runner Process**     | PR #5558    | Single episode runner          |
| **Charger** (object name)      | PR #5974    | Renamed to Junction            |

### Partially Deprecated

| Item                    | Evidence                   | Notes                                            |
| ----------------------- | -------------------------- | ------------------------------------------------ |
| `_load_legacy_cache()`  | In pr_similarity.py        | Cache migration still in codebase                |
| Old policy URI format   | Warning in play.py         | "Using policy from deprecated-format policy uri" |
| logit_kickstarter       | TODO comment               | "we should do this without reshaping"            |
| Hydra/OmegaConf configs | Being replaced by Pydantic | Transition ongoing                               |

### Potentially Stale

- `gastown/` directory - appears minimal/placeholder
- Some experiment recipes in `recipes/experiment/` may be inactive
- `typings/` directory - type stubs may lag behind implementation
- Some `notebooks/` may reference old APIs

---

## 21. Appendix: Entry Points and CLI Commands

### Python CLI Entry Points (from pyproject.toml)

```bash
metta              # metta.setup.metta_cli:cli_entry - Main CLI
skypilot           # devops.skypilot.launch:cli_entry - Cloud job launcher
skypilot-sandbox   # devops.skypilot.sandbox:cli_entry - GPU dev environments
cogames            # cogames.main:app - Game CLI
mettagrid-demo     # mettagrid demo script
```

### Primary Commands

```bash
# Training
uv run ./tools/run.py train arena run=my_experiment trainer.total_timesteps=100000

# Evaluation
uv run ./tools/run.py evaluate arena policy_uri=file://./train_dir/my_run/checkpoints

# Interactive play
uv run ./tools/run.py play arena policy_uri=file://./train_dir/my_run/checkpoints

# Replay
uv run ./tools/run.py replay arena

# List available tools/recipes
uv run ./tools/run.py arena --list

# Metta CLI
metta status          # Check component status
metta install         # Reinstall dependencies
metta pytest tests/   # Run tests
metta lint            # Run linters

# CoGames CLI
cogames list-missions
cogames play <mission>
cogames evaluate <mission>
cogames submit <policy>

# SkyPilot
skypilot launch <recipe>       # Launch cloud training
skypilot-sandbox create        # Create GPU dev environment

# Linting
uv run lint-imports            # Check import layer rules
```

### Testing

```bash
metta pytest tests/path/to/test.py -v    # Specific test
metta pytest --changed                    # Tests affected by changes
pytest -n auto --import-mode=importlib    # Parallel execution (default)
```

### Key URLs

| Service            | URL                                    |
| ------------------ | -------------------------------------- |
| Observatory        | `observatory.softmax-research.net`     |
| Observatory API    | `api.observatory.softmax-research.net` |
| SkyPilot Dashboard | `skypilot-api.softmax-research.net`    |

---

## 22. Update History

### 2026-01-31 - Initial Version

**Commit:** `4708bc8bcf` (branch: musing-mcclintock, main)

Initial comprehensive overview generated from full codebase exploration. Covers all major subsystems: mettagrid (C++
game environment), cogames (mission configs), cogames-agents (scripted/evolved policies), agent (policy architecture),
cortex (neural memory), metta core (RL training), recipes/tools (experiment management), app_backend (Observatory API),
tournament system, web frontends, devops/infrastructure, skills system, build systems, and CI/CD.

**Codebase state at time of writing:**

- Python 3.12.11, Bazel 9.0.0, Nim >= 2.2.4, pnpm 10.11.0
- 11 Python workspace members, 6 packages in `packages/`
- 36 GitHub Actions workflows, 46 AI assistant skills
- Primary game: Cogs vs Clips (CogsGuard) on the Alignment League Benchmark
- Recent major changes: GameValue reward system, coordinate system fix, collective/faction system, event scheduler,
  nimby version consolidation
