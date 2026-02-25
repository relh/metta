"""Add name, compat_version, git_commit, num_agents to mettagrid_env_configs

Revision ID: d4e5f6a7b8c9
Revises: a47a7013d7d0
Create Date: 2026-02-24 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "a47a7013d7d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("mettagrid_env_configs", sa.Column("name", sa.String(), nullable=True))
    op.add_column("mettagrid_env_configs", sa.Column("compat_version", sa.String(), nullable=True))
    op.add_column("mettagrid_env_configs", sa.Column("git_commit", sa.String(), nullable=True))
    op.add_column("mettagrid_env_configs", sa.Column("num_agents", sa.Integer(), nullable=True))
    op.create_index(
        "idx_env_configs_name_compat",
        "mettagrid_env_configs",
        ["name", "compat_version"],
        unique=True,
        postgresql_where=sa.text("name IS NOT NULL AND compat_version IS NOT NULL"),
    )
    op.create_index(
        "idx_env_configs_name_no_compat",
        "mettagrid_env_configs",
        ["name"],
        unique=True,
        postgresql_where=sa.text("name IS NOT NULL AND compat_version IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_env_configs_name_no_compat", table_name="mettagrid_env_configs")
    op.drop_index("idx_env_configs_name_compat", table_name="mettagrid_env_configs")
    op.drop_column("mettagrid_env_configs", "num_agents")
    op.drop_column("mettagrid_env_configs", "git_commit")
    op.drop_column("mettagrid_env_configs", "compat_version")
    op.drop_column("mettagrid_env_configs", "name")
