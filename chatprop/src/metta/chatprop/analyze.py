from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from metta.chatprop.config import ChatpropConfig, load_config
from metta.chatprop.scanner import find_transcripts_for_branches, read_transcript

logger = logging.getLogger(__name__)

MAX_PR_DIFF_CHARS = 50000
MAX_TRANSCRIPT_CHARS = 20000
MAX_TRANSCRIPTS_PER_BRANCH = 5

ANALYSIS_PROMPT = """You are analyzing coding agent transcripts to find generalizable lessons that should be \
codified in CLAUDE.md or similar project guidance files.

For each branch, you have:
1. The full transcript of the human-agent conversation that produced the work
2. The final PR diff (the ground truth of what actually landed)

Your job:
- Identify "fork in the road" moments: points where a different decision by the human or agent \
would have led to a better outcome faster
- Focus on PATTERNS, not one-off issues. A lesson is worth codifying only if it would prevent a \
class of mistakes, not just one specific mistake
- Propose specific, minimal updates to CLAUDE.md (or other guidance files in the repo)
- Each proposed update should be a concrete addition or modification, not a vague suggestion

Be ruthless about filtering: most transcripts won't have actionable lessons. That's fine. \
Only propose changes you're confident would help.

Output format:
1. For each branch, briefly summarize what happened and what the key correction points were
2. Then list proposed CLAUDE.md changes as diffs (additions/modifications to specific sections)
3. If no actionable lessons were found, say so

"""


def get_full_pr_diff(branch: str) -> str:
    try:
        result = subprocess.run(
            ["gh", "pr", "diff", branch],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return result.stdout
    except FileNotFoundError:
        logger.warning("gh CLI not found")
    return ""


def get_claude_md() -> str:
    claude_md = Path("CLAUDE.md")
    if claude_md.exists():
        return claude_md.read_text()
    return ""


def build_analysis_context(
    branches: list[str],
    config: ChatpropConfig | None = None,
) -> str:
    config = config or load_config()
    matches = find_transcripts_for_branches(config, branches)

    sections = [ANALYSIS_PROMPT]
    sections.append(f"## Current CLAUDE.md\n\n```\n{get_claude_md()}\n```\n")

    for branch in branches:
        sections.append(f"## Branch: {branch}\n")

        diff = get_full_pr_diff(branch)
        if diff:
            truncated_diff = diff[:MAX_PR_DIFF_CHARS] + "\n...(truncated)" if len(diff) > MAX_PR_DIFF_CHARS else diff
            sections.append(f"### PR Diff\n```diff\n{truncated_diff}\n```\n")
        else:
            sections.append("### PR Diff\nNo PR diff found.\n")

        branch_transcripts = [m for m in matches if branch in m.matched_branches]
        if branch_transcripts:
            sorted_transcripts = sorted(branch_transcripts, key=lambda tf: _safe_mtime(tf.path), reverse=True)
            selected_transcripts = sorted_transcripts[:MAX_TRANSCRIPTS_PER_BRANCH]
            if len(branch_transcripts) > len(selected_transcripts):
                sections.append(
                    "### Transcripts\n"
                    f"Using {len(selected_transcripts)} of {len(branch_transcripts)} matching transcripts "
                    "(most recent first).\n"
                )
            for tf in selected_transcripts:
                transcript_text = read_transcript(tf.path)
                if not transcript_text.strip():
                    continue
                truncated = (
                    transcript_text[:MAX_TRANSCRIPT_CHARS] + "\n...(truncated)"
                    if len(transcript_text) > MAX_TRANSCRIPT_CHARS
                    else transcript_text
                )
                sections.append(f"### Transcript ({tf.source}: {tf.session_id})\n```\n{truncated}\n```\n")
        else:
            sections.append("### Transcripts\nNo matching transcripts found.\n")

    return "\n".join(sections)


def run_analysis(branches: list[str], config: ChatpropConfig | None = None) -> str:
    context = build_analysis_context(branches, config)

    result = subprocess.run(
        ["claude", "--print", "-p", context],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        logger.error("claude --print failed: %s", result.stderr)
        return ""
    return result.stdout


def _safe_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0
