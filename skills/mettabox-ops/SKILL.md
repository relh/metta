---
name: mettabox-ops
description:
  Run, launch, instrument, audit, or profile jobs inside mettabox docker containers (metta0..metta4) and check SkyPilot
  sandboxes using devops/mettabox/cli.py; use when asked to operate on mettaboxes or their containerized runs.
---

# Mettabox Ops

## Defaults

- Use `./devops/mettabox/cli.py` for remote actions.
- Assume hosts `metta0`..`metta4`, container `metta`, repo `/workspace/metta`, logs
  `/workspace/metta/train_dir/<run_id>.log`.

## Workflows

### Launch a job

```bash
./devops/mettabox/cli.py run metta1 -- train arena run=my_run trainer.total_timesteps=100000
```

Use `--attach` to jump into the tmux session or `--session` to override the session name.

### List active runs

```bash
./devops/mettabox/cli.py runs metta1
./devops/mettabox/cli.py runs --all
```

### Stream logs and GPU snapshot

```bash
./devops/mettabox/cli.py instrument metta1 my_run --follow
```

Add `--no-gpu` for logs-only.

### Show the latest progress block

```bash
./devops/mettabox/cli.py progress metta1 my_run
```

### Audit host status

```bash
./devops/mettabox/cli.py audit metta2
./devops/mettabox/cli.py audit --all
```

### Reset repo to origin/main (stateless boxes)

```bash
./devops/mettabox/cli.py exec metta2 -- git -C /workspace/metta fetch origin
./devops/mettabox/cli.py exec metta2 -- git -C /workspace/metta checkout -f main
./devops/mettabox/cli.py exec metta2 -- git -C /workspace/metta reset --hard origin/main
./devops/mettabox/cli.py exec metta2 -- git -C /workspace/metta clean -fd
```

This discards local changes and untracked files.

### Profile resources

```bash
./devops/mettabox/cli.py profile metta3
```

### Run a one-off command

```bash
./devops/mettabox/cli.py exec metta4 -- ls -la /workspace/metta
```

Use `--tty` for interactive commands and `--no-cd` if the command should not run under `/workspace/metta`.

### Attach or list tmux sessions

```bash
./devops/mettabox/cli.py tmux metta1
./devops/mettabox/cli.py tmux metta1 my_run
```

### Check SkyPilot sandboxes

```bash
./devops/mettabox/cli.py sky-status
```

## Guardrails

- Prefer the CLI over ad-hoc `ssh` + `docker exec` unless the CLI is blocked.
- Always pass `--` before tool args to avoid argument parsing issues.
- If the container name differs, pass `--container <name>`.
- `instrument` and `progress` auto-detect logs in `train_dir/<run_id>.log` or `train_dir/<run_id>/logs/script.log`.

## Reference

- If defaults are unclear, read `devops/mettabox/README.md`.
