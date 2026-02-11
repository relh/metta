"""add user_settings table

Revision ID: a311d3c654c8
Revises: 7720c3b9167b
Create Date: 2026-02-10 15:16:50.908448

"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a311d3c654c8"
down_revision: Union[str, Sequence[str], None] = "7720c3b9167b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "user_settings",
        sa.Column("user_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "settings",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("user_id"),
    )
    # Drop legacy migration tracking table (only exists on DBs created by the old system)
    op.execute(sa.text("DROP TABLE IF EXISTS migrations"))


def downgrade() -> None:
    """Downgrade schema.

    NOTE: The legacy migrations table is recreated empty. Historical migration
    rows are intentionally lost — the old hand-rolled migration system is deleted
    and downgrading past this point is not supported.
    """
    op.create_table(
        "migrations",
        sa.Column("version", sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column("description", sa.TEXT(), autoincrement=False, nullable=False),
        sa.Column(
            "applied_at",
            postgresql.TIMESTAMP(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            autoincrement=False,
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("version", name=op.f("migrations_pkey")),
    )
    op.drop_table("user_settings")
