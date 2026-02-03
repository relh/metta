---
name: n.setup-worktree-ide-themes
description:
  Use when setting up new git worktrees and you want color-coded Cursor status bars to visually distinguish windows. Use
  when worktrees are created or when metta.code-workspace changes upstream.
---

# Setup Worktree IDE Themes

## Overview

Create `metta.local.code-workspace` files (gitignored via `*.local.code-workspace`) for each worktree with unique status
bar colors. Cursor ignores `workbench.colorCustomizations` in `.vscode/settings.json` but respects it in
`.code-workspace` files.

**Announce at start:** "Setting up worktree IDE color themes."

## The Process

1. Discover all worktrees for the repo
2. Present the list to the user and ask which ones to set up (use AskUserQuestion with multiSelect)
3. For each selected worktree, create `metta.local.code-workspace` with a unique status bar color

## Step 1: Discover Worktrees

```bash
git worktree list --porcelain | grep "^worktree " | sed 's/^worktree //'
```

Also note which ones already have a `metta.local.code-workspace` file.

## Step 2: Ask User

Use AskUserQuestion with multiSelect to present the discovered worktrees. Mark which already have local workspace files
so the user knows which would be regenerated. Pre-recommend any that are missing local workspace files.

## Step 3: Create Local Workspace Files

For each selected worktree, copy the base workspace file and inject a color block into the `settings` object.

### Color Palette

Assign colors in order of selection:

| Index | Label  | statusBar.background | statusBar.foreground |
| ----- | ------ | -------------------- | -------------------- |
| 0     | Blue   | `#1a3a5c`            | `#ccddee`            |
| 1     | Green  | `#1a4a2e`            | `#cceecc`            |
| 2     | Purple | `#3a1a5c`            | `#ddccee`            |
| 3     | Amber  | `#5c3a1a`            | `#eeddcc`            |
| 4     | Teal   | `#1a4a4a`            | `#cceedd`            |
| 5     | Red    | `#5c1a1a`            | `#eecccc`            |

### Injection

Find a stable key in the settings block (e.g. `"vim.textwidth"`) and insert the color block before it:

```jsonc
    "workbench.colorCustomizations": {
      "statusBar.background": "<bg>",
      "statusBar.foreground": "<fg>"
    },
```

Example using sed:

```bash
BASE_WORKSPACE="$WORKTREE/metta.code-workspace"
LOCAL_WORKSPACE="$WORKTREE/metta.local.code-workspace"
cp "$BASE_WORKSPACE" "$LOCAL_WORKSPACE"
sed -i '' "s|\"vim.textwidth\"|\"workbench.colorCustomizations\": {\n      \"statusBar.background\": \"$BG\",\n      \"statusBar.foreground\": \"$FG\"\n    },\n    \"vim.textwidth\"|" "$LOCAL_WORKSPACE"
```

## Step 4: Verify

```bash
grep -l "colorCustomizations" ~/repos/m*/metta.local.code-workspace
```

Remind the user to open `metta.local.code-workspace` instead of `metta.code-workspace` in Cursor.

## Notes

- `*.local.code-workspace` is already in `.gitignore`
- Colors apply instantly in Cursor without reload
- If `metta.code-workspace` changes upstream, re-run this skill to regenerate the local copies

## Integration

**Pairs with:**

- **wt.cleanup** - When removing worktrees, the local workspace file is deleted with the worktree
