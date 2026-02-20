"""add episode_agent_metrics

Revision ID: c90c87b3b5d6
Revises: c3d4e5f6a7b8
Create Date: 2026-02-18 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op

revision: str = "c90c87b3b5d6"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "episode_agent_metrics",
        sa.Column("episode_internal_id", sa.Integer(), nullable=False),
        sa.Column("pv_internal_id", sa.Integer(), nullable=False),
        sa.Column("agent_id", sa.Integer(), nullable=False),
        sa.Column("metric_name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["episode_internal_id"], ["episodes.internal_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["pv_internal_id"], ["policy_versions.internal_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("episode_internal_id", "pv_internal_id", "agent_id", "metric_name"),
    )
    op.create_index(
        "idx_episode_agent_metrics_pv_metric",
        "episode_agent_metrics",
        ["pv_internal_id", "metric_name"],
        unique=False,
    )
    op.create_index(
        "idx_episode_agent_metrics_episode",
        "episode_agent_metrics",
        ["episode_internal_id"],
        unique=False,
    )
    op.create_index(
        "idx_episode_agent_metrics_episode_metric",
        "episode_agent_metrics",
        ["episode_internal_id", "metric_name"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_episode_agent_metrics_episode_metric", table_name="episode_agent_metrics")
    op.drop_index("idx_episode_agent_metrics_episode", table_name="episode_agent_metrics")
    op.drop_index("idx_episode_agent_metrics_pv_metric", table_name="episode_agent_metrics")
    op.drop_table("episode_agent_metrics")
