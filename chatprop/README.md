# Chatprop

> Status: In development

Chatprop is a local-first transcript backprop system for coding-agent sessions. It maps session work to branches, splits
delivery vs revision work, infers a skill graph (explicit and implicit skills), and turns revision evidence into
guidance improvements.

## Standalone Local Usage

`chatprop` runs directly from this repo and does not require site services.

### Prerequisites

- Python `>=3.11`
- `uv`
- Optional CLIs for analysis/proposal flows:
  - `claude` (`chatprop analyze`, `chatprop propose`)
  - `gh` (`chatprop analyze`, `chatprop propose`)
  - `gt` (`chatprop propose`)

### 1) Install and initialize config

```bash
cd chatprop
uv sync
uv run chatprop init
```

This writes `~/.chatprop/config.toml` with defaults:

- Claude sessions: `~/.claude/projects`
- Codex sessions: `~/.codex/sessions`
- Chatprop state: `~/.chatprop`

Override defaults as needed:

```bash
uv run chatprop init \
  --force \
  --claude-code-path "/path/to/claude/sessions" \
  --codex-path "/path/to/codex/sessions" \
  --state-dir "/path/to/chatprop-state"
```

### 2) Ingest sessions into local archive

```bash
uv run chatprop daemon --once
uv run chatprop status
```

For continuous ingestion:

```bash
uv run chatprop daemon
```

Install a macOS launchd agent:

```bash
uv run chatprop daemon --install
```

### 3) Run local UI

```bash
uv run chatprop serve --host 127.0.0.1 --port 8765
```

Open `http://127.0.0.1:8765`.

### 4) Export weighted flowchart

```bash
uv run chatprop flowchart \
  --output ./chatprop_flowchart.mmd \
  --json-output ./chatprop_flowchart.json \
  --max-nodes 120 \
  --max-edges 350
```

### 5) Analyze/propose branch learnings

```bash
uv run chatprop analyze relh/my-branch --dry-run
uv run chatprop propose relh/my-branch
```

## CLI Reference

Run `uv run chatprop --help` for full command docs.

- `init`: write local config (`~/.chatprop/config.toml` by default)
- `daemon`: archive local transcript files (`--once` for one pass, `--install` for launchd plist)
- `status`: show archive/index counters
- `serve`: run local UI/API server
- `flowchart`: export weighted workflow graph
- `find BRANCH...`: list transcripts matching branch/PR strings
- `upload SESSION_ID`: force-archive a single session by id
- `analyze BRANCH...`: build branch context and run `claude --print` analysis (`--dry-run` prints prompt context only)
- `propose BRANCH...`: run analysis, apply suggested `CLAUDE.md` changes, and open PR automation

```bash
uv run chatprop find relh/my-branch another-branch
uv run chatprop upload abc123-session-id
uv run chatprop propose relh/my-branch --branch-name relh/my-branch-chatprop-proposal
```
