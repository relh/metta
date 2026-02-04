# Running training jobs

This page covers how to run training jobs locally and on SkyPilot sandboxes.

For general `tools/run.py` usage (recipes, discovery, override syntax), see `docs/tools.md`.

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
- Any arguments after the module path are passed through to `tools/run.py` (Hydra overrides).

### Launch a job with SkyPilot (no interactive SSH)

If you want to submit a job from your local machine using SkyPilot:

```bash
./devops/skypilot/launch.py recipes.experiment.cogsguard.train --gpus 8 --max-runtime-hours 120 -- run=your_run_name
```

Notes:

- By default, `launch.py` checks that your working tree is clean and the current commit is pushed (so the cloud job
  matches your code).
- You can use `--git-ref <branch-or-commit>` to launch a specific ref, or `--skip-git-check` to bypass validation.
- Use `--` to separate launch flags (e.g. `--gpus`, `--nodes`, `--max-runtime-hours`) from tool args (Hydra overrides).

## Kickstarting with a teacher

Kickstarting can be used with any recipe that accepts `teacher` / `use_default_teacher` (e.g. CogsGuard, Machina, etc.).

If a recipe exposes `use_default_teacher=true`, that enables a recipe-chosen default teacher.

### Examples

**CogsGuard default teacher (Machina 1 layout by default):**

```bash
./devops/skypilot/launch.py recipes.experiment.cogsguard.train --gpus 8 --max-runtime-hours 120 -- \
  run=your_run_name \
  use_default_teacher=true
```

To switch layouts, pass `layout=arena` (or `layout=machina_1` explicitly).

### Custom teacher overrides

You can also specify a custom teacher by providing a `teacher.policy_uri` and choosing a mode. Two modes that work well
currently are `sliced_cloner` and `supervisor`.

**Dict-style (single quoted override):**

```bash
./devops/skypilot/launch.py recipes.experiment.cogsguard.train --gpus 8 --max-runtime-hours 120 -- \
  'teacher={mode: sliced_cloner, policy_uri: "metta://policy/cogsguard?gear=10", teacher_led_proportion: 0.5, student_led_proportion: 0.5, steps: 1_000_000_000, anneal_start_step: 0, ppo_begin_step: 0}' \
  run=your_run_name
```

**Dot-style overrides:**

```bash
./devops/skypilot/launch.py recipes.experiment.cogsguard.train --gpus 8 --max-runtime-hours 120 -- \
  run=your_run_name \
  teacher.policy_uri='metta://policy/cogsguard?gear=10' \
  teacher.mode=sliced_cloner \
  teacher.teacher_led_proportion=0.5 \
  teacher.student_led_proportion=0.5
```

See `metta/rl/training/teacher.py` for available teacher modes and knobs (e.g. `teacher.kwargs.*` for per-mode config).

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
