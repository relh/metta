---
name: relh.tr.run-recipe
description:
  'Run ./tools/run.py recipes (train/play/evaluate) and summarize outcomes or failures. Use when asked to run a recipe.'
---

# Run Recipe

## Workflow

- Confirm the recipe target, mode, and args.
- Run `uv run ./tools/run.py <recipe>.<mode> <args...>` with a reasonable timeout.
- Capture output, summarize results, and point to relevant logs or files on failure.
- Suggest next-step commands when useful.
