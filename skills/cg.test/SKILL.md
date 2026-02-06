---
name: cg.test
description: Test cogames play across renderers - headless, vibescope, and MettaScope for 100 steps each
---

# CoGames Test

Run cogames play with planky across all three renderers to validate everything works.

## Steps

Run each sequentially. All use `--autostart` and 100 steps.

### Step 1: Headless

```bash
uv run cogames play --mission cogsguard_machina_1.basic --policy "metta://policy/planky" --render=none --steps=100 --autostart
```

### Step 2: Vibescope

```bash
uv run cogames play --mission cogsguard_machina_1.basic --policy "metta://policy/planky" --render=vibescope --steps=100 --autostart
```

### Step 3: MettaScope

```bash
uv run cogames play --mission cogsguard_machina_1.basic --policy "metta://policy/planky" --render=gui --steps=100 --autostart
```

## Customization

Override defaults via arguments:

- `--mission <name>` - Different mission
- `--policy <uri>` - Different policy URI
- `--steps <n>` - More/fewer steps per renderer (default: 100)
