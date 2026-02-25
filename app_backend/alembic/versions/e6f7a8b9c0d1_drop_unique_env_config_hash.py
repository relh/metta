"""Drop unique constraint on mettagrid_env_configs.config_hash

Revision ID: e6f7a8b9c0d1
Revises: d4e5f6a7b8c9
Create Date: 2026-02-25 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

revision: str = "e6f7a8b9c0d1"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Legacy databases may carry either a unique index or a unique constraint name.
    op.execute("ALTER TABLE mettagrid_env_configs DROP CONSTRAINT IF EXISTS mettagrid_env_configs_config_hash_key")
    op.execute("DROP INDEX IF EXISTS ix_mettagrid_env_configs_config_hash")
    op.create_index(
        "ix_mettagrid_env_configs_config_hash",
        "mettagrid_env_configs",
        ["config_hash"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_mettagrid_env_configs_config_hash", table_name="mettagrid_env_configs")
    op.create_index(
        "ix_mettagrid_env_configs_config_hash",
        "mettagrid_env_configs",
        ["config_hash"],
        unique=True,
    )
