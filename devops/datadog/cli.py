"""CLI for Datadog CI metrics collector and monitor management."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from devops.datadog.collectors.ci_collector import CICollector
from devops.datadog.datadog_client import DatadogMetricsClient
from devops.datadog.models import MetricSample

app = typer.Typer(
    help="Datadog CLI for metrics collection and monitor management",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

monitors_app = typer.Typer(
    help="Manage Datadog monitors as code",
    no_args_is_help=True,
)
app.add_typer(monitors_app, name="monitors")

dashboards_app = typer.Typer(
    help="Manage Datadog dashboards as code",
    no_args_is_help=True,
)
app.add_typer(dashboards_app, name="dashboards")


@app.command()
def collect(
    push: bool = typer.Option(
        False,
        "--push",
        help="Submit collected metrics to Datadog.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Print metrics instead of pushing to Datadog.",
    ),
    output: Path | None = typer.Option(  # noqa: B008
        None,
        "--output",
        "-o",
        help="Optional path to write JSON payload (useful for debugging).",
    ),
) -> None:
    """Collect CI metrics and optionally push to Datadog."""
    if push and dry_run:
        typer.echo("Error: --push and --dry-run are mutually exclusive")
        raise typer.Exit(1)

    collector = CICollector()
    samples = collector.collect()
    _handle_samples(samples, dry_run=dry_run, output=output)
    if push:
        DatadogMetricsClient().submit(samples)
        typer.echo("Metrics submitted to Datadog")


def _handle_samples(samples: list[MetricSample], *, dry_run: bool, output: Path | None) -> None:
    payload = [sample.to_dict() for sample in samples]
    if dry_run or not samples:
        typer.echo(json.dumps(payload, indent=2))
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, indent=2))
        typer.echo(f"Wrote payload to {output}")


@monitors_app.command("sync")
def monitors_sync(
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Print monitor configs without syncing to Datadog.",
    ),
) -> None:
    """Sync monitor definitions to Datadog.

    Creates new monitors or updates existing ones to match the definitions in code.
    Monitors are matched by name.
    """
    from devops.datadog.monitors import get_all_monitor_configs  # noqa: PLC0415
    from devops.datadog.monitors_client import DatadogMonitorsClient  # noqa: PLC0415

    configs = get_all_monitor_configs()

    if dry_run:
        typer.echo(f"Would sync {len(configs)} monitors:\n")
        typer.echo(json.dumps(configs, indent=2))
        return

    client = DatadogMonitorsClient()
    for config in configs:
        result = client.sync_monitor(config)
        typer.echo(f"Synced: {result['name']} (id={result['id']})")

    typer.echo(f"\nSynced {len(configs)} monitors to Datadog")


@monitors_app.command("list")
def monitors_list(
    name_filter: str | None = typer.Option(
        None,
        "--name",
        "-n",
        help="Filter monitors by name (substring match).",
    ),
    managed_only: bool = typer.Option(
        False,
        "--managed",
        help="Only show monitors managed by code (tagged 'managed-by:code').",
    ),
) -> None:
    """List monitors from Datadog."""
    from devops.datadog.monitors_client import DatadogMonitorsClient  # noqa: PLC0415

    client = DatadogMonitorsClient()
    monitors = client.list_monitors(name_filter=name_filter)

    if managed_only:
        monitors = [m for m in monitors if "managed-by:code" in m.get("tags", [])]

    typer.echo(f"Found {len(monitors)} monitors:\n")
    for m in monitors:
        typer.echo(f"  [{m['id']}] {m['name']}")


@dashboards_app.command("sync")
def dashboards_sync(
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Print dashboard configs without syncing to Datadog.",
    ),
) -> None:
    """Sync dashboard definitions to Datadog."""
    from devops.datadog.dashboards import get_all_dashboard_configs  # noqa: PLC0415
    from devops.datadog.dashboards_client import DatadogDashboardsClient  # noqa: PLC0415

    configs = get_all_dashboard_configs()

    if dry_run:
        typer.echo(f"Would sync {len(configs)} dashboards:\n")
        typer.echo(json.dumps(configs, indent=2))
        return

    client = DatadogDashboardsClient()
    for config in configs:
        result = client.sync_dashboard(config)
        typer.echo(f"Synced: {result['title']} (id={result['id']})")

    typer.echo(f"\nSynced {len(configs)} dashboards to Datadog")


@dashboards_app.command("list")
def dashboards_list(
    title_filter: str | None = typer.Option(
        None,
        "--title",
        "-t",
        help="Filter dashboards by title (substring match).",
    ),
    managed_only: bool = typer.Option(
        False,
        "--managed",
        help="Only show dashboards managed by code (tagged 'managed-by:code').",
    ),
) -> None:
    """List dashboards from Datadog."""
    from devops.datadog.dashboards import get_all_dashboard_configs  # noqa: PLC0415
    from devops.datadog.dashboards_client import DatadogDashboardsClient  # noqa: PLC0415

    client = DatadogDashboardsClient()
    dashboards = client.list_dashboards()

    if title_filter:
        dashboards = [d for d in dashboards if title_filter.lower() in d.get("title", "").lower()]

    if managed_only:
        managed_titles = {config["title"] for config in get_all_dashboard_configs()}
        dashboards = [d for d in dashboards if d.get("title") in managed_titles]

    typer.echo(f"Found {len(dashboards)} dashboards:\n")
    for d in dashboards:
        typer.echo(f"  [{d['id']}] {d['title']}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
