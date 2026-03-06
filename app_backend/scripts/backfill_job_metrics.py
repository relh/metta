#!/usr/bin/env python
"""Backfill job cost and episode.length metrics from DB data.

Reads completed/failed jobs from the database and:
1. Fills in missing instance_type/capacity_type from stored k8s events
2. Recomputes cost_usd using accurate timestamps
3. Updates job_requests.result with corrected data
4. Submits historical episode.length and job.cost gauge points to Datadog

Requires:
- STATS_DB_URI env var (or standard app_backend config)
- Datadog API key (via AWS Secrets Manager or DD_API_KEY env)
- Historical Metrics Ingestion enabled in Datadog for:
    - job.cost.backfill (gauge)
    - episode.length.backfill (gauge)

Usage:
    uv run python app_backend/scripts/backfill_job_metrics.py --dry-run
    uv run python app_backend/scripts/backfill_job_metrics.py --since 2025-01-01
    uv run python app_backend/scripts/backfill_job_metrics.py --since 2025-01-01 --submit-dd
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import text
from sqlmodel import Session, col, create_engine, select

from devops.datadog.datadog_client import DatadogMetricsClient
from devops.datadog.models import MetricKind, MetricSample
from metta.app_backend.database import get_sync_db_url
from metta.app_backend.ec2_pricing import get_instance_hourly_cost
from metta.app_backend.job_runner.config import get_dispatch_config
from metta.app_backend.models.job_request import JobRequest, JobStatus
from metta.app_backend.otel.job_metrics import compute_job_cost

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BATCH_SIZE = 500
INSTANCE_TYPE_LABEL = "node.kubernetes.io/instance-type"
CAPACITY_TYPE_LABEL = "karpenter.sh/capacity-type"


def _get_events_for_job(session: Session, job_id: UUID) -> list[dict]:
    """Fetch k8s events for a job, most recent first."""
    rows = session.execute(
        text(
            "SELECT event FROM k8s_events "
            "WHERE event->'object'->'metadata'->'labels'->>'job-id' = :jid "
            "ORDER BY event_time DESC LIMIT 10"
        ),
        {"jid": str(job_id)},
    ).all()
    return [r[0] for r in rows]


def _extract_node_labels(events: list[dict]) -> dict[str, str]:
    for event_data in events:
        node_labels = event_data.get("node_labels") or {}
        if node_labels:
            result = {}
            if INSTANCE_TYPE_LABEL in node_labels:
                result["instance_type"] = node_labels[INSTANCE_TYPE_LABEL]
            if CAPACITY_TYPE_LABEL in node_labels:
                result["capacity_type"] = node_labels[CAPACITY_TYPE_LABEL]
            if result:
                return result

        pod_data = event_data.get("object", {})
        node_name = pod_data.get("spec", {}).get("nodeName")
        if not node_name:
            continue
        spec_labels = pod_data.get("spec", {}).get("nodeSelector", {})
        if INSTANCE_TYPE_LABEL in spec_labels:
            return {"instance_type": spec_labels[INSTANCE_TYPE_LABEL]}

    return {}


def _extract_finished_at(events: list[dict]) -> datetime | None:
    for event_data in events:
        pod_data = event_data.get("object", {})
        for cs in pod_data.get("status", {}).get("containerStatuses", []):
            finished = cs.get("state", {}).get("terminated", {}).get("finishedAt")
            if finished:
                if isinstance(finished, str):
                    return datetime.fromisoformat(finished.replace("Z", "+00:00"))
                if isinstance(finished, datetime):
                    return finished.replace(tzinfo=UTC) if finished.tzinfo is None else finished
    return None


def _extract_steps_from_episode(session: Session, episode_id: str) -> int | None:
    """Read steps from episodes.attributes."""
    row = session.execute(
        text("SELECT attributes->>'steps' FROM episodes WHERE id = :eid"),
        {"eid": episode_id},
    ).first()
    if row and row[0] is not None:
        val = int(row[0])
        return val if val > 0 else None
    return None


def backfill(
    since: datetime,
    dry_run: bool,
    submit_dd: bool,
) -> None:
    engine = create_engine(get_sync_db_url(), pool_size=2)
    region = get_dispatch_config().EVAL_CLUSTER_REGION

    dd_samples = []

    with Session(engine) as session:
        stmt = (
            select(JobRequest)
            .where(col(JobRequest.status).in_([JobStatus.completed, JobStatus.failed]))
            .where(col(JobRequest.completed_at) >= since)
            .where(col(JobRequest.dispatched_at).is_not(None))
            .order_by(col(JobRequest.completed_at).asc())
        )
        jobs = session.execute(stmt).scalars().all()
        logger.info("Found %d completed/failed jobs since %s", len(jobs), since.isoformat())

        updated = 0
        cost_filled = 0
        instance_filled = 0
        steps_found = 0

        for i, job in enumerate(jobs):
            result = dict(job.result or {})
            changed = False

            has_instance = "instance_type" in result
            has_capacity = "capacity_type" in result

            events = _get_events_for_job(session, job.id)

            if not has_instance or not has_capacity:
                labels = _extract_node_labels(events)
                if labels:
                    result.update(labels)
                    changed = True
                    has_instance = "instance_type" in result
                    instance_filled += 1

            instance_type = result.get("instance_type")
            capacity_type = result.get("capacity_type")

            if has_instance and instance_type:
                cost_start = job.dispatched_at or job.running_at
                cost_end = _extract_finished_at(events) or job.completed_at
                if cost_start and cost_end:
                    cost_per_pod_hour = get_instance_hourly_cost(instance_type, capacity_type, region=region)
                    cost = compute_job_cost(cost_start, cost_end, cost_per_pod_hour)
                    if cost is not None:
                        old_cost = result.get("cost_usd")
                        result["cost_usd"] = round(cost, 6)
                        if old_cost != result["cost_usd"]:
                            changed = True
                            cost_filled += 1

                        if submit_dd and job.completed_at:
                            dd_samples.append(
                                {
                                    "metric": "job.cost.backfill",
                                    "value": result["cost_usd"],
                                    "timestamp": job.completed_at,
                                    "tags": {
                                        "job_type": job.job_type.value,
                                        "outcome": job.status.value,
                                    },
                                }
                            )

            episode_id = result.get("episode_id")
            if episode_id and submit_dd and job.completed_at:
                steps = _extract_steps_from_episode(session, episode_id)
                if steps:
                    steps_found += 1
                    dd_samples.append(
                        {
                            "metric": "episode.length.backfill",
                            "value": float(steps),
                            "timestamp": job.completed_at,
                            "tags": {"job_type": job.job_type.value},
                        }
                    )

            if changed:
                if dry_run:
                    logger.info(
                        "[DRY RUN] Would update job %s: instance_type=%s cost_usd=%s",
                        job.id,
                        result.get("instance_type"),
                        result.get("cost_usd"),
                    )
                else:
                    session.execute(
                        text("UPDATE job_requests SET result = :result WHERE id = :jid"),
                        {"result": _json_dumps(result), "jid": str(job.id)},
                    )
                    updated += 1

            if (i + 1) % BATCH_SIZE == 0:
                if not dry_run:
                    session.commit()
                logger.info("Processed %d/%d jobs...", i + 1, len(jobs))

        if not dry_run:
            session.commit()

    logger.info(
        "Done. jobs=%d updated=%d instance_filled=%d cost_filled=%d steps_found=%d dd_samples=%d",
        len(jobs),
        updated,
        instance_filled,
        cost_filled,
        steps_found,
        len(dd_samples),
    )

    if submit_dd and dd_samples:
        _submit_to_datadog(dd_samples, dry_run)


def _json_dumps(obj: dict) -> str:
    return json.dumps(obj, default=str)


def _submit_to_datadog(samples: list[dict], dry_run: bool) -> None:
    dd_metrics = [
        MetricSample(
            name=s["metric"],
            value=s["value"],
            tags=s["tags"],
            kind=MetricKind.GAUGE,
            timestamp=s["timestamp"],
        )
        for s in samples
    ]

    logger.info("Submitting %d metric points to Datadog", len(dd_metrics))
    if dry_run:
        for m in dd_metrics[:10]:
            logger.info("[DRY RUN] %s=%s tags=%s ts=%s", m.name, m.value, m.tags, m.timestamp)
        if len(dd_metrics) > 10:
            logger.info("[DRY RUN] ... and %d more", len(dd_metrics) - 10)
        return

    client = DatadogMetricsClient()
    for i in range(0, len(dd_metrics), BATCH_SIZE):
        batch = dd_metrics[i : i + BATCH_SIZE]
        client.submit(batch)
        logger.info("Submitted batch %d-%d", i, i + len(batch))


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill job cost and episode metrics")
    parser.add_argument("--since", type=str, default="2025-01-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--dry-run", action="store_true", help="Log changes without writing")
    parser.add_argument("--submit-dd", action="store_true", help="Submit historical metrics to Datadog")
    args = parser.parse_args()

    since = datetime.fromisoformat(args.since).replace(tzinfo=UTC)
    backfill(since=since, dry_run=args.dry_run, submit_dd=args.submit_dd)


if __name__ == "__main__":
    main()
