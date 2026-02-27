"""Add season public field

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-02-27 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f7a8b9c0d1e2"
down_revision: Union[str, Sequence[str], None] = "e6f7a8b9c0d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PRIVATE_SEASONS = ("test-season", "beta")


def upgrade() -> None:
    op.add_column("seasons", sa.Column("public", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.execute(
        sa.text("UPDATE seasons SET public = true WHERE name NOT IN :names").bindparams(
            sa.bindparam("names", value=PRIVATE_SEASONS, expanding=True)
        )
    )


def downgrade() -> None:
    op.drop_column("seasons", "public")
