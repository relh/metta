---
name: do.mettabox-ops
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

If tmux already has sessions in the container, `run` will create a new tmux window in the existing session (so runs show
up in the tmux UI you already have open). If no tmux sessions exist yet, it falls back to creating a new tmux session.

Use `--attach` to jump into tmux after launch and `--session` to override the session/window name.

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
./devops/mettabox/cli.py tmux metta1 0
```

### NVML / NVIDIA driver failure (inside tmux)

If you see `cannot initialize NVML` inside the tmux session, the container's NVIDIA driver is broken. Fix by restarting
the container on the host, then re-launch the run:

```bash
ssh metta@metta1 docker ps
ssh metta@metta1 docker kill metta
ssh metta@metta1 docker start metta
./devops/mettabox/cli.py run metta1 -- <tool args>
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
- If tmux shows `cannot initialize NVML`, restart the container on the host (`docker kill metta` + `docker start metta`)
  and retry the run.

## Reference

- If defaults are unclear, read `devops/mettabox/README.md`.
