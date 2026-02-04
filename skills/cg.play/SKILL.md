---
name: cg.play
description: Quick cogames play test - runs headless for a few steps, then vibescope render with timeout
---

# CoGames Play

Quick test workflow for cogames play with a policy.

## Workflow

1. Run headless for a few steps to verify the policy loads and runs
2. Run with vibescope render for visual inspection (short timeout)

## Commands

### Step 1: Headless validation

```bash
uv run cogames play --mission cogsguard_machina_1.basic --policy "metta://policy/planky" --render=none --steps=100
```

This validates the policy loads and runs without rendering overhead.

### Step 2: Visual inspection

```bash
uv run cogames play --mission cogsguard_machina_1.basic --policy "metta://policy/planky" --render=vibescope --steps=100
```

Runs with vibescope rendering for 100 steps. Press the play button in vibescope to start.

## Customization

Override defaults via arguments:

- `--mission <name>` - Different mission
- `--policy <uri>` - Different policy URI
- `--steps <n>` - More/fewer steps (default: 100)
