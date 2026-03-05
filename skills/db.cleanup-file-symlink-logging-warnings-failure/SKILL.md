---
name: db.cleanup-file-symlink-logging-warnings-failure
description: 'Use when cleaning up file symlink logging warnings failure.'
---

# Cleanup File Symlink Logging Warnings Failure

## Trigger

- Primary: "cleaning up file symlink logging warnings failure"

## Workflow

- Identify noisy file/symlink logging paths that obscure real failures in debug output.
- Remove redundant warning paths and consolidate logging around actionable error states.
- Verify behavior with focused failing scenarios so warnings are reduced without hiding breakage.
- Document the cleanup and the expected signal-to-noise improvement.
