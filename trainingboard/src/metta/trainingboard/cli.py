from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import click

from metta.trainingboard.ingest.asana import (
    default_raw_cache_path,
    parse_project_and_section_from_url,
    sync_project_research,
)
from metta.trainingboard.local.backend.server import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    DEFAULT_STATE_DIR,
    build_dashboard_for_state_dir,
    cache_path_for_state_dir,
    run_server,
)


@click.group()
def main() -> None:
    """Trainingboard CLI."""


@main.command()
@click.option("--host", default=DEFAULT_HOST)
@click.option("--port", type=int, default=DEFAULT_PORT)
@click.option("--state-dir", default=str(DEFAULT_STATE_DIR))
def serve(host: str, port: int, state_dir: str) -> None:
    """Run local six-panel dashboard server."""
    run_server(SimpleNamespace(host=host, port=port, state_dir=state_dir))


@main.command(name="ingest-asana")
@click.option("--project-gid", default="")
@click.option("--section-gid", default="")
@click.option("--source-url", default="", help="Asana list URL: /project/<project_gid>/list/<section_gid>")
@click.option("--token", default="", help="Asana access token (defaults to env).")
@click.option("--token-env", default="ASANA_TOKEN", help="Environment variable containing Asana token.")
@click.option("--output", default="", help="Output cache file path.")
@click.option("--raw-cache", default="", help="Raw per-task Asana cache path.")
@click.option("--include-completed/--no-include-completed", default=True)
@click.option("--merge-output/--overwrite-output", default=True)
@click.option("--story-workers", default=12, type=int, show_default=True)
@click.option("--state-dir", default=str(DEFAULT_STATE_DIR))
def ingest_asana(
    project_gid: str,
    section_gid: str,
    source_url: str,
    token: str,
    token_env: str,
    output: str,
    raw_cache: str,
    include_completed: bool,
    merge_output: bool,
    story_workers: int,
    state_dir: str,
) -> None:
    """Ingest an Asana project into local research cache."""
    access_token = token or (os.environ[token_env] if token_env in os.environ else "")
    if not access_token:
        raise click.ClickException(f"Missing Asana token. Set --token or ${token_env}.")

    if source_url:
        project_gid, section_gid = parse_project_and_section_from_url(source_url)
    if not project_gid:
        raise click.ClickException("Missing Asana source. Set --project-gid or --source-url.")
    section_gid = section_gid.strip() or None

    resolved_state_dir = Path(state_dir).expanduser()
    output_path = Path(output).expanduser() if output else cache_path_for_state_dir(resolved_state_dir)
    raw_cache_path = (
        Path(raw_cache).expanduser()
        if raw_cache
        else default_raw_cache_path(resolved_state_dir, project_gid=project_gid, section_gid=section_gid)
    )
    _, summary = sync_project_research(
        project_gid=project_gid,
        token=access_token,
        raw_cache_path=raw_cache_path,
        output_path=output_path,
        section_gid=section_gid,
        include_completed=include_completed,
        merge_output=merge_output,
        story_worker_count=max(1, story_workers),
    )

    click.echo(f"Source {summary.source_key}")
    if summary.used_project_fallback:
        click.echo("Section list returned no tasks; fell back to full project sync.")
    click.echo(f"Output records total={summary.output_records_total}")
    click.echo(f"Ingested source records={summary.records_written}")
    click.echo(
        "Story cache: "
        f"reused={summary.story_reuse_count} "
        f"refetched={summary.story_refetch_count} "
        f"tasks={summary.tasks_total}"
    )
    click.echo(
        f"Extracted evidence: paper_links={summary.paper_link_count} recommendations={summary.recommendation_count}"
    )
    click.echo(f"Wrote raw cache: {raw_cache_path}")
    click.echo(f"Wrote cache: {output_path}")


@main.command()
@click.option("--state-dir", default=str(DEFAULT_STATE_DIR))
def snapshot(state_dir: str) -> None:
    """Print current dashboard snapshot JSON."""
    payload = build_dashboard_for_state_dir(Path(state_dir).expanduser())
    click.echo(json.dumps(payload, indent=2))
