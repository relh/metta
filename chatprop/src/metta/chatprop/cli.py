from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

import click

from metta.chatprop.analyze import build_analysis_context, run_analysis
from metta.chatprop.config import load_config
from metta.chatprop.scanner import find_transcripts_for_branches, read_transcript


def _has_transcript_content(paths: list[Path]) -> bool:
    return any(read_transcript(path).strip() for path in paths)


def _current_branch() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


@click.group()
def main() -> None:
    """Chatprop: analyze coding agent transcripts to improve CLAUDE.md."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


@main.command()
@click.argument("branches", nargs=-1, required=True)
def find(branches: tuple[str, ...]) -> None:
    """Find local transcripts matching branch or PR names."""
    config = load_config()
    matches = find_transcripts_for_branches(config, list(branches))
    if not matches:
        click.echo("No matching transcripts found.")
        sys.exit(1)
    for tf in matches:
        click.echo(f"{tf.source} | {tf.session_id} | {tf.size_bytes:,}B | branches: {tf.matched_branches}")
        click.echo(f"  {tf.path}")


@main.command()
@click.argument("branches", nargs=-1, required=True)
@click.option("--dry-run", is_flag=True, help="Print analysis context without calling Claude")
def analyze(branches: tuple[str, ...], dry_run: bool) -> None:
    """Analyze transcripts for branches and propose CLAUDE.md updates."""
    branch_list = list(branches)
    config = load_config()

    matches = find_transcripts_for_branches(config, branch_list)
    click.echo(f"Found {len(matches)} transcript(s) across {len(branch_list)} branch(es)")
    if not matches:
        click.echo("No matching transcripts found.")
        sys.exit(1)
    for tf in matches:
        click.echo(f"  {tf.source}: {tf.session_id} ({tf.size_bytes:,}B)")

    if not _has_transcript_content([tf.path for tf in matches]):
        click.echo("Matched transcripts contain no parseable conversation/tool data. Aborting.")
        sys.exit(1)

    if dry_run:
        context = build_analysis_context(branch_list, config)
        click.echo(f"\n--- Analysis context ({len(context):,} chars) ---\n")
        click.echo(context)
        return

    click.echo("\nRunning analysis via claude --print ...")
    output = run_analysis(branch_list, config)
    if not output:
        click.echo("Analysis produced no output.")
        sys.exit(1)

    click.echo("\n--- Analysis Results ---\n")
    click.echo(output)


@main.command()
@click.argument("branches", nargs=-1, required=True)
@click.option("--branch-name", default=None, help="Branch name for the PR (default: <branch>-chatprop-proposal)")
def propose(branches: tuple[str, ...], branch_name: str | None) -> None:
    """Analyze transcripts and open a PR with proposed CLAUDE.md updates."""
    branch_list = list(branches)
    config = load_config()

    matches = find_transcripts_for_branches(config, branch_list)
    click.echo(f"Found {len(matches)} transcript(s) across {len(branch_list)} branch(es)")
    if not matches:
        click.echo("No matching transcripts found.")
        sys.exit(1)

    if not _has_transcript_content([tf.path for tf in matches]):
        click.echo("Matched transcripts contain no parseable conversation/tool data. Aborting.")
        sys.exit(1)

    click.echo("Running analysis via claude --print ...")
    output = run_analysis(branch_list, config)
    if not output:
        click.echo("Analysis produced no output.")
        sys.exit(1)

    click.echo("\n--- Analysis Results ---\n")
    click.echo(output)

    pr_branch = branch_name or f"{branch_list[0]}-chatprop-proposal"
    claude_md = Path("CLAUDE.md")
    if not claude_md.exists():
        click.echo("No CLAUDE.md found in current directory.")
        sys.exit(1)

    click.echo(f"\nApplying changes on branch {pr_branch} ...")

    current_claude_md = claude_md.read_text()
    apply_result = subprocess.run(
        [
            "claude",
            "--print",
            "-p",
            f"""Given this analysis output, apply the proposed CLAUDE.md changes.
Output ONLY the new full contents of CLAUDE.md, nothing else.

{output}

Current CLAUDE.md:
{current_claude_md}""",
        ],
        capture_output=True,
        text=True,
    )
    if apply_result.returncode != 0 or not apply_result.stdout.strip():
        click.echo("Failed to generate updated CLAUDE.md")
        sys.exit(1)

    updated_claude_md = apply_result.stdout
    if updated_claude_md == current_claude_md:
        click.echo("No CLAUDE.md changes proposed. Skipping PR creation.")
        return

    claude_md.write_text(updated_claude_md)

    starting_branch = _current_branch()
    subprocess.run(["git", "add", "CLAUDE.md"], check=True)
    title = f"chatprop: CLAUDE.md learnings from {', '.join(branch_list)}"
    body = f"Auto-generated by chatprop from analysis of branches: {', '.join(branch_list)}\n\n{output[:3000]}"
    try:
        subprocess.run(["gt", "create", pr_branch, "-m", title], check=True)
        subprocess.run(["gt", "submit", "--no-edit"], check=True)
        subprocess.run(["gh", "pr", "edit", "--title", title, "--body", body], check=True)
    finally:
        if _current_branch() != starting_branch:
            subprocess.run(["git", "checkout", starting_branch], check=True)
    click.echo("PR created.")


if __name__ == "__main__":
    main()
