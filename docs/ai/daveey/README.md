# Daveey's AI Skills

Personal AI skills for Daveey. Shared skills live in `docs/ai/skills.md`.

## Location

- Personal skills: `skills/user/daveey/`
- Shared skills: `skills/`

## Setup

### For Claude Code + Codex

In this repo, `.claude/skills` and `.codex/skills` point at `skills/` (shared only). To sync personal skills into your
local tools, run:

```bash
./scripts/skills-sync.sh
```

That command only syncs shared skills. If you only want Daveey's personal skills, run:

```bash
./scripts/skills-sync.sh skills/user/daveey
```

To sync shared + all user skills, run:

```bash
./scripts/skills-sync.sh --include-user
```

### For Cursor

If you want Cursor to surface these skills, add a rule file under `.cursor/rules/` that points at `skills/user/daveey/`
(see `docs/ai/skills.md` for the shared catalog).

## Available Skills

### Graphite (gt) Skills

These skills help manage Graphite PR stacks:

| Skill             | Description                                                                 |
| ----------------- | --------------------------------------------------------------------------- |
| `gt:fix-branch`   | Sync, restack, address PR comments, and fix CI on current branch            |
| `gt:fix-stack`    | Fix an entire Graphite stack from bottom to top                             |
| `gt:fix-ci`       | Find and fix CI failures on a branch                                        |
| `gt:fix-comments` | Address PR review comments with regression tests                            |
| `gt:submit`       | Run tests, cleanup, and submit to Graphite                                  |
| `gt:cool`         | Clean up backwards compatibility cruft                                      |
| `gt:make-stack`   | Break a large branch into a reviewable stack                                |
| `gt:extract`      | Extract a feature into a separate parallel branch                           |
| `gt:extract-copy` | Copy a feature to a new branch without modifying original                   |
| `gt:split`        | Split a branch into multiple sequential branches in the same stack position |
| `gt:apply`        | Route uncommitted changes to the correct branches in a Graphite stack       |

### Repo Scaffolding

| Skill            | Description                                                            |
| ---------------- | ---------------------------------------------------------------------- |
| `r:make-package` | Create a new Python package in packages/ with uv workspace integration |

### Meta Skills

| Skill            | Description                                                                     |
| ---------------- | ------------------------------------------------------------------------------- |
| `cf:really`      | Run a skill repeatedly until it succeeds (e.g., `cf:really gt:fix-ci`)          |
| `m:make-skill`   | Create a new skill with proper directory, symlink, and README updates           |
| `m:update-skill` | Update an existing skill and submit via m:submit-skill                          |
| `m:submit-skill` | Commit and submit skill changes (worktree, lint, submit, publish, merge)        |
| `m:sync-skills`  | Sync skills to Claude Code and Codex (symlinks from a skills directory)         |
| `m:learn-skills` | Import skills from a path (symlink if in-repo, copy via m:make-skill otherwise) |

### Testing

| Skill         | Description                                                 |
| ------------- | ----------------------------------------------------------- |
| `t:run-tests` | Run tests progressively: failed tests -> pytest -> metta ci |

## Usage

### In Claude Code

Invoke skills using slash commands:

```
/gt:fix-branch
/gt:fix-stack
/gt:submit
```

### In Cursor

Reference the skills in your prompts:

```
Use the gt:fix-branch skill to fix the current branch
```

## Editing Skills

Edit the skills directly in `skills/user/daveey/`.
