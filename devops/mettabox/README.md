# Mettabox CLI

Utilities for running and inspecting jobs inside mettabox docker containers.

Assumptions (from recent usage):

- Hosts: `metta0`..`metta4` reachable via SSH.
- Container name: `metta`.
- Repo path: `/workspace/metta`.
- Logs: `/workspace/metta/train_dir/<run_id>.log`.

## Quick usage

```bash
# List known boxes
./devops/mettabox/cli.py list-boxes

# Launch a run in tmux
./devops/mettabox/cli.py run metta1 -- train arena run=my_run trainer.total_timesteps=100000

# Attach to a tmux session
./devops/mettabox/cli.py tmux metta1 my_run

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
