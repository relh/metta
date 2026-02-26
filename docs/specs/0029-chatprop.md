# Chatprop: Transcript-Driven CLAUDE.md Improvement

> **Status:** Draft **Author:** Nishad **Created:** 2026-02-26

## Summary

A system that uploads full Claude Code and Codex transcripts to S3, then analyzes them on PR merge to find predictable
fork-in-the-road moments and propose CLAUDE.md updates. Named after backpropagation: compare what landed against what
was first attempted, adjust the "model" (CLAUDE.md, skills) accordingly.

## Problem

When working with coding agents to build and ship PRs, there are predictable points where a different decision by the
human or agent would have led to a better outcome. These patterns are visible in hindsight but currently no system
captures or learns from them. Learnings stay trapped in individual sessions and human memory.

## Solution

Two-phase system:

1. **Collection**: Local daemon uploads full transcripts to S3.
2. **Analysis**: GitHub Actions workflow on PR merge finds relevant transcripts, compares each "done" signal against the
   final merged state, and opens a PR with proposed CLAUDE.md updates.

## Goals

- [ ] All Claude Code and Codex transcripts uploaded to S3 automatically
- [ ] Transcripts indexed by branch name for fast lookup
- [ ] On PR merge, relevant transcripts are identified and analyzed
- [ ] Analysis produces actionable CLAUDE.md update PRs

## Non-Goals

- Real-time transcript analysis during sessions
- Perfect reconstruction of intermediate git states (lossy comparison is fine)
- Codex hook integration (Codex has no Stop hook; daemon handles it via polling)

## Design

### Architecture

```
LOCAL MACHINE                               S3 (chatprop-transcripts)
                                            ├── transcripts/
~/.claude/projects/*/*.jsonl ──┐            │   ├── claude-code/
~/.codex/sessions/**/*.jsonl ──┼── daemon ──┤   └── codex/
                               │  (30s poll)├── metadata/
                               └────────────└── index.json

GITHUB ACTIONS (on PR merge)
  1. Read index.json from S3
  2. Find transcripts matching merged branch
  3. Download matched transcripts + get PR diff
  4. Spawn claude --headless for analysis
  5. Open PR with proposed CLAUDE.md updates
```

### Phase 1: Transcript Collection

#### Daemon

Polling daemon that watches transcript directories and uploads completed sessions to S3. Deliberately dumb — no semantic
parsing, no done-signal detection, no PR correlation.

Core loop (every 30 seconds):

1. Scan `~/.claude/projects/*/` and `~/.codex/sessions/` for `.jsonl` files
2. Compare `(path, mtime, size)` against local manifest (`~/.chatprop/manifest.json`)
3. If file is new/changed and inactive >60s, upload raw transcript to S3
4. Write minimal metadata sidecar, update manifest

Metadata (per transcript):

```python
class TranscriptMetadata(BaseModel):
    session_id: str
    source: Literal["claude-code", "codex"]
    started_at: datetime
    ended_at: datetime
    transcript_s3_key: str
    size_bytes: int
```

#### Index

Separate indexing step scans transcripts in S3, extracts `gitBranch` fields from JSONL content, and builds `index.json`
mapping branch names to transcript S3 keys. Updated incrementally after each upload. This avoids downloading all
transcripts during analysis.

#### CLI

- `chatprop daemon` — run polling loop (foreground)
- `chatprop daemon --install` — install macOS launchd plist
- `chatprop upload <session-id>` — manual upload
- `chatprop status` — daemon status and manifest stats

#### Config

`~/.chatprop/config.toml`:

```toml
[s3]
bucket = "chatprop-transcripts"
region = "us-east-1"

[sources.claude-code]
path = "~/.claude/projects"

[sources.codex]
path = "~/.codex/sessions"

[daemon]
poll_interval_seconds = 30
inactivity_threshold_seconds = 60
```

#### S3 Key Structure

```
s3://chatprop-transcripts/
  transcripts/claude-code/<session-id>.jsonl
  transcripts/codex/<session-id>.jsonl
  metadata/<session-id>.json
  index.json
```

#### Package Structure

```
metta/chatprop/
  __init__.py
  daemon.py
  s3.py
  indexer.py
  config.py
  models.py
  cli.py
  launchd.py
```

### Phase 2: Analysis Pipeline

#### Trigger

GitHub Actions: `on: pull_request: types: [closed]`, filtered to `merged == true`.

#### Steps

1. **Find transcripts**: Read `index.json`, find transcripts referencing the merged branch (from `gitBranch` fields,
   `git push` calls, `gh pr create` output).

2. **Build timeline**: Parse matched transcripts to identify "done signals" — points where the agent signaled
   completion:
   - Tool calls to `gh pr create` / `gt create`
   - Tool calls to `git push` after a PR exists
   - Assistant messages indicating completion

3. **Compare against ground truth**: Final merged PR diff (`gh pr diff`) is ground truth. Compare against the agent's
   file write/edit tool calls around each done signal. Intentionally lossy — force-pushes from `gt sync` make
   intermediate SHAs unreliable, so we reconstruct intent from transcript content rather than git history.

4. **Claude analysis**: Spawn `claude --headless` with transcripts, PR diff, current CLAUDE.md. Ask it to identify
   predictable, generalizable lessons and propose specific CLAUDE.md updates.

5. **Open PR**: Branch `chatprop/learnings-<pr-number>` with proposed changes and reasoning in the description.

#### What Analysis Looks For

- Patterns the agent consistently gets wrong that the human corrects
- Architectural decisions that always get revised
- Missing CLAUDE.md context that would have prevented a class of correction
- Workflow patterns (forgetting tests, wrong branch conventions)

## Open Questions

1. Should the index be a single `index.json` or sharded per-project/per-month?
2. What's the right `claude --headless` invocation for the analysis step? Need to verify CLI supports this or whether to
   use the API directly.
3. Should analysis aggregate across multiple PRs to find cross-PR patterns, or strictly analyze one PR at a time?
