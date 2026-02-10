"""Test that autogenerate produces no diffs against the Alembic baseline."""

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine
from sqlmodel import SQLModel

from metta.app_backend.models import (  # noqa: F401
    episodes,
    eval_task,
    job_request,
    k8s_events,
    policies,
    sweep,
    tournament,
)


def test_autogenerate_is_empty(db_context):
    """Verify ORM matches Alembic baseline — autogenerate should find no diffs."""
    engine = create_engine(db_context)
    with engine.connect() as conn:
        mc = MigrationContext.configure(conn)
        diffs = compare_metadata(mc, SQLModel.metadata)

    if diffs:
        diff_lines = "\n".join(f"  {d}" for d in diffs)
        raise AssertionError(f"Autogenerate found diffs (ORM != Alembic baseline):\n{diff_lines}")
