# Mettabox CLI

Utilities for running and inspecting jobs inside mettabox docker containers.

Assumptions (from recent usage):

- Hosts: `metta0`..`metta4` reachable via SSH.
- Host alias: use `local` when already SSH'd into the target mettabox and you want to run without SSH hop.
- Container name: `metta`.
- Repo path: `/workspace/metta`.
- Logs: `/workspace/metta/train_dir/<run_id>.log`.

## Quick usage

```bash
# List known boxes
./devops/mettabox/cli.py list-boxes

# Launch a run in tmux
./devops/mettabox/cli.py run metta1 -- train arena run=my_run trainer.total_timesteps=100000

# Already on the target mettabox host (SSH'd in): run locally (no SSH hop)
./devops/mettabox/cli.py run local -- train arena run=my_run trainer.total_timesteps=100000

# If the container already has tmux running (for example started via devops/mettabox/docker.sh),
# `run` will create a new tmux window in the existing session and (optionally) attach.
./devops/mettabox/cli.py run metta1 --attach -- train arena run=my_run trainer.total_timesteps=100000

# Attach to tmux later
./devops/mettabox/cli.py tmux metta1 0

# List active run processes
./devops/mettabox/cli.py runs metta1
./devops/mettabox/cli.py runs --all

# Follow logs (with GPU snapshot)
./devops/mettabox/cli.py instrument metta1 my_run --follow

# Show the most recent progress block
./devops/mettabox/cli.py progress metta1 my_run

# Audit one box or all boxes
./devops/mettabox/cli.py audit metta2
./devops/mettabox/cli.py audit --all

# Resource snapshot
./devops/mettabox/cli.py profile metta3
```

## GitHub Token Forwarding

`run` and `exec` forward your local GitHub token into the container command environment by default.

- Source order: `GH_TOKEN`, then `GITHUB_TOKEN`, then `gh auth token`.
- Exported remotely as both `GH_TOKEN` and `GITHUB_TOKEN`.
- Forwarded via a temporary remote `--env-file` to avoid putting token values in command argv.
- Disable per command with `--no-forward-gh-token`.

## AWS Credential Forwarding

`run` and `exec` also forward AWS credentials by default for S3/secrets workflows.

- Source order: local AWS env vars first, then `aws configure export-credentials`.
- Credential keypair source is selected atomically (no mixing access key + secret across sources).
- Exported vars: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`, `AWS_REGION`, `AWS_DEFAULT_REGION`.
- If credential forwarding is enabled but no local keypair can be resolved, the CLI prints a warning with the reason
  (for example an invalid `AWS_PROFILE`) so failures are visible before container-side auth falls back.
- Disable per command with `--no-forward-aws-creds`.

## Log discovery

`instrument` and `progress` try these paths in order:

- `/workspace/metta/train_dir/<run_id>.log`
- `/workspace/metta/train_dir/<run_id>/logs/script.log`
- `/workspace/metta/train_dir/<run_id>/logs/monitor.log`

## SkyPilot sandboxes

```bash
./devops/mettabox/cli.py sky-status
```

For launching sandboxes or jobs, see `devops/skypilot/README.md`.
