# Daveey's AI Skills

Personal AI skills and commands for use with Claude Code and Cursor.

## Setup

### For Claude Code

Run the setup script to symlink skills to `~/.claude/skills/`:

```bash
./docs/ai/daveey/setup.sh
```

This creates symlinks from `~/.claude/skills/` to `docs/ai/daveey/skills/`, allowing Claude Code to discover them
automatically.

### For Cursor

The skills are automatically available via `.cursor/rules/daveey_skills.mdc`.

## Available Skills

### Graphite (gt) Skills

These skills help manage Graphite PR stacks:

| Skill             | Description                                                      |
| ----------------- | ---------------------------------------------------------------- |
| `gt:fix-branch`   | Sync, restack, address PR comments, and fix CI on current branch |
| `gt:fix-stack`    | Fix an entire Graphite stack from bottom to top                  |
| `gt:fix-ci`       | Find and fix CI failures on a branch                             |
| `gt:fix-comments` | Address PR review comments with regression tests                 |
| `gt:submit`       | Run tests, cleanup, and submit to Graphite                       |
| `gt:cool`         | Clean up backwards compatibility cruft                           |
| `gt:make-stack`   | Break a large branch into a reviewable stack                     |
| `gt:extract`      | Extract a feature into a separate parallel branch                |
| `gt:extract-copy` | Copy a feature to a new branch without modifying original        |

### Worktrunk

| Skill       | Description                                                                   |
| ----------- | ----------------------------------------------------------------------------- |
| `worktrunk` | Worktrunk configuration, hooks, LLM commits, and troubleshooting (via plugin) |

### Meta Skills

| Skill            | Description                                                                     |
| ---------------- | ------------------------------------------------------------------------------- |
| `cf:really`      | Run a skill repeatedly until it succeeds (e.g., `cf:really gt:fix-ci`)          |
| `m:make-skill`   | Create a new skill with proper directory, symlink, and README updates           |
| `m:learn-skills` | Import skills from a path (symlink if in-repo, copy via m:make-skill otherwise) |
| `t:run-tests`    | Run tests progressively: failed tests → pytest → metta ci                       |

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

Edit the skills directly in `docs/ai/daveey/skills/`. Changes are automatically picked up by Claude Code (via symlinks)
and Cursor (via the rule file).
