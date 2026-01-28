---
name: m:update-skill
description: Use when making changes to an existing skill - applies updates and submits via m:submit-skill
args: <skill-name> "<description of changes>"
---

# Update Skill

## Overview

Apply user-requested changes to an existing skill and submit via `/m:submit-skill`.

**Announce at start:** "Updating skill `<skill-name>` and submitting."

## The Process

1. Locate and read the existing skill
2. Apply requested changes
3. Submit via `/m:submit-skill`

## Step 1: Locate Skill

```bash
SKILL_NAME="<skill-name>"
REPO_ROOT=$(git rev-parse --show-toplevel)
SKILL_PATH="$REPO_ROOT/skills/$SKILL_NAME/SKILL.md"

if [ ! -f "$SKILL_PATH" ]; then
  SKILL_PATH=$(find "$REPO_ROOT/skills/user" -maxdepth 3 -path "*/$SKILL_NAME/SKILL.md" -print -quit)
fi
```

Read the current SKILL.md to understand context.

## Step 2: Apply Changes

Make the requested modifications to the SKILL.md (and any supporting files).

**Guidelines:**

- Preserve existing structure unless explicitly asked to restructure
- Update the Integration section if dependencies changed
- Keep the skill under 500 words

## Step 3: Submit

Invoke `/m:submit-skill` to handle worktree, lint, commit, submit, publish, and merge-when-ready.

## Integration

**Uses:**

- **m:submit-skill** - Handles the submission workflow

**Pairs with:**

- **m:make-skill** - For creating new skills from scratch
