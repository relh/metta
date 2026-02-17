# ruff: noqa: E402
# need this to import and call suppress_noisy_logs first
from metta.common.util.log_config import suppress_noisy_logs

suppress_noisy_logs()
import uuid
from collections.abc import Iterator
from unittest.mock import MagicMock

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg import sql
from testcontainers.postgres import PostgresContainer

from metta.app_backend import config as app_config
from metta.app_backend.clients.stats_client import StatsClient
from metta.app_backend.database import run_alembic_upgrade
from metta.app_backend.server import create_app
from metta.app_backend.test_support.client_adapter import (
    create_test_stats_client,
    get_fake_softmax_user,
    get_user_headers,
)
from metta.common.tests_support import docker_client_fixture

# Register the docker_client fixture
docker_client = docker_client_fixture()


def pytest_configure(config: pytest.Config):
    """Configure test settings before any tests run (works with xdist workers)."""
    app_config.settings.RUN_MIGRATIONS = True
    app_config.settings.OBSERVATORY_AUTH_SECRET = "test_secret"


@pytest.fixture(scope="session")
def postgres_container():
    """Create a PostgreSQL container for testing (session-scoped for performance)."""
    container = PostgresContainer(
        image="postgres:17",
        username="test_user",
        password="test_password",
        dbname="test_db",
        driver=None,
    )
    container.start()
    yield container
    container.stop()


TEMPLATE_DB_NAME = "test_template"


@pytest.fixture(scope="session")
def template_db_uri(postgres_container: PostgresContainer) -> str:
    """Create a template database with Alembic migrations pre-applied.

    This runs once per session. Individual tests clone from this template,
    which is much faster than running migrations for each test.
    """
    db_uri = postgres_container.get_connection_url()

    # Create the template database
    with psycopg.connect(db_uri, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(TEMPLATE_DB_NAME)))
            cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(TEMPLATE_DB_NAME)))

    # Run Alembic migrations on template
    template_uri = db_uri.replace("/test_db", f"/{TEMPLATE_DB_NAME}")
    app_config.settings.STATS_DB_URI = template_uri
    run_alembic_upgrade()

    return db_uri  # Return base URI for cloning operations


def clone_template_database(base_uri: str) -> tuple[str, str]:
    """Clone the template database for an isolated test.

    Returns (cloned_db_uri, db_name) tuple.
    """
    db_name = f"test_{uuid.uuid4().hex[:8]}"

    with psycopg.connect(base_uri, autocommit=True) as conn:
        with conn.cursor() as cur:
            # Must disconnect all connections from template before cloning
            cur.execute(
                sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(
                    sql.Identifier(db_name), sql.Identifier(TEMPLATE_DB_NAME)
                )
            )

    cloned_uri = base_uri.replace("/test_db", f"/{db_name}")
    return cloned_uri, db_name


def drop_database(base_uri: str, db_name: str) -> None:
    """Drop a database (used for cleanup)."""
    with psycopg.connect(base_uri, autocommit=True) as conn:
        with conn.cursor() as cur:
            # Terminate any connections to the database first
            cur.execute(
                sql.SQL("""
                    SELECT pg_terminate_backend(pg_stat_activity.pid)
                    FROM pg_stat_activity
                    WHERE pg_stat_activity.datname = %s
                    AND pid <> pg_backend_pid()
                """),
                [db_name],
            )
            cur.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(db_name)))


@pytest.fixture
def softmax_headers() -> dict[str, str]:
    """Authentication headers for a softmax team member."""
    return get_user_headers(get_fake_softmax_user())


@pytest.fixture
def regular_headers() -> dict[str, str]:
    """Authentication headers for a regular (non-softmax) user."""
    from metta.app_backend.auth import User  # noqa: PLC0415

    return get_user_headers(User(id="regular@example.com", email="regular@example.com", is_softmax_team_member=False))


@pytest.fixture(autouse=True)
def fake_aws_credentials(monkeypatch: pytest.MonkeyPatch):
    """Set fake AWS credentials for boto3 (required for presigned URL generation)."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("EVAL_S3_BUCKET", "test-bucket")
    from metta.app_backend.job_runner.config import get_dispatch_config  # noqa: PLC0415

    get_dispatch_config.cache_clear()


@pytest.fixture(autouse=True)
def mock_k8s_client(monkeypatch: pytest.MonkeyPatch):
    """Prevent any accidental k8s API calls in tests."""
    from metta.app_backend.job_runner import dispatcher  # noqa: PLC0415

    mock_client = MagicMock()
    monkeypatch.setattr(dispatcher, "get_k8s_client", lambda: mock_client)
    yield mock_client


@pytest.fixture(autouse=True)
def mock_dispatch_job(monkeypatch: pytest.MonkeyPatch):
    def stub_dispatch(job, policy_s3_keys: dict | None = None):
        return f"mock-k8s-job-{job.id.hex[:8]}"

    monkeypatch.setattr("metta.app_backend.routes.job_routes.dispatch_job", stub_dispatch)


# Function-scoped fixtures using template database cloning for test isolation
@pytest.fixture
def db_context(template_db_uri: str) -> Iterator[str]:
    """Create an isolated database by cloning the template.

    This is much faster than creating a schema and running migrations,
    since PostgreSQL just copies the template's data files.
    """
    cloned_uri, db_name = clone_template_database(template_db_uri)
    yield cloned_uri
    # Cleanup: drop the cloned database
    drop_database(template_db_uri, db_name)


@pytest.fixture
def stats_repo(db_context: str) -> str:
    """Function-scoped stats repo with isolated database."""
    from metta.app_backend import database  # noqa: PLC0415

    database._engine = None
    database._session_factory = None
    app_config.settings.STATS_DB_URI = db_context

    # No need to run migrations - template already has them!
    return db_context


@pytest.fixture
def test_app(stats_repo: str) -> FastAPI:
    """Create a FastAPI app with isolated database."""
    _ = stats_repo
    return create_app()


@pytest.fixture
def test_client(test_app: FastAPI) -> TestClient:
    """Create a test client with isolated database."""
    return TestClient(test_app)


@pytest.fixture
def stats_client(test_client: TestClient) -> StatsClient:
    """Create a stats client with isolated database for testing."""
    return create_test_stats_client(test_client, user=get_fake_softmax_user())
