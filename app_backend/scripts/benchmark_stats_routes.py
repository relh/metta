#!/usr/bin/env -S uv run
# ruff: noqa: E402
# Imports must come after suppress_noisy_logs() call
"""
Benchmark script for app_backend stats routes.

Usage:
    cd app_backend
    uv run python scripts/benchmark_stats_routes.py

    # With custom settings:
    uv run python scripts/benchmark_stats_routes.py --policies 500 --versions-per-policy 5 --episodes 5000

This script:
1. Starts a temporary PostgreSQL container
2. Populates it with realistic fake data
3. Benchmarks each stats route with timing measurements
4. Reports results with statistical analysis
"""

import asyncio
import os
import random
import statistics
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Suppress noisy logs before other imports
from metta.common.util.log_config import suppress_noisy_logs

suppress_noisy_logs()

import typer
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from testcontainers.postgres import PostgresContainer

from metta.app_backend import config as app_config
from metta.app_backend import database
from metta.app_backend.auth import User
from metta.app_backend.database import db_session
from metta.app_backend.models.tournament import Pool, PoolPlayer, Season
from metta.app_backend.queries import episode_queries, policy_queries
from metta.app_backend.server import create_app
from metta.app_backend.test_support.client_adapter import get_user_headers

app = typer.Typer(
    help="Benchmark app_backend stats routes with realistic fake data",
    context_settings={"help_option_names": ["-h", "--help"]},
    no_args_is_help=False,
    pretty_exceptions_show_locals=False,
)


@dataclass
class BenchmarkResult:
    """Result of a benchmark run."""

    name: str
    times_ms: list[float]

    @property
    def mean(self) -> float:
        return statistics.mean(self.times_ms)

    @property
    def median(self) -> float:
        return statistics.median(self.times_ms)

    @property
    def stdev(self) -> float:
        return statistics.stdev(self.times_ms) if len(self.times_ms) > 1 else 0.0

    @property
    def min(self) -> float:
        return min(self.times_ms)

    @property
    def max(self) -> float:
        return max(self.times_ms)

    @property
    def p95(self) -> float:
        return statistics.quantiles(self.times_ms, n=20)[18] if len(self.times_ms) >= 20 else self.max

    @property
    def p99(self) -> float:
        return statistics.quantiles(self.times_ms, n=100)[98] if len(self.times_ms) >= 100 else self.max


def get_headers_for_user(user_id: str, is_softmax: bool = False) -> dict[str, str]:
    """Create auth headers for a test user."""
    user = User(id=user_id, email=f"{user_id}@example.com", is_softmax_team_member=is_softmax)
    return get_user_headers(user)


class DataGenerator:
    """Generates fake data for benchmarking."""

    def __init__(
        self,
        num_policies: int,
        num_versions_per_policy: int,
        num_users: int,
        num_seasons: int,
        num_pools_per_season: int,
        pool_membership_ratio: float,
        num_episodes: int,
    ):
        self.num_policies = num_policies
        self.num_versions_per_policy = num_versions_per_policy
        self.num_users = num_users
        self.num_seasons = num_seasons
        self.num_pools_per_season = num_pools_per_season
        self.pool_membership_ratio = pool_membership_ratio
        self.num_episodes = num_episodes

        self.users: list[str] = []
        self.policies: list[uuid.UUID] = []
        self.policy_versions: list[uuid.UUID] = []
        self.seasons: list[uuid.UUID] = []
        self.pools: list[uuid.UUID] = []

    async def generate_all(self):
        """Generate all fake data."""
        print("Generating fake data...")
        start = time.time()

        await self._generate_users()
        await self._generate_policies_and_versions()
        await self._generate_seasons_and_pools()
        await self._submit_to_pools()
        await self._generate_episodes()

        elapsed = time.time() - start
        print(f"Data generation complete in {elapsed:.1f}s")
        print(f"  - {len(self.users)} users")
        print(f"  - {len(self.policies)} policies")
        print(f"  - {len(self.policy_versions)} policy versions")
        print(f"  - {len(self.seasons)} seasons")
        print(f"  - {len(self.pools)} pools")

    async def _generate_users(self):
        """Generate user IDs."""
        self.users = [f"user-{i}@example.com" for i in range(self.num_users)]
        print(f"  Generated {self.num_users} user IDs")

    async def _generate_policies_and_versions(self):
        """Generate policies and their versions."""
        print(f"  Generating {self.num_policies} policies with {self.num_versions_per_policy} versions each...")

        for i in range(self.num_policies):
            user_id = random.choice(self.users)
            policy_name = f"policy-{i:04d}-{uuid.uuid4().hex[:8]}"

            policy_id = await policy_queries.upsert_policy(
                name=policy_name, user_id=user_id, attributes={"benchmark": True, "index": i}
            )
            self.policies.append(policy_id)

            for _ in range(self.num_versions_per_policy):
                pv_id = await policy_queries.create_policy_version(
                    policy_id=policy_id,
                    s3_path=f"s3://benchmark-bucket/policies/{policy_id}/{uuid.uuid4()}.zip",
                    git_hash=uuid.uuid4().hex[:7],
                    policy_spec={"type": "benchmark", "layers": [64, 64]},
                    attributes={"training_steps": random.randint(1000, 100000)},
                )
                self.policy_versions.append(pv_id)

            if (i + 1) % 100 == 0:
                print(f"    Created {i + 1}/{self.num_policies} policies...")

    async def _generate_seasons_and_pools(self):
        """Generate seasons and pools."""
        print(f"  Generating {self.num_seasons} seasons with {self.num_pools_per_season} pools each...")

        # Create a mix of public and hidden seasons
        season_names = ["beta-cvc", "beta-cogsguard", "production-v1", "test-season", "beta"]

        async with db_session() as session:
            for i, name in enumerate(season_names[: self.num_seasons]):
                season = Season(
                    name=name,
                    canonical=True,
                    description=f"Benchmark season {i}",  # non-hidden seasons
                )
                session.add(season)
                await session.flush()
                self.seasons.append(season.id)

                for j in range(self.num_pools_per_season):
                    pool = Pool(season_id=season.id, name=f"{name}-pool-{j}")
                    session.add(pool)
                    await session.flush()
                    self.pools.append(pool.id)

    async def _submit_to_pools(self):
        """Submit some policy versions to pools."""
        num_to_submit = int(len(self.policy_versions) * self.pool_membership_ratio)
        versions_to_submit = random.sample(self.policy_versions, num_to_submit)
        print(f"  Submitting {num_to_submit} policy versions to pools...")

        async with db_session() as session:
            for i, pv_id in enumerate(versions_to_submit):
                pool_id = random.choice(self.pools)
                pool_player = PoolPlayer(pool_id=pool_id, policy_version_id=pv_id)
                session.add(pool_player)

                if (i + 1) % 500 == 0:
                    await session.flush()
                    print(f"    Submitted {i + 1}/{num_to_submit} versions...")

            await session.flush()

    async def _generate_episodes(self):
        """Generate episodes with tags and metrics."""
        print(f"  Generating {self.num_episodes} episodes...")

        sim_names = ["arena-basic", "arena-advanced", "training-map", "eval-map"]
        job_ids = [uuid.uuid4() for _ in range(100)]  # Reuse job IDs

        for i in range(self.num_episodes):
            episode_id = uuid.uuid4()

            # Pick 2-4 random policy versions for this episode
            num_policies = random.randint(2, 4)
            episode_pvs = random.sample(self.policy_versions, min(num_policies, len(self.policy_versions)))

            policy_versions_list = [(pv_id, random.randint(1, 4)) for pv_id in episode_pvs]
            policy_metrics = [(pv_id, "reward", random.uniform(-10, 100)) for pv_id in episode_pvs]

            tags = [
                ("sim_name", random.choice(sim_names)),
                ("job_id", str(random.choice(job_ids))),
            ]

            await episode_queries.record_episode(
                id=episode_id,
                data_uri=f"s3://benchmark-bucket/episodes/{episode_id}.duckdb",
                replay_url=f"https://example.com/replays/{episode_id}",
                attributes={"benchmark": True, "index": i},
                eval_task_id=None,
                thumbnail_url=f"https://example.com/thumbnails/{episode_id}.png",
                tags=tags,
                policy_versions=policy_versions_list,
                policy_metrics=policy_metrics,
            )

            if (i + 1) % 1000 == 0:
                print(f"    Created {i + 1}/{self.num_episodes} episodes...")


class Benchmarker:
    """Runs benchmarks against stats routes."""

    def __init__(
        self,
        client: TestClient,
        data: DataGenerator,
        warmup_iterations: int,
        benchmark_iterations: int,
    ):
        self.client = client
        self.data = data
        self.warmup_iterations = warmup_iterations
        self.benchmark_iterations = benchmark_iterations
        self.results: list[BenchmarkResult] = []

        # Headers for different user types
        self.anon_headers: dict[str, str] = {}
        self.user_headers = get_headers_for_user(data.users[0], is_softmax=False)
        self.softmax_headers = get_headers_for_user("softmax@softmax.com", is_softmax=True)

    def run_all(self):
        """Run all benchmarks."""
        print("\nRunning benchmarks...")
        print(f"  Warmup iterations: {self.warmup_iterations}")
        print(f"  Benchmark iterations: {self.benchmark_iterations}")
        print()

        # GET /stats/policies
        self._benchmark(
            "GET /stats/policies (anon)",
            lambda: self.client.get("/stats/policies", headers=self.anon_headers),
        )
        self._benchmark(
            "GET /stats/policies (user)", lambda: self.client.get("/stats/policies", headers=self.user_headers)
        )
        self._benchmark(
            "GET /stats/policies (softmax)", lambda: self.client.get("/stats/policies", headers=self.softmax_headers)
        )

        # GET /stats/policies with fuzzy search
        self._benchmark(
            "GET /stats/policies?name_fuzzy=policy",
            lambda: self.client.get("/stats/policies", params={"name_fuzzy": "policy"}, headers=self.softmax_headers),
        )

        # GET /stats/policies with pagination
        self._benchmark(
            "GET /stats/policies?offset=500",
            lambda: self.client.get(
                "/stats/policies", params={"offset": 500, "limit": 50}, headers=self.softmax_headers
            ),
        )

        # GET /stats/policy-versions
        self._benchmark(
            "GET /stats/policy-versions (anon)",
            lambda: self.client.get("/stats/policy-versions", headers=self.anon_headers),
        )
        self._benchmark(
            "GET /stats/policy-versions (softmax)",
            lambda: self.client.get("/stats/policy-versions", headers=self.softmax_headers),
        )

        # GET /stats/policy-versions with mine=true
        self._benchmark(
            "GET /stats/policy-versions?mine=true",
            lambda: self.client.get("/stats/policy-versions", params={"mine": "true"}, headers=self.user_headers),
        )

        # GET /stats/policies/{pv_id} - single policy version lookup
        sample_pv_id = str(self.data.policy_versions[0])
        self._benchmark(
            "GET /stats/policies/{pv_id}",
            lambda: self.client.get(f"/stats/policies/{sample_pv_id}", headers=self.softmax_headers),
        )

        # GET /stats/policies/{policy_id}/versions
        sample_policy_id = str(self.data.policies[0])
        self._benchmark(
            "GET /stats/policies/{policy_id}/versions",
            lambda: self.client.get(f"/stats/policies/{sample_policy_id}/versions", headers=self.softmax_headers),
        )

        # GET /stats/policies/my-versions
        self._benchmark(
            "GET /stats/policies/my-versions",
            lambda: self.client.get("/stats/policies/my-versions", headers=self.user_headers),
        )

        # POST /stats/episodes/query - various queries
        sample_pv_ids = [str(pv) for pv in random.sample(self.data.policy_versions, 5)]
        self._benchmark(
            "POST /stats/episodes/query (by pv_ids)",
            lambda: self.client.post(
                "/stats/episodes/query",
                json={"primary_policy_version_ids": sample_pv_ids, "limit": 100},
                headers=self.softmax_headers,
            ),
        )

        self._benchmark(
            "POST /stats/episodes/query (by tag)",
            lambda: self.client.post(
                "/stats/episodes/query",
                json={"tag_filters": {"sim_name": ["arena-basic"]}, "limit": 100},
                headers=self.softmax_headers,
            ),
        )

        self._benchmark(
            "POST /stats/episodes/query (all, limit=200)",
            lambda: self.client.post(
                "/stats/episodes/query",
                json={"limit": 200},
                headers=self.softmax_headers,
            ),
        )

    def _benchmark(self, name: str, fn: Any):
        """Run a single benchmark."""
        print(f"  Benchmarking: {name}")

        # Warmup
        for _ in range(self.warmup_iterations):
            response = fn()
            if response.status_code >= 400:
                print(f"    WARNING: {name} returned status {response.status_code}")

        # Benchmark
        times_ms: list[float] = []
        for _ in range(self.benchmark_iterations):
            start = time.perf_counter()
            response = fn()
            elapsed_ms = (time.perf_counter() - start) * 1000
            times_ms.append(elapsed_ms)

            if response.status_code >= 400:
                print(f"    WARNING: {name} returned status {response.status_code}")

        result = BenchmarkResult(name=name, times_ms=times_ms)
        self.results.append(result)
        print(f"    Mean: {result.mean:.1f}ms, Median: {result.median:.1f}ms")

    def print_results(self):
        """Print benchmark results in a formatted table."""
        print("\n" + "=" * 100)
        print("Stats Routes Benchmark Results")
        print("=" * 100)
        num_versions = self.data.num_policies * self.data.num_versions_per_policy
        num_eps = self.data.num_episodes
        print(f"Database: {self.data.num_policies} policies, {num_versions} versions, {num_eps} episodes")
        print(f"Iterations: {self.benchmark_iterations} (after {self.warmup_iterations} warmup)")
        print()

        # Header
        header = f"{'Route':<50} | {'Mean':>8} | {'Median':>8} | {'Min':>8} | {'Max':>8} | {'Stdev':>8}"
        print(header)
        separator = "-" * 50 + "-+-" + "-" * 8 + "-+-" + "-" * 8 + "-+-" + "-" * 8 + "-+-" + "-" * 8 + "-+-" + "-" * 8
        print(separator)

        # Results
        for r in self.results:
            row = (
                f"{r.name:<50} | {r.mean:>7.1f}ms | {r.median:>7.1f}ms | "
                f"{r.min:>7.1f}ms | {r.max:>7.1f}ms | {r.stdev:>7.1f}ms"
            )
            print(row)

        print("=" * 100)


def setup_database(db_uri: str):
    """Configure database connection and run migrations."""
    database._engine = None
    database._session_factory = None
    app_config.settings.STATS_DB_URI = db_uri
    app_config.settings.RUN_MIGRATIONS = True
    app_config.settings.OBSERVATORY_AUTH_SECRET = "benchmark_secret"

    alembic_cfg = Config(str(Path(__file__).parent.parent / "alembic.ini"))
    command.upgrade(alembic_cfg, "head")


@app.command()
def main(
    # Data generation options
    policies: int = typer.Option(
        1000,
        "--policies",
        "-p",
        help="Number of policies to create",
        min=1,
    ),
    versions_per_policy: int = typer.Option(
        10,
        "--versions-per-policy",
        "-v",
        help="Number of versions per policy",
        min=1,
    ),
    users: int = typer.Option(
        100,
        "--users",
        "-u",
        help="Number of users to distribute policies across",
        min=1,
    ),
    seasons: int = typer.Option(
        5,
        "--seasons",
        help="Number of seasons to create",
        min=1,
        max=5,
    ),
    pools_per_season: int = typer.Option(
        10,
        "--pools-per-season",
        help="Number of pools per season",
        min=1,
    ),
    pool_membership_ratio: float = typer.Option(
        0.3,
        "--pool-membership-ratio",
        help="Fraction of policy versions submitted to pools (0.0-1.0)",
        min=0.0,
        max=1.0,
    ),
    episodes: int = typer.Option(
        10000,
        "--episodes",
        "-e",
        help="Number of episodes to create",
        min=1,
    ),
    # Benchmark options
    warmup: int = typer.Option(
        3,
        "--warmup",
        "-w",
        help="Number of warmup iterations before benchmarking",
        min=0,
    ),
    iterations: int = typer.Option(
        10,
        "--iterations",
        "-i",
        help="Number of benchmark iterations per route",
        min=1,
    ),
):
    """
    Benchmark app_backend stats routes.

    Starts a temporary PostgreSQL container, populates it with fake data,
    and measures the performance of each stats route.
    """
    print("Stats Routes Benchmark")
    print("=" * 50)

    # Set fake AWS credentials for presigned URL generation
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
    os.environ["EVAL_S3_BUCKET"] = "test-bucket"

    print("\nStarting PostgreSQL container...")
    try:
        container = PostgresContainer(
            image="postgres:17",
            username="benchmark_user",
            password="benchmark_password",
            dbname="benchmark_db",
            driver=None,
        )
        container.start()
    except Exception as e:
        print(f"ERROR: Failed to start PostgreSQL container: {e}")
        print("Make sure Docker is running.")
        sys.exit(1)

    try:
        db_uri = container.get_connection_url()
        print(f"Database URI: {db_uri}")

        print("\nSetting up database and running migrations...")
        setup_database(db_uri)

        print("\nCreating FastAPI app...")
        fastapi_app = create_app()
        client = TestClient(fastapi_app)

        # Generate data
        data_generator = DataGenerator(
            num_policies=policies,
            num_versions_per_policy=versions_per_policy,
            num_users=users,
            num_seasons=seasons,
            num_pools_per_season=pools_per_season,
            pool_membership_ratio=pool_membership_ratio,
            num_episodes=episodes,
        )
        asyncio.run(data_generator.generate_all())

        # Run benchmarks
        benchmarker = Benchmarker(
            client,
            data_generator,
            warmup_iterations=warmup,
            benchmark_iterations=iterations,
        )
        benchmarker.run_all()
        benchmarker.print_results()

    finally:
        print("\nStopping PostgreSQL container...")
        container.stop()

    print("\nBenchmark complete!")


if __name__ == "__main__":
    app()
