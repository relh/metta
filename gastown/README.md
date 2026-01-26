# Gas Town Integration for Metta

This directory contains scripts for integrating the metta repository with Gas Town, Anthropic's multi-agent workspace
manager.

## Asana Sync

Syncs tasks from Asana into beads for Gas Town native workflow.

### Setup

1. Get an Asana personal access token from https://app.asana.com/0/developer-console
2. Export it: `export ASANA_TOKEN=your_token_here`

### Usage

From the metta rig directory (`~/gt/metta`):

```bash
# Preview what would be imported
./scripts/sync-asana.sh --dry-run

# Sync your assigned tasks (default)
./scripts/sync-asana.sh

# Sync all configured project tasks
./scripts/sync-asana.sh --scope all

# View imported tasks
bd list --label asana
bd ready --label asana
```

### Scripts

| Script                  | Purpose                           |
| ----------------------- | --------------------------------- |
| `asana_sync.py`         | Main sync: Asana → beads JSONL    |
| `asana_util.py`         | Shared Asana API utilities        |
| `asana_config.yaml`     | Config: workspace, projects, user |
| `sync-asana.sh`         | Convenience wrapper               |
| `asana_task_details.py` | Fetch single task details         |
| `asana_task_comment.py` | Post comments to Asana tasks      |
| `asana_pr_sync.py`      | Sync PR links back to Asana       |
| `task_plan_stub.py`     | Generate implementation plan stub |

### Configuration

Edit `scripts/asana_config.yaml` to configure:

- Workspace GID
- Projects to sync
- User email (if using service account token)

## Workflow

1. **Sync Asana** → `./scripts/sync-asana.sh`
2. **View tasks** → `bd list --label asana`
3. **Pick work** → `bd show mt-asana-<gid>`
4. **Start work** → `gt sling mt-asana-<gid> polecat`
5. **Polecat works** → Creates branch, implements, submits PR
6. **Review** → Human reviews PR
7. **Merge** → Refinery processes merge queue

## Bead IDs

Imported tasks get IDs like `mt-asana-1234567890123`:

- `mt` = rig prefix
- `asana` = source identifier
- number = Asana task GID

This ensures no collision with manual beads and enables re-sync updates.
