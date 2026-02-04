---
name: cb.lint-fix
description: Run lint autofix, address remaining lint errors, and summarize changes. Use when asked to fix lint issues.
---

# Lint Fix

## Overview

Fix lint and formatting errors in the codebase. Ensures all required formatters (including prettier) are available
before running.

**Announce at start:** "Running lint fix."

## The Process

### Step 1: Ensure Prettier is Available

`metta lint` requires prettier for markdown, JavaScript, JSON, YAML, and other non-Python files. **Always verify
prettier is available before running lint:**

```bash
# Check if prettier is available
if ! command -v prettier &> /dev/null && ! npx prettier --version &> /dev/null 2>&1; then
  echo "Installing prettier..."
  npm install -g prettier
fi

# Verify it works
npx prettier --version
```

**If npm/npx is not available:** Report to user that prettier cannot be installed and lint will fail for non-Python
files.

### Step 2: Run Lint Autofix

```bash
metta lint --fix
```

This runs all configured linters with autofix enabled:

- **Python:** ruff (format + lint)
- **Markdown/JS/JSON/YAML/etc:** prettier
- **Shell:** shfmt

### Step 3: Fix Remaining Errors

If lint still fails after autofix:

1. Read the error output carefully
2. Fix each error manually
3. Limit changes to the files with errors (don't refactor surrounding code)

### Step 4: Verify

```bash
metta lint
```

Re-run lint without `--fix` to confirm all errors are resolved.

## Common Issues

| Issue                      | Solution                                       |
| -------------------------- | ---------------------------------------------- |
| "prettier: not found"      | Run `npm install -g prettier` or use `npx`     |
| Markdown formatting errors | Run `npx prettier --write <file.md>`           |
| Line too long (Python)     | Break into multiple lines or use a variable    |
| Import order               | Usually autofix handles this; re-run if needed |
| Trailing whitespace        | Autofix handles this; check editor settings    |
| Missing newline at EOF     | Autofix handles this; check editor settings    |

## Integration

**Called by:**

- **pr.submit** - Before submitting PRs
- **pr.fix-ci** - When lint CI fails
- **pr.fix-branch** - During branch fixing
- **st.make-stack** - Before creating stack branches
- **sk.submit-skill** - Before submitting skill changes

**Note:** Other skills should invoke `/cb.lint-fix` rather than running `metta lint` directly to ensure prettier and
other formatters are properly available.
