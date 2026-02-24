# Running training jobs

This page covers how to run training jobs locally and on SkyPilot sandboxes.

For general `tools/run.py` usage (recipes, discovery, override syntax), see `docs/tools.md`.

## Table of contents

- [SkyPilot sandboxes](#skypilot-sandboxes)
- [Discovering And Explaining Training Knobs](#discovering-and-explaining-training-knobs)
- [Kickstarting with a teacher](#kickstarting-with-a-teacher)
- [Routed adapters for multi-agent training](#routed-adapters-for-multi-agent-training)
- [Horde prediction framework](#horde-prediction-framework)
- [Useful recipes and games](#useful-recipes-and-games)
  - [CogsGuard](#cogsguard)
  - [CogsGuard MARLBRO](#cogsguard-marlbro)

## SkyPilot sandboxes

### Create a sandbox

Create an 8-GPU sandbox:

```bash
./devops/skypilot/sandbox.py new --gpus 8 --name subho-8x-1
```

Common management commands (examples; see `./devops/skypilot/sandbox.py new --help` for the full list):

- **SSH in**: `ssh <sandbox-name>`
- **Stop (keeps data)**: `uv run sky stop <sandbox-name>`
- **Restart**: `uv run sky start <sandbox-name>`
- **Delete completely**: `uv run sky down <sandbox-name>`
- **Logs**: `uv run sky logs <sandbox-name>`
- **Retry a stuck launch**: `uv run sky launch -c <sandbox-name> --no-setup`

### Run a training job inside a sandbox

Once you are SSH’d into a sandbox, run distributed training via `torchrun` using `devops/run.sh`:

```bash
./devops/run.sh recipes.experiment.cogsguard.train run=your_run_name
```

Notes:

- `devops/run.sh` automatically sets up `torchrun` using `NUM_GPUS`, `NUM_NODES`, `MASTER_ADDR`, `MASTER_PORT`, and
  `NODE_INDEX`.
- Any arguments after the module path are passed through to `tools/run.py` as tool args (`key=value` overrides).

### Launch a job with SkyPilot (no interactive SSH)

If you want to submit a job from your local machine using SkyPilot:

```bash
./devops/skypilot/launch.py recipes.experiment.cogsguard.train --gpus 8 --max-runtime-hours 120 -- run=your_run_name
```

Notes:

- By default, `launch.py` checks that your working tree is clean and the current commit is pushed (so the cloud job
  matches your code).
- You can use `--git-ref <branch-or-commit>` to launch a specific ref, or `--skip-git-check` to bypass validation.
- Use `--` to separate launch flags (e.g. `--gpus`, `--nodes`, `--max-runtime-hours`) from tool args (`key=value`
  overrides).

## Discovering And Explaining Training Knobs

The training entrypoint is `TrainTool` (`metta/tools/train.py`). Recipes (e.g. `recipes/experiment/cogsguard.py`) return
a configured `TrainTool` instance which you then override via `key=value` args.

```bash
# List all available config fields for a recipe's train tool.
./tools/run.py train arena -h

# Validate args (construct + override + pydantic validate), without running.
./tools/run.py train arena --dry-run run=my_run

# Print the effective config (after tool-specific defaulting/mutations), without running.
./tools/run.py train arena --print-effective-config run=my_run
```

## Kickstarting with a teacher

Kickstarting can be used with any recipe that accepts `teacher` (e.g. CogsGuard, Machina, etc.).

### Examples

**CogsGuard default teacher (Machina 1 layout by default):**

```bash
./devops/skypilot/launch.py recipes.experiment.cogsguard.train --gpus 8 --max-runtime-hours 120 -- \
  run=your_run_name
```

To switch layouts, pass `layout=arena` (or `layout=machina_1` explicitly).

To disable the default teacher, override the policy URI:

```bash
./devops/skypilot/launch.py recipes.experiment.cogsguard.train --gpus 8 --max-runtime-hours 120 -- \
  run=your_run_name \
  teacher.policy_uri=null
```

### Custom teacher overrides

You can also specify a custom teacher by providing a `teacher.policy_uri` and choosing a mode. Two modes that work well
currently are `scripted.eer_cloner.sliced` and `scripted.supervisor.mixed`.

**JSON-style (single quoted override):**

```bash
./devops/skypilot/launch.py recipes.experiment.cogsguard.train --gpus 8 --max-runtime-hours 120 -- \
  'teacher={"mode":"scripted.eer_cloner.sliced","policy_uri":"metta://policy/cogsguard?gear=10","teacher_led_proportion":0.5,"student_led_proportion":0.5,"steps":1000000000,"anneal_start_step":0,"ppo_begin_step":0}' \
  run=your_run_name
```

**Dot-style overrides:**

```bash
./devops/skypilot/launch.py recipes.experiment.cogsguard.train --gpus 8 --max-runtime-hours 120 -- \
  run=your_run_name \
  teacher.policy_uri='metta://policy/cogsguard?gear=10' \
  teacher.mode=scripted.eer_cloner.sliced \
  teacher.teacher_led_proportion=0.5 \
  teacher.student_led_proportion=0.5
```

See `metta/rl/training/teacher.py` for available teacher modes and knobs (e.g. `teacher.kwargs.*` for per-mode config).

## Routed adapters for multi-agent training

Routed adapters are per-agent low-rank adapters (LoRA-style) injected into the Cortex policy’s linear layers. They’re a
useful middle ground between “one fully shared policy for all agents” and “a separate policy per agent”: you keep a
single shared trunk, but give each agent its own small set of parameters to specialize.

### How it works

When enabled, Cortex replaces linear-like modules with adapter-augmented versions. Each adapted module keeps its base
weights (the shared trunk), plus `num_slots` sets of low-rank adapter weights. At runtime, each batch element provides a
`route_id` (typically the agent index); the module selects the corresponding adapter slot and adds its low-rank delta on
top of the shared base computation.

In Metta’s multi-agent rollouts, `route_id` is derived from `agent_slot_ids` (agent index within an env), then mapped
into `[0, num_slots)` via modulo. This means:

- `num_slots == num_agents` gives each agent its own adapter.
- `num_slots < num_agents` makes multiple agents share an adapter slot (less capacity, but cheaper and encourages
  sharing).

### Key parameters and tradeoffs

- `routed_adapter.rank`: adapter capacity per slot (higher rank = more parameters per agent, typically better
  specialization). Tradeoff: higher rank increases memory usage and slows SPS due to extra matmuls/parameters. Rank `8`
  has worked well in practice for CogsGuard, but the right value depends on your perf budget.
- `routed_adapter.trunk_lr_mult`: gradient multiplier applied to the shared trunk parameters in the adapted module tree.
  Values `< 1` update the trunk slower than the adapters (often helpful to reduce cross-agent interference while letting
  adapters learn quickly). Tradeoff: too small can starve the trunk of learning signal; `0` effectively freezes the
  trunk (within the adapted module tree).
- `routed_adapter.num_slots`: number of adapter slots. More slots = more per-agent (or per-role) capacity; fewer slots =
  more sharing and lower overhead.

Other knobs you may occasionally want:

- `routed_adapter.alpha`: scales the adapter contribution (defaults to `rank`, which gives a scale of `1.0`).
- `routed_adapter.dropout`: regularization on the adapter path.
- `routed_adapter.freeze_base`: freezes the base linear weights (adapter-only learning).

### Example (CogsGuard)

```bash
./devops/run.sh recipes.experiment.cogsguard.train \
  run=your_run_name \
  variants='["no_clips","milestones","no_objective"]' \
  'teacher.policy_uri=metta://policy/nlanky?miner=4&aligner=2&disable_role_switching=1' \
  routed_adapter.enabled=true \
  routed_adapter.rank=8 \
  routed_adapter.trunk_lr_mult=0.5
```

## Horde prediction framework

Horde (`diff_horde`) is an auxiliary loss that trains the policy to predict a vector of user-defined _cumulants_
(GVF-style signals) from the rollout stream.

Recipes that accept `diff_horde_cumulants` (currently `recipes/experiment/cogsguard.py`) automatically set
`policy_architecture.horde_num_cumulants` to match the total cumulant size and attach the `diff_horde` loss to the
appropriate training slice(s).

CogsGuard also supports preset cumulant groups via `horde_variants` (implemented in
`metta/rl/diff_horde/presets/cogsguard.py`). Preset names are stackable and resolve into `diff_horde_cumulants`;
explicit `diff_horde_cumulants` entries with the same `name` override preset entries.

### CogsGuard preset variants

Available CogsGuard horde variants:

- `all`: alias that expands to all variants below.
- `junctions`: team-level junction control snapshot now (`cogs` and `clips` aligned junction counts).
- `vitals`: agent internal state now (`hp`, `energy`, `influence`, `solar`).
- `roles`: agent role/gear inventory now (`miner`, `aligner`, `scrambler`, `scout` amounts).
- `cortex_core`: policy-internal `core` representation (`td_key` cumulant over `core`).
- `economy_agent`: agent resource cargo now (`carbon`, `oxygen`, `germanium`, `silicon`, `heart` amounts).
- `economy_collective`: team bank/resource totals now for Cogs (`carbon`, `oxygen`, `germanium`, `silicon`, `heart`).
- `tempo`: episode progression signals (`steps`, `max_steps`, agent `reward_step`).
- `junction_events`: junction event flow (`gained/lost` for both teams) and agent align/scramble counts.
- `economy_flow`: resource/gear transaction deltas (agent gained/lost and team deposited/withdrawn flows).
- `action_counters`: per-agent action counters (`move/noop/change_vibe` outcomes, failures, cells visited).

### Spec format

`diff_horde_cumulants` is passed as JSON and can be either:

- a mapping of `name -> spec`, or
- a list of specs (each spec can include `name`; otherwise a default `cumulant_<i>` is assigned).

All spec kinds support:

- `scale` (float, default `1.0`)
- `clip` (`[min,max]`, optional)

### Supported cumulant kinds

- `info_scalar`: reads a scalar from `env_info[<key>]` (tensorized from the env `info` payload at rollout time for the
  requested keys). Keys are slash-separated (nested env dicts are flattened) and support an `env_` prefix alias, so
  `env_collective/...` matches raw payload keys like `collective/...`. Use env-level keys like
  `env_collective/cogs/aligned.junction` (broadcast to all agents in an env) or per-agent keys prefixed with `agent/`
  (sourced from the env `_per_agent_infos` payload, e.g. `agent/reward_step`). Values must be numeric scalars
  (non-scalar values are hard errors; missing keys use the loss-level default, `0.0` by default for `diff_horde`).
- `env_obs_feature`: extracts a single feature from token observations `env_obs` and reduces across matching tokens
  (`"mean"|"sum"|"max"`). `env_obs` is shaped like `[B,M,3]` bytes `{location, feature_id, value}`; empty token slots
  are padded with `location=255`. Set `feature` to a name (e.g. `"inv:hp"`) or numeric feature id; set `normalize=true`
  to divide `value` by the feature's configured normalization. `"mean"` divides by the number of matching tokens (if
  there are none, the cumulant is `0.0`).
- `td_key`: slices and/or reduces a TensorDict key from the rollout stream (e.g. `"core"` or `"actor_hidden"`). If
  `reduce` is set (`"mean"|"sum"|"max"`), the cumulant is a scalar. If you omit both `slice` and `reduce`, it uses the
  whole flattened vector and infers size from the policy/output tensor for that `key`. Provide `size` only when a key
  cannot be inferred from policy outputs.

Guidance: prefer instantaneous cumulants (`*.amount`, `aligned.junction`) over cumulative counters (`*.held`,
`*.success`) when possible; they are typically more stationary and easier to learn.

### Normalization defaults

`DiffHordeLoss` applies per-cumulant RMS normalization by default (`normalize_cumulants=true`) before computing targets,
with configurable EMA/clip knobs:

- `trainer.losses.diff_horde.normalize_cumulants`
- `trainer.losses.diff_horde.cumulant_rms_alpha`
- `trainer.losses.diff_horde.cumulant_rms_epsilon`
- `trainer.losses.diff_horde.cumulant_rms_min_scale`
- `trainer.losses.diff_horde.cumulant_rms_clip`

### Examples (CLI overrides)

```bash
# kind=info_scalar
./devops/run.sh recipes.experiment.cogsguard.train \
  run=your_run_name \
  'diff_horde_cumulants={"territory_now":{"kind":"info_scalar","key":"env_collective/cogs/aligned.junction"}}'
```

```bash
# kind=info_scalar (agent key)
./devops/run.sh recipes.experiment.cogsguard.train \
  run=your_run_name \
  'diff_horde_cumulants={"reward_step":{"kind":"info_scalar","key":"agent/reward_step"}}'
```

```bash
# kind=env_obs_feature
./devops/run.sh recipes.experiment.cogsguard.train \
  run=your_run_name \
  'diff_horde_cumulants={"hp":{"kind":"env_obs_feature","feature":"inv:hp","reduce":"mean","normalize":true}}'
```

```bash
# kind=td_key (whole flattened vector; no explicit size needed)
./devops/run.sh recipes.experiment.cogsguard.train \
  run=your_run_name \
  'diff_horde_cumulants={"hidden_all":{"kind":"td_key","key":"actor_hidden"}}'
```

```bash
# kind=td_key
./devops/run.sh recipes.experiment.cogsguard.train \
  run=your_run_name \
  'diff_horde_cumulants={"core2":{"kind":"td_key","key":"core","slice":"0:2"}}'
```

```bash
# preset groups (stackable)
./devops/run.sh recipes.experiment.cogsguard.train \
  run=your_run_name \
  'horde_variants=["junctions","vitals","roles","cortex_core"]'
```

```bash
# all preset variants
./devops/run.sh recipes.experiment.cogsguard.train \
  run=your_run_name \
  'horde_variants=["all"]'
```

## Useful recipes and games

### CogsGuard

**Train:**

```bash
./devops/run.sh recipes.experiment.cogsguard.train run=your_run_name
```

**Defaults (leaderboard baseline)**

- `layout=machina_1`
- `num_agents=8`
- `max_steps=10000`
- `variants` omitted (no mission or reward variants)
- `include_eval_missions=false`
- `include_fixed_maps=false`
- `max_steps_buckets=[max_steps]` (single bucket)
- `event_profiles` uses baseline clips/weather only

**Curriculum options (opt-in)**

- Add eval missions: `include_eval_missions=true`
- Add fixed maps: `include_fixed_maps=true`
- Multiple step buckets: `max_steps_buckets='[1000,2000,5000,10000]'`
- Event profile bundle (Python): `cogames.cogs_vs_clips.cogsguard_curriculum.COGSGUARD_EVENT_PROFILES`

**Reward variants**

The CogsGuard recipe (`recipes/experiment/cogsguard.py`) supports stackable reward “variants”:

- **objective**: no-op marker; keeps the mission’s default objective reward wiring.
- **no_objective**: disables the objective stat reward (`aligned.junction.held`).
- **milestones**: shaping for aligning/scrambling junctions and holding more junctions.
- **credit**: dense early-learning shaping for precursor behaviors (resources/gear/deposits).

Example:

```bash
./devops/run.sh recipes.experiment.cogsguard.train \
  run=your_run_name \
  variants='["milestones","credit"]'
```

To train on the arena layout instead of Machina 1:

```bash
./devops/run.sh recipes.experiment.cogsguard.train \
  run=your_run_name \
  layout=arena
```

### CogsGuard MARLBRO

`recipes.experiment.cogsguard_marlbro.train` is the two-slice MARLBRO variant of CogsGuard. It trains miner and aligner
roles in separate trajectory-isolation slices with role-conditioned rewards.

**Train:**

```bash
./devops/run.sh recipes.experiment.cogsguard_marlbro.train run=your_run_name
```

**Default behavior (no routers, no teacher):**

- Uses separate policies: `miner_policy` and `aligner_policy`
- Uses two fixed slices:
  - `miner_slice`: agents `0:4`
  - `aligner_slice`: agents `4:8`
- Uses standard per-slice PPO losses (`ppo_actor_*`, `ppo_critic_*`)
- No teacher/supervisor losses are attached by default

#### Enable routed adapters

When `routed_adapter` is enabled for MARLBRO, default slices switch to a single shared policy (`shared_policy`) with
per-slice route slots.

```bash
./devops/run.sh recipes.experiment.cogsguard_marlbro.train \
  run=your_run_name \
  routed_adapter.enabled=true
```

Useful knobs:

- `routed_adapter.rank`
- `routed_adapter.trunk_lr_mult`
- `routed_adapter.num_slots` (defaults to `num_agents` if not set)
- `routed_adapter.alpha`
- `routed_adapter.dropout`
- `routed_adapter.freeze_base`

#### Enable teacher from CLI

MARLBRO now accepts top-level `teacher.*` overrides (same style as CogsGuard). Scripted mixed supervisor is supported:

```bash
./devops/run.sh recipes.experiment.cogsguard_marlbro.train \
  run=your_run_name \
  teacher.policy_uri=metta://policy/nlanky \
  teacher.mode=scripted.supervisor.mixed
```

You can combine teacher + routed adapters:

```bash
./devops/run.sh recipes.experiment.cogsguard_marlbro.train \
  run=your_run_name \
  routed_adapter.enabled=true \
  teacher.policy_uri=metta://policy/nlanky \
  teacher.mode=scripted.supervisor.mixed
```

#### Caveats

- Top-level `teacher` and slice-level `slice_configs[*].teacher` cannot be used together.
- Per-slice scripted teachers with different scripted URIs are not supported (scripted supervisor URI is global).
- If `policy_architecture` already sets `cortex_routed_adapter`, do not also pass top-level `routed_adapter`.
- Custom `route_slot_ids` require routed adapters and must be within `[0, routed_adapter.num_slots)`.
