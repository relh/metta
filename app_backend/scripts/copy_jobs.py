#!/usr/bin/env python
import argparse
import uuid

from metta.app_backend.clients.stats_client import StatsClient
from metta.app_backend.models.job_request import JobRequestCreate, JobType
from metta.common.util.constants import DEV_STATS_SERVER_URI, PROD_STATS_SERVER_URI

SERVERS = {
    "dev": DEV_STATS_SERVER_URI,
    "prod": PROD_STATS_SERVER_URI,
}


def copy_jobs(stats_client: StatsClient, job_ids: list[uuid.UUID]) -> list[uuid.UUID]:
    new_jobs = []
    for job_id in job_ids:
        existing = stats_client.get_job(job_id)
        job_data = dict(existing.job)
        job_data["episode_tags"] = {
            "source": "copy-job-script",
            **{k: v for k, v in job_data.get("episode_tags", {}).items() if k in ("game",)},
        }
        new_jobs.append(
            JobRequestCreate(
                job_type=JobType.episode,
                job=job_data,
            )
        )
    return stats_client.create_jobs(new_jobs)


def main() -> None:
    parser = argparse.ArgumentParser(description="Copy existing episode jobs")
    parser.add_argument("--server", choices=["dev", "prod"], default="prod", help="Target environment")
    parser.add_argument("job_ids", nargs="+", type=uuid.UUID, help="Job IDs to copy")
    args = parser.parse_args()

    stats_client = StatsClient(SERVERS[args.server])
    try:
        new_ids = copy_jobs(stats_client, args.job_ids)
        print(f"Created {len(new_ids)} job(s):")
        for new_id in new_ids:
            print(f"  {new_id}")
    finally:
        stats_client.close()


if __name__ == "__main__":
    main()
