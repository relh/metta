# Chatprop: Transcript-Driven CLAUDE.md Improvement

> **Status:** Draft **Author:** Nishad **Created:** 2026-02-26

## Summary

A CLI tool that searches local Claude Code and Codex transcripts for sessions related to specific branches/PRs, analyzes
them against the final PR diff to find "fork in the road" moments, and opens a PR with proposed CLAUDE.md updates. Named
after backpropagation: compare what landed against what was first attempted, adjust the "model" (CLAUDE.md, skills)
accordingly.

## Problem

When working with coding agents to build and ship PRs, there are predictable points where a different decision by the
human or agent would have led to a better outcome. These patterns are visible in hindsight but currently no system
captures or learns from them. Learnings stay trapped in individual sessions and human memory.

## Solution

A local CLI tool that:

1. Greps local transcript files for branch/PR names to find relevant sessions
2. Gets the final PR diff via `gh pr diff`
3. Sends transcripts + diffs + current CLAUDE.md to Claude for analysis
4. Opens a PR with proposed CLAUDE.md updates

No cloud infrastructure needed — everything runs locally against files already on disk.

## Goals

- [ ] Find transcripts matching branch names across Claude Code and Codex
- [ ] Analyze transcripts against final PR diffs to find correctable patterns
- [ ] Propose CLAUDE.md updates as a PR

## Non-Goals

- S3 upload or cloud storage (future phase)
- Real-time transcript analysis during sessions
- Perfect reconstruction of intermediate git states (lossy comparison is fine)
- Automated triggering on PR merge (future phase — run manually for now)

## Design

### Architecture

```
LOCAL MACHINE

~/.claude/projects/*/*.jsonl ──┐
~/.codex/sessions/**/*.jsonl ──┼── chatprop find <branches>
                               │     grep for branch names
                               └── matched transcripts
                                        │
                                        ▼
                               chatprop analyze <branches>
                                 1. Read matched transcripts
                                 2. Get PR diff via gh pr diff
                                 3. Send to claude --print
                                 4. Output analysis results
                                        │
                                        ▼
                               chatprop propose <branches>
                                 1. Run analysis
                                 2. Apply CLAUDE.md changes
                                 3. Open PR via gh pr create
```

### Transcript Sources

- **Claude Code**: `~/.claude/projects/<project-slug>/<session-id>.jsonl` — JSONL with `user`, `assistant`, `progress`
  (tool calls), `system` message types. Contains `gitBranch` field, full model responses, tool inputs/outputs.
- **Codex**: `~/.codex/sessions/<year>/<month>/<day>/rollout-<timestamp>-<id>.jsonl` — similar JSONL format with session
  metadata and tool calls.

### CLI

- `chatprop find <branch1> <branch2> ...` — find matching transcripts
- `chatprop analyze <branch1> ... [--dry-run]` — analyze transcripts (dry-run shows context without calling Claude)
- `chatprop propose <branch1> ...` — analyze and open PR with CLAUDE.md updates

### Analysis

The analysis prompt asks Claude to:

1. Identify "done signal" moments where the agent thought work was complete
2. Compare the agent's state at each done signal against the final merged diff
3. Find generalizable patterns (not one-off issues)
4. Propose specific, minimal CLAUDE.md updates

Comparison is intentionally lossy — force-pushes from `gt sync` make intermediate SHAs unreliable, so we reconstruct
intent from transcript content (tool calls, file writes) rather than git history.

### Package Structure

```
chatprop/
  pyproject.toml
  src/metta/chatprop/
    __init__.py
    analyze.py       # Build context, call claude --print
    cli.py           # Click CLI
    config.py        # Source paths
    scanner.py       # Find and read transcripts
```

## Future Work

- **S3 sync**: Daemon or hook to upload transcripts to S3 for team-wide analysis
- **GitHub Actions trigger**: Auto-run analysis on PR merge
- **Cross-PR aggregation**: Analyze multiple PRs together to find broader patterns
- **Transcript indexing**: Pre-built index mapping branches to transcript keys for faster lookup

## Open Questions

1. Should analysis aggregate across multiple PRs to find cross-PR patterns, or strictly analyze one PR at a time?
2. What's the right context window strategy when transcripts are very large (>100k tokens)?
