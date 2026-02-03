"""CLI for Datadog CI metrics collector and monitor management."""

from __future__ import annotations

import json
import shutil
import subprocess
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
    from devops.datadog.dashboards_client import DatadogDashboardsClient  # noqa: PLC0415

    client = DatadogDashboardsClient()
    dashboards = client.list_dashboards()

    if title_filter:
        dashboards = [d for d in dashboards if title_filter.lower() in d.get("title", "").lower()]

    if managed_only:
        dashboards = [d for d in dashboards if "managed-by:code" in d.get("tags", [])]

    typer.echo(f"Found {len(dashboards)} dashboards:\n")
    for d in dashboards:
        typer.echo(f"  [{d['id']}] {d['title']}")


CACHE_DIR = Path.home() / ".metta"
CACHE_FILE = CACHE_DIR / "dd_api_key"


def _check_jq() -> bool:
    if shutil.which("jq"):
        return True
    typer.echo("jq is not installed. Install it:")
    typer.echo("  macOS:  brew install jq")
    typer.echo("  Linux:  sudo apt-get install jq")
    return False


def _get_cached_api_key() -> str | None:
    if CACHE_FILE.exists():
        return CACHE_FILE.read_text().strip() or None
    return None


def _cache_api_key(key: str) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(key)
    CACHE_FILE.chmod(0o600)


def _fetch_api_key_from_aws() -> str | None:
    if not shutil.which("aws"):
        return None
    try:
        result = subprocess.run(
            [
                "aws",
                "secretsmanager",
                "get-secret-value",
                "--secret-id",
                "datadog/api-key",
                "--query",
                "SecretString",
                "--output",
                "text",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip() or None
    except subprocess.CalledProcessError:
        return None


@app.command()
def setup(
    force: bool = typer.Option(False, "--force", help="Overwrite existing cached API key."),
) -> None:
    """Set up skills usage tracking (jq + Datadog API key)."""
    ok = True

    typer.echo("Checking prerequisites...\n")

    if _check_jq():
        typer.echo("  jq: OK")
    else:
        ok = False

    existing_key = _get_cached_api_key()
    if existing_key and not force:
        typer.echo(f"  DD API key: cached at {CACHE_FILE}")
    else:
        typer.echo("  DD API key: fetching...")
        api_key = _fetch_api_key_from_aws()
        if api_key:
            _cache_api_key(api_key)
            typer.echo(f"  DD API key: cached from AWS at {CACHE_FILE}")
        else:
            typer.echo("  Could not fetch from AWS. Enter your Datadog API key:")
            api_key = typer.prompt("  API key", hide_input=True)
            if not api_key:
                typer.echo("  No key provided.")
                ok = False
            else:
                _cache_api_key(api_key)
                typer.echo(f"  DD API key: cached at {CACHE_FILE}")

    if ok:
        typer.echo("\nSkills tracking is ready.")
    else:
        typer.echo("\nSetup incomplete -- fix the issues above and re-run.")
        raise typer.Exit(1)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
