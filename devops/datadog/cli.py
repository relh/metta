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
    from devops.datadog.monitors import get_all_monitor_configs
    from devops.datadog.monitors_client import DatadogMonitorsClient

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
    from devops.datadog.monitors_client import DatadogMonitorsClient

    client = DatadogMonitorsClient()
    monitors = client.list_monitors(name_filter=name_filter)

    if managed_only:
        monitors = [m for m in monitors if "managed-by:code" in m.get("tags", [])]

    typer.echo(f"Found {len(monitors)} monitors:\n")
    for m in monitors:
        typer.echo(f"  [{m['id']}] {m['name']}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
