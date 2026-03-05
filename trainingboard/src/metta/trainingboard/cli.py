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
from metta.trainingboard.llm_scoring import (
    DEFAULT_OPENAI_MODEL,
    load_llm_score_cache,
    resolve_openai_api_key,
    score_tasks_with_openai,
)
from metta.trainingboard.local.backend.server import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    DEFAULT_STATE_DIR,
    build_dashboard_for_state_dir,
    cache_path_for_state_dir,
    dashboard_cache_path_for_state_dir,
    default_repo_cache_path,
    run_server,
    task_ranking_llm_cache_path_for_state_dir,
)
from metta.trainingboard.scoring import build_task_ranking_snapshot, load_cached_papers


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
@click.option(
    "--repo-output/--no-repo-output",
    default=True,
    help="When --output is unset, write normalized cache to trainingboard/data/asana_research_cache.ndjson.",
)
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
    repo_output: bool,
    raw_cache: str,
    include_completed: bool,
    merge_output: bool,
    story_workers: int,
    state_dir: str,
) -> None:
    """Ingest an Asana project into local research cache."""
    access_token = token or os.environ.get(token_env, "")
    if not access_token:
        raise click.ClickException(f"Missing Asana token. Set --token or ${token_env}.")

    if source_url:
        project_gid, section_gid = parse_project_and_section_from_url(source_url)
    if not project_gid:
        raise click.ClickException("Missing Asana source. Set --project-gid or --source-url.")
    section_gid = section_gid.strip() or None

    resolved_state_dir = Path(state_dir).expanduser()
    if output:
        output_path = Path(output).expanduser()
    elif repo_output:
        output_path = default_repo_cache_path(resolved_state_dir)
    else:
        output_path = cache_path_for_state_dir(resolved_state_dir)
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


@main.command(name="rank-tasks")
@click.option("--state-dir", default=str(DEFAULT_STATE_DIR))
@click.option("--limit", type=int, default=50, show_default=True)
@click.option("--llm/--no-llm", default=False, show_default=True)
@click.option("--llm-model", default=DEFAULT_OPENAI_MODEL, show_default=True)
@click.option("--llm-api-key", default="", help="OpenAI API key value.")
@click.option("--llm-api-key-env", default="OPENAI_API_KEY", show_default=True)
@click.option("--llm-cache", default="", help="Path to LLM score cache NDJSON.")
@click.option("--llm-task-limit", type=int, default=0, show_default=True)
@click.option("--llm-task-offset", type=int, default=0, show_default=True)
@click.option("--llm-force-refresh/--no-llm-force-refresh", default=False, show_default=True)
def rank_tasks(
    state_dir: str,
    limit: int,
    llm: bool,
    llm_model: str,
    llm_api_key: str,
    llm_api_key_env: str,
    llm_cache: str,
    llm_task_limit: int,
    llm_task_offset: int,
    llm_force_refresh: bool,
) -> None:
    """Print ranked tasks with 12-metric scoring."""
    if limit < 0:
        raise click.ClickException("--limit must be non-negative.")
    if llm_task_limit < 0:
        raise click.ClickException("--llm-task-limit must be non-negative.")
    if llm_task_offset < 0:
        raise click.ClickException("--llm-task-offset must be non-negative.")

    resolved_state_dir = Path(state_dir).expanduser()
    task_cache_path = dashboard_cache_path_for_state_dir(resolved_state_dir)
    papers = load_cached_papers(task_cache_path)
    llm_cache_path = (
        Path(llm_cache).expanduser() if llm_cache else task_ranking_llm_cache_path_for_state_dir(resolved_state_dir)
    )
    llm_summary_payload = None
    if llm:
        resolved_api_key = resolve_openai_api_key(explicit_key=llm_api_key, token_env=llm_api_key_env)
        if not resolved_api_key:
            raise click.ClickException(f"Missing OpenAI API key. Set --llm-api-key or ${llm_api_key_env}.")
        task_limit_for_llm = None if llm_task_limit == 0 else llm_task_limit
        _, llm_summary = score_tasks_with_openai(
            papers,
            model=llm_model,
            api_key=resolved_api_key,
            cache_path=llm_cache_path,
            task_limit=task_limit_for_llm,
            task_offset=llm_task_offset,
            force_refresh=llm_force_refresh,
        )
        llm_summary_payload = llm_summary.model_dump()

    llm_scores_by_gid = {gid: entry.scores for gid, entry in load_llm_score_cache(llm_cache_path).items()}
    payload = build_task_ranking_snapshot(
        papers,
        limit=limit,
        llm_scores_by_gid=llm_scores_by_gid,
        require_llm_scores=True,
    ).model_dump()
    payload["llm_cache_path"] = str(llm_cache_path)
    payload["llm_scores_loaded"] = len(llm_scores_by_gid)
    if llm_summary_payload is not None:
        payload["llm_summary"] = llm_summary_payload
    click.echo(json.dumps(payload, indent=2))
