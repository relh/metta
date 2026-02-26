# Submitting Metta-Trained Policies to CoGames

Trained checkpoints use `CheckpointPolicy` from the `agent/` package, which isn't installed in the isolated venv by
default. Use `--include-files agent` to bundle the package and `trained_setup_script.py` to install it along with its
third-party dependencies.

```bash
# From the repo root:
uv run cogames upload \
  -p ./train_dir/<run>/checkpoints/<run>:<version> \
  --include-files agent \
  --include-files packages/cortex \
  --setup-script packages/cogames-agents/trained_setup_script.py \
  -n <submission-name> \
  --dry-run
```

Example:

```bash
uv run cogames upload \
  -p ./train_dir/my_run/checkpoints/my_run:v30 \
  --include-files agent \
  --include-files packages/cortex \
  --setup-script packages/cogames-agents/trained_setup_script.py \
  -n my-trained-policy \
  --dry-run
```

The `trained_setup_script.py` installs `packages/cortex` (the `cortexcore` library) and the `agent/` package (which
brings `pufferlib-core` and `einops`) along with additional dependencies (`torchrl`, `safetensors`, `optree`). `torch`
and `pufferlib-core` are already present in the isolated venv from mettagrid.
