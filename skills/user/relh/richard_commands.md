# Richard Higgins - Workspace-agnostic slash commands

This file consolidates common slash-command patterns observed across multiple workspaces (including Metta and
tribal-village) into a single, reusable set of workspace-agnostic commands.

## Commands

### /review-main

Purpose: review branch changes vs main using merge-base diff and return prioritized findings, including unintended or
simplification opportunities when relevant. Inputs: base_branch=main (default), focus_paths (optional). Steps:

- git fetch origin (if needed)
- base=$(git merge-base HEAD origin/main)
- git diff $base Output: prioritized, actionable findings + risks + unintended change callouts (if any).

### /branch-hygiene

Purpose: audit the branch vs origin/main for unintended changes, redundant code, or missing tests. Inputs:
base_branch=origin/main (default), focus_paths (optional). Steps:

- git fetch origin (if needed)
- base=$(git merge-base HEAD origin/main)
- git diff $base and review for unintended or overly defensive changes Output: cleanup recommendations + risky changes +
  test suggestions.

### /pr-summary

Purpose: generate a PR title + description from branch diff vs main. Inputs: base_branch=main (default), audience=tech
(optional). Steps:

- git fetch origin
- base=$(git merge-base HEAD origin/main)
- summarize git diff --stat and key file diffs Output: title + short body + tests run/recommended.

### /merge-conflicts

Purpose: resolve merge conflicts after merging main and explain non-trivial resolutions. Inputs: conflict list
(optional), priority_files (optional). Steps:

- inspect conflict markers
- keep upstream structure while preserving branch intent Output: resolved files + short rationale.

### /sync-main

Purpose: commit local changes, sync with main, resolve conflicts, and push the branch. Inputs: commit_message
(optional), base_branch=main (default). Steps:

- git status and summarize changes
- git add/commit (if requested)
- git fetch origin and merge/rebase from origin/main
- resolve conflicts and push branch Output: summary of sync steps + any conflicts resolved.

### /lint-fix

Purpose: run lint autofix and address remaining issues. Inputs: lint_cmd="metta lint --fix" (default), allowlist_paths
(optional). Steps:

- run lint autofix
- fix remaining lint errors Output: summary of edits + remaining issues (if any).

### /test-triage

Purpose: diagnose pytest/CI failures and implement minimal fixes. Inputs: failing command output or traceback. Steps:

- identify failing tests and root cause
- patch minimal fix
- rerun targeted tests if asked Output: root cause + fix summary + verify command.

### /run-and-triage

Purpose: run command(s) and report errors/root cause. Inputs: command(s) (required). Steps:

- execute command(s)
- capture and summarize failures Output: error summary + suggested fixes. Notes:
- If the command is a recipe run (./tools/run.py), include a reasonable timeout and summarize outcomes or failures.

### /run-recipe

Purpose: run ./tools/run.py recipes (train/play/evaluate) and summarize outcomes or failures. Inputs: recipe command
(required), timeout (optional). Steps:

- run `uv run ./tools/run.py <recipe>.<mode> <args...>` with a reasonable timeout
- summarize results or failures with file/line pointers when relevant Output: run outcome + errors + next-step commands.

### /cogames-command

Purpose: craft or adjust cogames commands (train/play/eval) for missions/variants/policies. Inputs: goal + partial
command or policy/run id. Steps:

- produce final command for the goal
- explain key flags Output: finalized command + short explanation.

### /checkpoint-find

Purpose: locate a checkpoint for a run id and provide follow-up command. Inputs: run id (required), desired
action=play|eval (optional). Steps:

- find latest checkpoint for run
- craft next command using checkpoint Output: checkpoint path + follow-up command.

### /policy-save-load-audit

Purpose: audit policy save/load and checkpoint handling across metta/cogames. Inputs: affected files or error logs.
Steps:

- trace save/load call graph
- flag compatibility risks or legacy shims Output: compatibility report + cleanup plan.

### /sync-nim-python

Purpose: compare Nim vs Python scripted agent implementations and align behavior. Inputs: target agent(s) or files.
Steps:

- enumerate behavioral differences
- port missing logic Output: aligned implementations + test/docs updates.

### /cleanup-refactor

Purpose: simplify code and remove legacy/backcompat shims while preserving behavior. Inputs: target paths/snippets.
Steps:

- inline/remove redundant code and comments
- keep diff minimal Output: concise changes + rationale.

### /simplify-diff

Purpose: make an existing change more concise without altering behavior. Inputs: file path or snippet (required). Steps:

- inline helpers or remove redundant logic
- avoid unrelated edits Output: minimal diff + rationale.

### /fix-traceback

Purpose: analyze an error/traceback and implement the minimal fix with a root-cause summary. Inputs: traceback or log
output (required). Steps:

- identify the first actionable frame
- implement the smallest fix Output: root cause + fix summary + verify command.

### /address-review

Purpose: apply review comments (including comment-on-lines) and respond to each. Inputs: review notes (required). Steps:

- implement requested changes
- respond to each comment with action taken Output: summary + checklist of responses.

### /check-ci

Purpose: check CI status for current PR/branch and summarize failures (optionally fix). Inputs: tool=gh|gt (optional).
Steps:

- fetch CI status
- summarize failing jobs Output: failures + suggested fixes.

### /graphite-stack

Purpose: split changes into a Graphite stack with titles/descriptions. Inputs: desired boundaries (optional). Steps:

- propose stack split
- draft PR titles/descriptions Output: stack plan + PR metadata.

### /recipe-curriculum-audit

Purpose: explain maps/variants/curriculum used by a training command. Inputs: ./tools/run.py command or recipe path.
Steps:

- inspect recipe config
- summarize map list + curriculum ordering Output: concise curriculum breakdown + file paths.

### /cogames-variant-debug

Purpose: debug CoGames mission/variant regressions by comparing branch vs main. Inputs: cogames play command, expected
vs observed behavior. Steps:

- locate variant definitions and reward logic
- diff vs main Output: root cause + fix proposal + verify command.
