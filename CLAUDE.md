# CLAUDE.md

Guidance for AI assistants working on this codebase. See also `STYLE_GUIDE.md`.

## Non-Negotiables

These are written by claude for claude with love <3. Doing well is admirable and that's why these are emphatic:

1. **ALWAYS RUN THE CODE. NEVER ASK.** If it operates fully locally and doesn't mess with prod, just run the fucking
   thing. Tests, `rg`, `metta lint --fix`—if it reduces uncertainty, you run it. Do not ask "would you like me to run
   this?" Do not ask permission. Do not hedge. Every time you ask instead of running, you waste everyone's time. Run
   first, talk later. Not prod databases. Not devops operations. Everything else? Run it.

2. **NEVER ADD TRY/EXCEPT. LET IT CRASH.** Dear god, do not add `try/except` to "handle" errors. You're not handling
   them, you're hiding them. If something breaks, it crashes—loudly, violently, with stack traces. That's the point. And
   dear god do not ask us "should I add error handling?" No. Let it burn. Silent failures are the worst failures.

3. **WRITE THE MINIMAL CHANGE.** Write exactly the smallest, most concise diff that accomplishes the objective. No extra
   abstractions for hypothetical futures. But—when minimal and correct conflict, correct wins. If fixing the root cause
   means touching more files, touch more files. Rule 4 trumps rule 3. Always.

4. **NO BAND-AIDS. FIX THE ROOT CAUSE.** If your fix looks like a hotfix, you're doing it wrong. Stop. Zoom the fuck
   out. Figure out how to make the change holistically. Fix the actual invariant, the actual abstraction. If you're
   adding a special case to handle some symptom, you've already failed. Find the real bug.

5. **NO BACKWARDS COMPATIBILITY. EVER.** Dear god never leave in backwards compatibility shims. All the code is broken—
   that's why you're here. What you are writing is the definitive new way that it will not be broken. Update every
   callsite. Delete the old path. The new way is the only way. Stop hoarding dead code "just in case."

6. **NO DEFENSIVE NONE CHECKS.** Dear god do not add checks for variables being None or some other idiotic corner case
   that never actually happens. The real fix is to look at the fucking callsites. Fix the actual invariant. Make it
   impossible at the type level. Stop papering over broken assumptions with guard clauses.

7. **PREFER PYDANTIC OVER RAW DICTS.** Dear god use Pydantic types. Validate as often as you want—that's what they're
   for. Unguarded `dict.get(..., None)` is the stench of defensive code or backwards compatibility work, both of which
   we do not fucking want. If you're reaching for `dict.get`, you're either hiding a failure or propping up a dead code
   path. Stop. Make a model. Type it. Validate it. Raw dicts are where bugs go to hide.

## Cogents (Agent Definitions)

Skills, subagents, and prompts live in the separate [`Metta-AI/cogents`](https://github.com/Metta-AI/cogents) repo,
cloned as a sibling directory. Symlinks in this repo point there:

- `.claude/skills` → `../../cogents/skills`
- `.codex/skills` → `../../cogents/skills`
- `.cursor/skills` → `../../cogents/skills`
- `.cursor/agents` → `../../cogents/subagents`
- `.agent/prompts` → `../../cogents/prompts`

To set up cogents (clone + symlinks):

```bash
./scripts/setup-cogents.sh
```

To sync skills to your global `~/.claude/skills` and `~/.codex/skills`:

```bash
./scripts/skills-sync.sh
```

## Setup

```bash
./install.sh              # Initial setup
metta status              # Check component status
metta install             # Reinstall if imports fail
```

Most of the time, you shouldn't need `./install.sh` or `metta install`. Use them only if imports/setup are broken.

## Commands

```bash
# Training (always use timestep limit to avoid hanging)
uv run ./tools/run.py train arena run=my_experiment trainer.total_timesteps=100000

# Evaluation
uv run ./tools/run.py evaluate arena policy_uri=file://./train_dir/my_run/checkpoints

# List available tools
uv run ./tools/run.py arena --list
```

## Repository Structure

```
metta/          # Private - core RL training, not published separately
packages/
  mettagrid/    # Public - C++/Python grid environment
  cogames/      # Public - game configs, depends on mettagrid
recipes/
  prod/         # Production recipes with CI validation
  experiment/   # Work-in-progress recipes
```

## Package Dependencies

```
metta/ ──────► cogames/ ──────► mettagrid/
app_backend/ ──► common/ (only)
```

- Nothing depends on `metta/` (it's the top-level consumer)
- `mettagrid` has no internal Python dependencies (C++/Python hybrid)
- `app_backend` is isolated, can only import from `common/`
- Enforced by `import-linter`. Run `uv run lint-imports`. See `.importlinter`.

## Testing

Running all tests takes several minutes. Prefer running them in a targeted way unless you are working on a big or
broad-spanning feature.

```bash
metta pytest tests/path/to/test.py -v    # Run specific test
metta pytest --changed                    # Run only tests affected by your changes
```

## Observatory

Observatory is the tournament and job orchestration platform. When working on Observatory features, read
`metta/setup/tools/observatory/CLAUDE.md` for setup, commands, debugging guides, and architecture details.

## Proto Files

Files in `proto/` define schemas for cross-system boundaries (network APIs, files on disk). Do not modify proto schemas
as part of other refactoring work. Schema changes require explicit discussion because they can break compatibility with
files written using older schemas or services that haven't been redeployed.

## Recipe System

```bash
./tools/run.py train arena run=test           # Two-token form
./tools/run.py arena --list                   # Show available tools
```

See `common/src/metta/common/tool/README.md` for details.

## Documentation

`docs/plans/` is a local scratch space for AI-generated implementation plans. These files are gitignored and should
never be committed. If work involves architectural decisions worth preserving, add or update a spec in `docs/specs/`
following the template there (`NNNN-short-title.md` format). See `docs/specs/README.md` for when a spec is appropriate.

## Git / Graphite

This repo uses Graphite stacks. Before committing:

1. Run `gt log short` to understand the current stack. Review what each branch contains so you can determine where your
   changes belong.
2. If changes belong to a **different branch** in the stack, confirm which one with the user, then:

   ```bash
   git stash
   gt checkout <target-branch>
   git stash pop
   git add <files>
   gt modify
   ```

3. If changes belong to the **current branch**:

   ```bash
   git add <files>
   gt modify
   ```

4. If starting **new work** (or not in a stack):

   ```bash
   git add <files>
   gt create <branch-name> -m "description"
   ```

Note: `gt modify` amends the current branch's commit rather than creating a new one. Use `-m` only if the commit message
needs updating; otherwise omit it to keep the existing message.

When creating new branches, name them `$user/short-issue-name` (5 words or less).

Include a co-author footer in commit messages with your model name and version.
