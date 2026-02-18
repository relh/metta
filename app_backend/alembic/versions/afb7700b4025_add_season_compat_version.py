"""add season compat_version

Revision ID: afb7700b4025
Revises: a311d3c654c8
Create Date: 2026-02-17 12:56:38.590688

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "afb7700b4025"
down_revision: Union[str, Sequence[str], None] = "a311d3c654c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("seasons", sa.Column("compat_version", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("seasons", "compat_version")
