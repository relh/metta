# Chatprop: Unified Transcript Backprop Framework (Local-First)

> **Status:** Draft  
> **Authors:** Nishad + Richard  
> **Updated:** 2026-02-27

## Summary

Chatprop is one framework under `metta.chatprop` with two integrated tracks:

1. **Branch analysis/proposal** (`find/analyze/propose`) for CLAUDE.md and skill updates.
2. **Local collection + GUI wrapper** (`daemon/upload/status/serve`) for transcript archive, index, and exploration.

This keeps Nishad's existing command model as the primary surface and adds local backend/frontend capabilities as an
augmentation, not a separate product.

## Problem

Coding-agent sessions contain repeated decision patterns, but teams lack a tight loop that:

1. captures local transcript evidence,
2. structures that evidence into workflow/skill paths, and
3. feeds lessons back into CLAUDE.md and skill docs.

## Skill Ontology and Placement Policy

Chatprop treats prompts and skills with one model:

1. Every prompt is a manually instantiated skill (explicit or implicit).
2. `CLAUDE.md` and `AGENTS.md` are ALWAYS-true facets of skill behavior.
3. Skill files encode scoped variants, not universal policy.

Placement rules for proposed updates:

- If guidance should apply to all prompts/skills, write it to both `CLAUDE.md` and `AGENTS.md`.
- If guidance is specific to one skill, write it to that skill's `SKILL.md`.
- If many prompts are semantically the same request, refactor them into one reusable skill on topic `X`.
- If prompts consistently compose two specific topics, refactor into a combined skill on topics `X` and `Y`.

Chatprop analysis/proposal should classify each recommendation into one of these buckets before generating edits.

## Goals

- [ ] Keep a single canonical `chatprop` CLI and package (`metta.chatprop`)
- [ ] Preserve Nishad's `find/analyze/propose` workflow
- [ ] Add local archive/index backend and GUI wrapper inside the same framework
- [ ] Keep v1 local-first with no mandatory cloud dependencies
- [ ] Make branch analysis and local archive/index operate on a shared config model
- [ ] Route recommendations to `CLAUDE.md`, `AGENTS.md`, or `SKILL.md` by policy scope
- [ ] Convert repeated semantic prompt patterns into named reusable skills

## Non-Goals

- A second standalone chatprop product/package in the repo
- Mandatory cloud or S3 sync for v1
- Fully automatic merge-triggered analysis in v1

## Architecture

```text
metta.chatprop (single framework)

  Analysis track
    find/analyze/propose
      - locate branch transcripts
      - compare against final PR diff
      - classify scope (global vs skill-specific)
      - propose updates to CLAUDE.md + AGENTS.md (global) or SKILL.md (scoped)

  Local data + UX track
    daemon/upload/status
      - archive raw transcripts under ~/.chatprop
      - maintain manifest + metadata + branch index
    serve
      - render local workflow frontend
      - provide GUI wrappers for branch analysis (`find`, context preview, `analyze`)
```

Local storage layout:

```text
~/.chatprop/
  config.toml
  manifest.json
  archive/
    transcripts/claude-code/<session-id>-<mtime>.jsonl
    transcripts/codex/<session-id>-<mtime>.jsonl
    metadata/<session-id>.json
    index.json
```

## CLI Surface

Primary analysis commands (Nishad framework):

- `chatprop find <branch...>`
- `chatprop analyze <branch...> [--dry-run]`
- `chatprop propose <branch...>`

Augmenting local data/UI commands:

- `chatprop daemon [--once] [--install]`
- `chatprop upload <session-id>`
- `chatprop status`
- `chatprop serve`

## Package Structure

```text
chatprop/src/metta/chatprop/
  cli.py
  config.py
  scanner.py
  analyze.py
  local/
    daemon.py
    indexer.py
    models.py
    launchd.py
    backend/
    frontend/
```

`local/` modules are implementation details that augment the core `metta.chatprop` framework. The public command surface
remains one `chatprop` CLI.

## Config

`~/.chatprop/config.toml`:

```toml
[sources.claude-code]
path = "~/.claude/projects"

[sources.codex]
path = "~/.codex/sessions"

[daemon]
poll_interval_seconds = 30
inactivity_threshold_seconds = 60

[state]
dir = "~/.chatprop"
```

## Future Work

- Machine-readable proposal output for ranking/triage
- Cross-PR aggregation and pattern confidence tracking
- Optional team sync/cloud export as a non-default mode
