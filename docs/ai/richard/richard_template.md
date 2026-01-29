# Richard Higgins - Template Command Candidates

This file collects candidate Codex slash commands (skills) derived from local session logs. Append new sections per
workspace to keep contributions merge-friendly.

## Dummyspace Metta (/Users/relh/Code/dummyspace/metta)

Source notes:

- Logs scanned: ~/.codex/sessions/2025 and ~/.codex/sessions/2026
- Workspace filter: /Users/relh/Code/dummyspace/metta
- Prompts observed: 1452 across 199 session files (user prompts only)

### /cb.review-main

- Intent: Review branch changes against main with a merge-base diff and return prioritized findings.
- Typical ask: "Review the code changes against the base branch 'main'... Run git diff <merge-base> and provide
  prioritized, actionable findings."
- Template:
  - Compute merge base when not provided: `git merge-base HEAD "$(git rev-parse --abbrev-ref "main@{u}")"`
  - Run: `git diff <merge-base>`
  - Output: prioritized findings, risks, and suggested fixes.

### /pr.summary

- Intent: Audit branch vs main and write a short PR summary (what changed, why, tests, risks).
- Typical ask: "Can you audit our branch vs main and write a PR summary for us?"
- Template:
  - Summarize scope, key files, and behavior changes.
  - Note tests run or recommend targeted tests.

### /relh.pr.merge-conflicts

- Intent: Resolve merge conflicts (often after main updates), preserve main where required, explain key resolutions.
- Typical ask: "Can you resolve the merge conflicts... and explain what the diff is about?"
- Template:
  - Resolve conflicts, highlight any non-trivial decisions.
  - Provide a short explanation of the final shape.

### /cb.lint-fix

- Intent: Run lint auto-fix and address remaining issues.
- Typical ask: "Can you run metta lint --fix and address the issues?"
- Template:
  - Run: `metta lint --fix`
  - Fix any remaining lint errors and summarize changes.

### /db.run-and-triage

- Intent: Run one or more commands and report errors/root cause (often training or eval).
- Typical ask: "Run ./devops/run.sh train ... and tell me what errors you see."
- Template:
  - Execute the provided command(s).
  - Summarize failures, point to offending files, propose fixes.

### /tr.checkpoint-find

- Intent: Locate a checkpoint for a run id and provide the next command to use it.
- Typical ask: "Investigate this run and find a checkpoint for it; I think they save every N."
- Template:
  - Find latest checkpoint for a run id.
  - Return a follow-up command (often `cogames play ...` or eval).

### /policy-play

- Intent: Produce a working `cogames play` command for a given policy or run.
- Typical ask: "Give me a play command for this policy."
- Template:
  - Use provided policy/run id, mission, cogs, and variant to build `cogames play`.

### /cb.sync-nim-python

- Intent: Compare Nim vs Python scripted agent implementations and port missing behavior.
- Typical ask: "Compare the python version with our nim version and port over any missing/different functionality."
- Template:
  - Enumerate functional differences.
  - Port or align behavior and update tests/docs as needed.

## Metta (/Users/relh/Code/metta)

### /cb.review-main

- Intent: Review the merge diff vs main and return prioritized, actionable findings.
- Template: "Review the code changes against the base branch 'main'. Start by finding the merge diff between the current
  branch and main's upstream e.g. (`git merge-base HEAD \"$(git rev-parse --abbrev-ref \"main@{upstream}\")\"`), then
  run `git diff` against that SHA to see what changes we would merge into the main branch. Provide prioritized,
  actionable findings."

### /relh.cb.branch-hygiene

- Intent: Audit the branch for unintended changes vs main and call out cleanup or missing tests.
- Template: "Audit this branch against origin/main. Show the merge-base SHA, list the files changed, and call out
  anything that looks unintended or risky. Keep the diff surface minimal and suggest cleanups if needed."

### /debug-command

- Intent: Run a command (often `metta`, `uv run`, or `cogames`) and debug until it succeeds.
- Template: "Run this command and keep debugging until it works. If it fails, identify the root cause, fix it minimally,
  and re-run: <COMMAND>"

### /db.fix-traceback

- Intent: Analyze a traceback or error log and patch the minimal fix with a short root-cause summary.
- Template: "Here is the traceback/error output. Identify the root cause and implement the smallest sensible fix.
  Summarize why it broke and why the fix works: <TRACEBACK_OR_LOG>"

### /cb.simplify-diff

- Intent: Make a change more concise while preserving behavior.
- Template: "Make this change more concise while preserving behavior. Prefer inlining or removing redundant
  code/comments and keep the diff minimal: <FILE_OR_SNIPPET>"

### /tr.cogames-command

- Intent: Craft or adjust `cogames`/`uv run` commands for missions, variants, and policies.
- Template: "I want to run or modify this cogames command. Please adjust it to fit the goal and explain the final
  command: <COMMAND_AND_GOAL>"

### /cb.lint-fix

- Intent: Run `metta lint --fix`, address remaining issues, and summarize changes.
- Template: "Run `metta lint --fix`, fix any remaining lint failures, and summarize what changed."

### /review-comments

- Intent: Address code review comments or change requests and respond to each one.
- Template: "Here are review comments. Please address each comment in code and respond to each one with what you
  changed: <COMMENTS>"

## Metta (Linux, /home/relh/Code/metta)

Notes:

- Logs scanned: ~/.codex/sessions/2025 and ~/.codex/sessions/2026
- Workspace filter: /home/relh/Code/metta (and related /home/relh/Code/\*/metta workspaces)
- Prompts observed: included in combined totals in richard.md; per-workspace counts are not broken out here.

### /cb.review-main

- Intent: Review the merge diff vs origin/main and return prioritized, actionable findings.
- Template: "Review the code changes vs origin/main using the merge base and list prioritized findings."

### /relh.cb.branch-hygiene

- Intent: Audit the branch for unintended changes or simplification opportunities.
- Template: "Audit this branch vs origin/main and call out any unintended changes or cleanup opportunities."

### /relh.tr.run-recipe

- Intent: Run ./tools/run.py recipes (train/play/evaluate) with timeouts and summarize results.
- Template: "Run ./tools/run.py <recipe>.<mode> with these args, capture failures, and summarize results."

### /debug-command

- Intent: Run a command (metta/uv/cogames) and debug until it succeeds.
- Template: "Run this command and debug until it works. If it fails, identify the root cause and fix it: <COMMAND>"

### /db.fix-traceback

- Intent: Analyze a traceback or error log and implement the smallest fix.
- Template: "Identify the root cause in this traceback and implement the minimal fix: <TRACEBACK_OR_LOG>"

### /cb.simplify-diff

- Intent: Make a change more concise while preserving behavior.
- Template: "Make this more concise without changing behavior; keep the diff minimal: <FILE_OR_SNIPPET>"

### /tr.cogames-command

- Intent: Craft or adjust cogames commands (train/play/eval) for missions/variants/policies.
- Template: "Adjust this cogames command to meet the goal and explain key flags: <COMMAND_AND_GOAL>"

### /cb.lint-fix

- Intent: Run metta lint --fix and address remaining lint errors.
- Template: "Run metta lint --fix, fix remaining lint issues, and summarize changes."

### /pr.check-ci

- Intent: Check CI status with gh/gt and summarize failures (optionally fix).
- Template: "Check CI for this PR/branch with gh/gt and summarize failures. Fix if needed."

### /st.graphite-stack

- Intent: Split changes into a Graphite stack with titles/descriptions.
- Template: "Split this branch into a Graphite stack and draft PR titles/descriptions."

## Workspace Metta (/Users/relh/Code/workspace/metta)

Notes:

- These were observed in `/Users/relh/Code/workspace/metta`.
- Overlaps with the dummyspace list above are omitted here to reduce duplication.

### /audit-origin-main

- Intent: Audit branch vs origin/main for unnecessary changes and suggest cleanups.
- Typical ask: "Audit our branch compared to origin/main to make sure we dont have unnecessary additions."
- Template:
  - Run `git diff origin/main` (or merge-base as needed).
  - Call out extraneous files/changes and propose reductions.

### /st.graphite-stack

- Intent: Split the branch into a Graphite stack and draft titles/descriptions.
- Typical ask: "Split our branch into a few separate stacked PR's a la Graphite."
- Template:
  - Propose stack boundaries.
  - Create/update PR titles and descriptions.

### /pr.check-ci

- Intent: Use gh/gt to check CI status and summarize failures (optionally fix).
- Typical ask: "Check CI with gh/gt and fix whatever issues you find."
- Template:
  - Fetch CI results for the current PR/branch.
  - Summarize failing jobs and propose fixes.

### /pytest-debug

- Intent: Run targeted pytest, debug failures, and fix.
- Typical ask: "Run pytest and investigate why we aren't passing tests."
- Template:
  - Run `metta pytest --changed` or the requested test target.
  - Investigate failures and summarize root cause + fix.

### /cogames-train

- Intent: Run a quick `cogames train` for a specified mission/variants.
- Typical ask: "Give me a full cogames train command with more missions."
- Template:
  - Run `uv run cogames train --mission <mission> --variant <v1> ...`.
  - Report key metrics and issues.

### /cogames-play

- Intent: Run a `cogames play` command for a specified mission/policy.
- Typical ask: "Give me a cogames play command to run this policy."
- Template:
  - Run `uv run cogames play --mission <mission> --cogs <n> -p <policy>`.
  - Summarize observed behavior/issues.

### /cogames-eval

- Intent: Run evaluation script and summarize results.
- Typical ask: "Run run_evaluation.py for agent X and summarize the outcome."
- Template:
  - Run `uv run packages/cogames/scripts/run_evaluation.py --agent <agent> --cogs <n> --repeats <n>`.
  - Summarize results/regressions.

### /relh.tr.run-recipe

- Intent: Run a recipe via `./tools/run.py` (train/play/evaluate) and summarize outcome.
- Typical ask: "Run ./tools/run.py <recipe>.<mode> and summarize the outcome."
- Template:
  - Run `uv run ./tools/run.py <recipe>.<mode> <args...>` with a reasonable timeout.
  - Summarize outcome and errors.

### /resolve-merge-main

- Intent: Merge/rebase origin/main, resolve conflicts, and preserve intended changes.
- Typical ask: "Merge main and resolve conflicts, keep main where possible."
- Template:
  - Merge/rebase origin/main.
  - Resolve conflicts, explain non-trivial decisions.

## Fourthspace Metta (/Users/relh/Code/fourthspace/metta)

### /cb.review-main

Purpose: review branch changes vs main using merge-base diff and return prioritized findings. Inputs: base_branch=main
(default), focus_paths (optional), output=prioritized_findings. Template:

- "Review the code changes against the base branch 'main'. Find the merge base, run git diff from that SHA, and list
  prioritized actionable findings."

### /pr.summary

Purpose: generate PR title + description from branch diff vs main (optionally read current PR via gh/gt). Inputs:
base_branch=main (default), include_tools={gh,gt} (optional), format=title+body. Template:

- "Analyze our branch vs main and write a PR title and description that reflects what changed and why."

### /cb.lint-fix

Purpose: run lint autofix and report the resulting changes. Inputs: lint_cmd="metta lint --fix", scope=touched_files
(optional). Template:

- "Run metta lint --fix, fix issues, and summarize the changes (focus on files we touched)."

### /test-audit

Purpose: update any broken tests and run targeted pytest. Inputs: test_cmd="metta pytest --changed" (or explicit path),
include_lint (optional). Template:

- "If this might break tests, update them and run pytest (targeted if possible). Summarize failures and fixes."

### /eval-script

Purpose: run evaluation scripts (evaluate_scripted_agents.py or run_evaluation.py), compare branch vs main, and debug
errors or speed issues. Inputs: eval_cmd (required), compare_to=origin/main (optional), focus=performance|correctness.
Template:

- "Run the evaluation command, compare results to origin/main, and summarize differences or fixes."

### /relh.tr.run-recipe

Purpose: run tools/run.py recipes for training or evaluation, and summarize outcomes or failures. Inputs: recipe_cmd
(required), timeout (optional), summary=short. Template:

- "Run ./tools/run.py <recipe> with these args, capture failures, and summarize the outcome."

### /cb.cleanup-refactor

Purpose: remove legacy/backcompat shims and simplify code while keeping behavior stable. Inputs: target_paths
(required), constraints="no legacy shims" (optional). Template:

- "Refactor for conciseness and remove legacy shims/backcompat. Keep the diff tight and behavior unchanged."

### /pr.address-review

Purpose: apply Graphite/PR review comments or "comment on lines" feedback and verify. Inputs: review_notes (required),
verification=tests_or_lint (optional). Template:

- "Address these review comments (comment-on-lines) and re-run the relevant checks. Summarize changes."

### /branch-audit-simplify

Purpose: audit branch changes and call out simplification opportunities. Inputs: base_branch=origin/main (default).
Template:

- "Audit our branch for simplification opportunities, list redundant/defensive code, and suggest minimal cleanups."

## Thirdspace Metta (/Users/relh/Code/thirdspace/metta)

These are candidate slash commands derived from Codex session logs where `cwd=/Users/relh/Code/thirdspace/metta`.

### /pr-review-main

- Intent: Review current branch vs origin/main and list prioritized findings.
- Inputs: optional focus area(s) or paths.
- Actions: `git fetch origin`; `base=$(git merge-base HEAD origin/main)`; review `git diff $base`; scan tests.
- Output: findings ordered by severity + overall correctness verdict.

### /pr-summary-branch

- Intent: Write a clean PR summary for the current branch.
- Inputs: optional audience (tech/non-tech) or focus.
- Actions: `git fetch origin`; `base=$(git merge-base HEAD origin/main)`; summarize `git diff --stat $base` + key file
  diffs.
- Output: 5-10 bullet summary + tests/run commands.

### /merge-conflicts-main

- Intent: Resolve merge conflicts after merging main (preserve current branch intent).
- Inputs: conflict list from `git status` or specific files to prioritize.
- Actions: inspect conflict files; keep upstream structure while preserving branch behavior; run targeted tests if
  asked.
- Output: resolved files + short rationale per file.

### /lint-fix-branch

- Intent: Run `metta lint --fix` and limit changes to branch-touched files.
- Inputs: optional path allowlist (e.g. `notebooks/`).
- Actions: list changed files; run `metta lint --fix`; revert unrelated diffs; rerun lint if needed.
- Output: clean working tree + commit-ready change list.

### /test-failure-triage

- Intent: Diagnose pytest/CI failures or stack traces and propose fixes.
- Inputs: failing command output or traceback.
- Actions: identify failing tests, locate source code, explain root cause, suggest minimal fix + rerun command.
- Output: root cause + patch plan + verification command.

### /tr.cogames-variant-debug

- Intent: Debug CoGames mission/variant behavior regressions.
- Inputs: `uv run cogames play` command, expected vs observed behavior.
- Actions: locate variant definitions, reward/assembler logic, and map setup; diff vs main to find regressions.
- Output: cause + patch suggestion + repro/verify command.

### /tr.recipe-curriculum-audit

- Intent: Explain which maps/variants/curriculum a training command uses.
- Inputs: `./tools/run.py` train command or recipe path.
- Actions: inspect recipe config, map lists, curriculum ordering, and cache usage; call out any overrides.
- Output: concise curriculum/map breakdown + relevant file paths.

### /tr.policy-save-load-audit

- Intent: Audit policy save/load and checkpoint handling across metta/cogames.
- Inputs: affected files or error logs (PolicySpec, .mpt, safetensors).
- Actions: trace save/load call graph, verify compatibility points, remove legacy shims when safe.
- Output: compatibility report + recommended cleanup steps.
