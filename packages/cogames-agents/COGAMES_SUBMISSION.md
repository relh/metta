# Submitting Policies to CoGames

## Nim agents (nlanky, thinky, role, alignall, race_car, nim_random)

Nim agents need a different setup script that handles nim compilation:

```bash
cd packages/cogames-agents

cogames upload \
  -p <short_name> \
  --include-files src/cogames_agents \
  --setup-script nim_setup_script.py \
  -n <submission-name> \
  --dry-run
```

Example:

```bash
cogames upload -p thinky --include-files src/cogames_agents --setup-script nim_setup_script.py -n my-thinky --dry-run
```

The `nim_setup_script.py` installs Python deps, downloads the nim compiler via nimby, syncs nim dependencies, and
compiles `nim_agents.nim`. The `.nim-version` and `.nimby-version` files live inside
`src/cogames_agents/policy/nim_agents/` so they're bundled automatically.
