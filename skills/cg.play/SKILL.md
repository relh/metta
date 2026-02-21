---
name: cg.play
description: Run cogames play with nlanky policy and vibescope rendering
---

# CoGames Play

Run a game with the nlanky policy and vibescope rendering. Starts automatically.

## Command

```bash
uv run cogames play --mission cogsguard_machina_1.basic --policy "metta://policy/nlanky" --render=vibescope --autostart
```

## Customization

Override defaults via arguments:

- `--mission <name>` - Different mission
- `--policy <uri>` - Different policy URI
- `--steps <n>` - Number of steps (default: 1000)
- `--render <mode>` - gui (MettaScope), vibescope, unicode, log, none
