---
name: cg.play
description: Run cogames play with planky policy and vibescope rendering
---

# CoGames Play

Run a game with the planky policy and vibescope rendering. Starts automatically.

## Command

```bash
uv run cogames play --mission cogsguard_machina_1.basic --policy "metta://policy/planky" --render=vibescope --autostart
```

## Customization

Override defaults via arguments:

- `--mission <name>` - Different mission
- `--policy <uri>` - Different policy URI
- `--steps <n>` - Number of steps (default: 1000)
- `--render <mode>` - gui (MettaScope), vibescope, unicode, log, none
