"""Add team tournament tables (teams, team_policy_versions) and matches.team_id

Revision ID: a1b2c3d4e5f6
Revises: afb7700b4025
Create Date: 2026-02-11 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "afb7700b4025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "teams",
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("pool_id", sa.Uuid(), nullable=False),
        sa.Column("eliminated", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["pool_id"], ["pools.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_teams_pool_id"), "teams", ["pool_id"], unique=False)
    op.create_index("idx_teams_pool_eliminated", "teams", ["pool_id", "eliminated"], unique=False)

    op.create_table(
        "team_policy_versions",
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("policy_version_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["policy_version_id"], ["policy_versions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("team_id", "position", name="team_policy_versions_team_id_position_key"),
    )
    op.create_index(op.f("ix_team_policy_versions_team_id"), "team_policy_versions", ["team_id"], unique=False)
    op.create_index(
        op.f("ix_team_policy_versions_policy_version_id"),
        "team_policy_versions",
        ["policy_version_id"],
        unique=False,
    )

    op.add_column("matches", sa.Column("team_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("matches_team_id_fkey", "matches", "teams", ["team_id"], ["id"], ondelete="SET NULL")
    op.create_index(op.f("ix_matches_team_id"), "matches", ["team_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_matches_team_id"), table_name="matches")
    op.drop_constraint("matches_team_id_fkey", "matches", type_="foreignkey")
    op.drop_column("matches", "team_id")

    op.drop_index(op.f("ix_team_policy_versions_policy_version_id"), table_name="team_policy_versions")
    op.drop_index(op.f("ix_team_policy_versions_team_id"), table_name="team_policy_versions")
    op.drop_table("team_policy_versions")

    op.drop_index("idx_teams_pool_eliminated", table_name="teams")
    op.drop_index(op.f("ix_teams_pool_id"), table_name="teams")
    op.drop_table("teams")
