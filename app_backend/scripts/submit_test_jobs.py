#!/usr/bin/env python
import argparse

from metta.app_backend.clients.stats_client import StatsClient
from metta.app_backend.models.job_request import JobRequestCreate, JobType
from metta.app_backend.tournament.referees.envs import make_cogsguard_env
from metta.common.util.constants import DEV_STATS_SERVER_URI, PROD_STATS_SERVER_URI
from mettagrid.runner.types import SingleEpisodeJob

SERVERS = {
    "dev": DEV_STATS_SERVER_URI,
    "prod": PROD_STATS_SERVER_URI,
}


def main():
    parser = argparse.ArgumentParser(description="Submit test episode jobs")
    parser.add_argument("--server", choices=["dev", "prod"], default="prod", help="Target environment")
    parser.add_argument("--num-agents", type=int, default=2, help="Number of agents")
    parser.add_argument("--num-jobs", type=int, default=1, help="Number of jobs to submit")
    parser.add_argument("--policy-uri", help="Policy URI")
    args = parser.parse_args()

    if not args.policy_uri:
        raise ValueError("Policy URI is required")

    server_url = SERVERS[args.server]

    policy_uris = [args.policy_uri]

    jobs = []
    for seed in range(args.num_jobs):
        env = make_cogsguard_env(seed=seed, num_agents=args.num_agents)
        job = SingleEpisodeJob(
            policy_uris=policy_uris,
            assignments=[i % len(policy_uris) for i in range(args.num_agents)],
            env=env,
            seed=seed,
            episode_tags={"source": "submit_test_jobs"},
        )
        jobs.append(
            JobRequestCreate(
                job_type=JobType.episode,
                job=job.model_dump(),
            )
        )

    stats_client = StatsClient(server_url)
    try:
        job_ids = stats_client.create_jobs(jobs)
        print(f"Created {len(job_ids)} job(s):")
        for job_id in job_ids:
            print(f"  {job_id}")
    finally:
        stats_client.close()


if __name__ == "__main__":
    main()
