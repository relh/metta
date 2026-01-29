# Devcontainer Development

## Graphite Workflow

Use graphite ("gt") for all git operations. Name branches `$user/short-issue-name` (5 words or less).

### Common Commands

```bash
gt checkout <branch>      # Switch branches
gt create <branch>        # Create new branch from current
gt submit                 # Push and create/update PR
gt sync                   # Pull latest main, restack all branches
gt restack                # Rebase current stack on updated parents
gt move --onto main       # Move branch to stack on main (use when parent was merged)
```

### Before Submitting a PR

**ALWAYS run the full lint before pushing:**

```bash
metta lint
```

This checks Python (ruff), JSON, Markdown, and other file types. Fix any issues before running `gt submit`.

### After Rebases and Conflict Resolution

1. Resolve conflict markers in files
2. **Verify the entire file** - rebases can carry over unwanted changes beyond conflict markers
3. Run `metta lint` to catch formatting issues before continuing
4. `gt add -A && gt continue`

### Stale Branches

When a parent branch is merged, child branches become stale. Fix with:

```bash
gt move --onto main       # Rebase onto main
# Resolve any conflicts, then:
gt add -A && gt continue
gt submit
```

## Formatting

After any rebase or conflict resolution involving devcontainer files:

1. Run `pnpm exec prettier --write .devcontainer/` to fix formatting
2. Verify no trailing commas in JSON files (invalid JSON syntax)

## Testing Changes

Rebuild the devcontainer to test changes:

```bash
devcontainer up --workspace-folder . --remove-existing-container --build-no-cache
```

## initializeCommand

The `initializeCommand` runs on the host before the container starts. It must be a single string command (not an array
of separate commands) because the devcontainer CLI treats array elements as arguments to the first element, not as
separate commands.
