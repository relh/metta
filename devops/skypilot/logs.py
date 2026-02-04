#!/usr/bin/env -S uv run
"""CLI tool for viewing SkyPilot job logs.

Usage:
    logs.py <job_id>           # View last 100 lines of logs
    logs.py <job_id> -f        # Follow logs in real-time
    logs.py <job_id> -n 500    # View last 500 lines
    logs.py <job_id> --wandb   # Open W&B run page in browser
"""

import sys
import webbrowser
from typing import Annotated

import sky
import sky.jobs
import typer

from devops.skypilot.utils.job_helpers import skypilot_sanity_check, tail_job_log
from metta.common.util.constants import METTA_WANDB_ENTITY, METTA_WANDB_PROJECT
from metta.common.util.log_config import init_logging

app = typer.Typer(rich_markup_mode="rich")


def get_wandb_url_for_job(job_id: int) -> str | None:
    """Get the W&B URL for a job by looking up the job name (which is the run ID)."""
    job_records = sky.jobs.queue(refresh=False, all_users=True, job_ids=[job_id])
    if job_records:
        job_name = job_records[0].get("job_name")
        if job_name:
            # Job name is the run ID, which is also the W&B run name
            return f"https://wandb.ai/{METTA_WANDB_ENTITY}/{METTA_WANDB_PROJECT}/runs/{job_name}"
    return None


def follow_logs(job_id: int) -> None:
    """Follow logs for a running job using the SkyPilot SDK."""
    print(f"Following logs for job {job_id}... (Ctrl+C to stop)")
    sky.jobs.tail_logs(job_id=job_id, follow=True)


@app.command()
def main(
    job_id: Annotated[int, typer.Argument(help="The SkyPilot job ID to view logs for")],
    follow: Annotated[bool, typer.Option("-f", "--follow", help="Follow logs in real-time")] = False,
    lines: Annotated[int, typer.Option("-n", "--lines", help="Number of lines to show")] = 100,
    wandb: Annotated[bool, typer.Option("--wandb", help="Open W&B run page in browser")] = False,
    wandb_url: Annotated[bool, typer.Option("--wandb-url", help="Print W&B run URL")] = False,
):
    """
    View logs for a SkyPilot job.

    [bold green]Examples:[/bold green]

    [bold yellow]View last 100 lines:[/bold yellow]
    logs.py 123

    [bold yellow]Follow logs in real-time:[/bold yellow]
    logs.py 123 -f

    [bold yellow]View last 500 lines:[/bold yellow]
    logs.py 123 -n 500

    [bold yellow]Open W&B page in browser:[/bold yellow]
    logs.py 123 --wandb
    """
    skypilot_sanity_check()

    # Handle W&B URL options
    if wandb or wandb_url:
        url = get_wandb_url_for_job(job_id)
        if url:
            if wandb:
                print(f"Opening W&B run: {url}")
                webbrowser.open(url)
            else:
                print(url)
        else:
            print(f"Could not find W&B run for job {job_id}")
            sys.exit(1)
        return

    # Follow logs if requested
    if follow:
        follow_logs(job_id)
        return

    # Otherwise, get the tail of logs
    result = tail_job_log(str(job_id), lines=lines)
    if result:
        print(result)
    else:
        print(f"No logs available for job {job_id}")
        sys.exit(1)


if __name__ == "__main__":
    init_logging()
    app()
