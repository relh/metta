---
name: quick-train-test
description:
  Run a quick local training test for 3 epochs to verify a recipe works. Use when asked to test training, verify a
  recipe, or run a quick training check.
disable-model-invocation: false
---

# Quick Train Test

Run a local training test for approximately 3 epochs to verify a recipe works without committing to a full training run.

## When to Use

- User asks to test training or verify a recipe works
- User mentions "quick test", "test run", "see if it works", or "3 epochs"
- User wants to validate a recipe before a longer training run

## Instructions

When invoked:

1. **Parse the recipe name** from user input:
   - If user says "use the recipe X" or "recipe X", extract X
   - Accept recipe names like `arena_basic_easy_shaped.py`, `arena_basic_easy_shaped`, or short names like `arena`
   - Remove `.py` extension if present

2. **Find the recipe file**:
   - Search for the recipe in `recipes/prod/` first, then `recipes/experiment/`
   - Use glob patterns to find files matching the name
   - If found, convert to module path format:
     - `recipes/prod/arena_basic_easy_shaped.py` → `recipes.prod.arena_basic_easy_shaped`
     - `recipes/experiment/arena.py` → `recipes.experiment.arena`
   - If not found by exact filename, try resolving via recipe registry using short names

3. **Construct the training command**:
   - Base command: `./tools/run.py <module_path>.train`
   - Add overrides for quick test:
     - `trainer.total_timesteps=500000` (approximately 3 epochs with default batch_size)
   - Add a run name: `run=quick_test_<timestamp>` or let it auto-generate

4. **Execute the command**:
   - Run the command using the terminal
   - Monitor for errors or early completion
   - Report success/failure and any relevant output

## Examples

User: "use the recipe arena_basic_easy_shaped.py" → Find `recipes/prod/arena_basic_easy_shaped.py` → Run:
`./tools/run.py recipes.prod.arena_basic_easy_shaped.train trainer.total_timesteps=500000 checkpointer.epoch_interval=1 evaluator.epoch_interval=1`

User: "test training with arena recipe" → Find recipe (try `arena` → resolves to `recipes.prod.arena_basic_easy_shaped`
or similar) → Run:
`./tools/run.py arena.train trainer.total_timesteps=500000 checkpointer.epoch_interval=1 evaluator.epoch_interval=1`

User: "/quick-train-test recipes/prod/arena_basic_easy_shaped.py" → Extract recipe name, find file, construct and run
command

## Notes

- The `total_timesteps=500000` value is chosen to approximate 3 epochs with typical batch sizes (~2M), but will complete
  quickly
- If the recipe has a very small batch_size, adjust timesteps accordingly
- The command uses the existing `./tools/run.py` infrastructure which handles all the complexity
- Recipe discovery uses the same logic as the tool system (short names resolve automatically)
