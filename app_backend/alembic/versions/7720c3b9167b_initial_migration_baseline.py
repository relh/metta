"""Initial migration baseline

Revision ID: 7720c3b9167b
Revises:
Create Date: 2026-02-09 12:28:08.308749

"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "7720c3b9167b"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Enable uuid-ossp extension for uuid_generate_v4()
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    # Create sequences for auto-incrementing internal_id fields
    op.execute("CREATE SEQUENCE episodes_internal_id_seq")
    op.execute("CREATE SEQUENCE policy_versions_internal_id_seq")

    # Create eval_tasks WITHOUT the latest_attempt_id FK (circular dependency with task_attempts)
    op.create_table(
        "eval_tasks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("command", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("data_uri", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("git_hash", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("attributes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("user_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("is_finished", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("latest_attempt_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "job_requests",
        sa.Column("worker", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("error_type", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("job_type", sa.Enum("episode", name="jobtype"), nullable=False),
        sa.Column("job", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "dispatched", "running", "completed", "failed", name="job_status"),
            server_default=sa.text("'pending'::job_status"),
            nullable=False,
        ),
        sa.Column("user_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("dispatched_at", sa.DateTime(), nullable=True),
        sa.Column("running_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_job_requests_status", "job_requests", ["status"], unique=False)
    op.create_index("idx_job_requests_user_id", "job_requests", ["user_id"], unique=False)
    op.create_index(
        "idx_job_requests_type_status_created",
        "job_requests",
        ["job_type", "status", sa.text("created_at DESC")],
        unique=False,
    )
    op.create_index(
        "idx_job_requests_type_created", "job_requests", ["job_type", sa.text("created_at DESC")], unique=False
    )
    op.create_index("idx_job_requests_created", "job_requests", [sa.text("created_at DESC")], unique=False)
    op.create_table(
        "k8s_events",
        sa.Column("id", sa.BIGINT(), nullable=False),
        sa.Column("cluster", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.Column("event_time", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("event", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("processed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_k8s_events_cluster_event_time", "k8s_events", ["cluster", sa.text("event_time DESC")], unique=False
    )
    op.create_index(
        "idx_k8s_events_unprocessed",
        "k8s_events",
        ["event_time"],
        unique=False,
        postgresql_where=sa.text("processed_at IS NULL"),
    )
    op.create_table(
        "mettagrid_env_configs",
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("config_hash", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_mettagrid_env_configs_config_hash"), "mettagrid_env_configs", ["config_hash"], unique=True)
    op.create_table(
        "policies",
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("user_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("attributes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "seasons",
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("canonical", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("disabled_at", sa.DateTime(), nullable=True),
        sa.Column("description", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", "version", name="seasons_name_version_key"),
    )
    op.create_index(op.f("ix_seasons_name"), "seasons", ["name"], unique=False)
    op.create_index(
        "idx_seasons_canonical", "seasons", ["name"], unique=True, postgresql_where=sa.text("canonical = true")
    )
    op.create_table(
        "sweeps",
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("project", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("entity", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("wandb_sweep_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "state", sqlmodel.sql.sqltypes.AutoString(), server_default=sa.text("'running'::text"), nullable=False
        ),
        sa.Column("run_counter", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("user_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("idx_sweeps_name", "sweeps", ["name"], unique=False)
    op.create_table(
        "task_attempts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "status", sqlmodel.sql.sqltypes.AutoString(), server_default=sa.text("'unprocessed'::text"), nullable=False
        ),
        sa.Column("status_details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("assignee", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("assigned_at", sa.DateTime(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("output_log_path", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.ForeignKeyConstraint(["task_id"], ["eval_tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Add deferred FK from eval_tasks to task_attempts (circular dependency)
    op.create_foreign_key(
        "eval_tasks_latest_attempt_fkey",
        "eval_tasks",
        "task_attempts",
        ["latest_attempt_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.create_table(
        "policy_versions",
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column(
            "internal_id",
            sa.Integer(),
            server_default=sa.text("nextval('policy_versions_internal_id_seq')"),
            autoincrement=True,
            nullable=True,
        ),
        sa.Column("policy_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("s3_path", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("git_hash", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("policy_spec", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("attributes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["policy_id"], ["policies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("internal_id"),
        sa.UniqueConstraint("policy_id", "version", name="policy_versions_policy_id_version_key"),
    )
    op.create_index(op.f("ix_policy_versions_policy_id"), "policy_versions", ["policy_id"], unique=False)
    op.create_table(
        "pools",
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("season_id", sa.Uuid(), nullable=True),
        sa.Column("env_config_id", sa.Uuid(), nullable=True),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["env_config_id"], ["mettagrid_env_configs.id"]),
        sa.ForeignKeyConstraint(["season_id"], ["seasons.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_pools_season_name", "pools", ["season_id", "name"], unique=False)
    op.create_index(op.f("ix_pools_season_id"), "pools", ["season_id"], unique=False)
    op.create_table(
        "episodes",
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column(
            "internal_id",
            sa.Integer(),
            server_default=sa.text("nextval('episodes_internal_id_seq')"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("data_uri", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("replay_url", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("thumbnail_url", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("attributes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("eval_task_id", sa.Uuid(), nullable=True),
        sa.Column("primary_pv_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["primary_pv_id"], ["policy_versions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("internal_id"),
    )
    op.create_table(
        "job_policy_versions",
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("policy_version_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["job_requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["policy_version_id"], ["policy_versions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("job_id", "position"),
    )
    op.create_index(
        "idx_job_policy_versions_policy_version_id", "job_policy_versions", ["policy_version_id"], unique=False
    )
    op.create_table(
        "matches",
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("pool_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        sa.Column("assignments", postgresql.ARRAY(sa.INTEGER()), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "scheduled", "running", "completed", "failed", name="match_status"),
            server_default=sa.text("'pending'::match_status"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["job_requests.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["pool_id"], ["pools.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_matches_status", "matches", ["status"], unique=False)
    op.create_index("idx_matches_pool_status", "matches", ["pool_id", "status"], unique=False)
    op.create_index("idx_matches_pool_created", "matches", ["pool_id", sa.text("created_at DESC")], unique=False)
    op.create_index(op.f("ix_matches_job_id"), "matches", ["job_id"], unique=False)
    op.create_index(op.f("ix_matches_pool_id"), "matches", ["pool_id"], unique=False)
    op.create_table(
        "policy_version_tags",
        sa.Column("policy_version_id", sa.Uuid(), nullable=False),
        sa.Column("key", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("value", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.ForeignKeyConstraint(["policy_version_id"], ["policy_versions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("policy_version_id", "key"),
    )
    op.create_index("idx_policy_version_tags_key_value", "policy_version_tags", ["key", "value"], unique=False)
    op.create_table(
        "pool_players",
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("pool_id", sa.Uuid(), nullable=False),
        sa.Column("policy_version_id", sa.Uuid(), nullable=False),
        sa.Column("retired", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["policy_version_id"], ["policy_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["pool_id"], ["pools.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("pool_id", "policy_version_id", name="pool_players_pool_id_policy_version_id_key"),
    )
    op.create_index(op.f("ix_pool_players_policy_version_id"), "pool_players", ["policy_version_id"], unique=False)
    op.create_index(op.f("ix_pool_players_pool_id"), "pool_players", ["pool_id"], unique=False)
    op.create_table(
        "episode_jobs",
        sa.Column("episode_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["episode_id"], ["episodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["job_requests.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("episode_id", "job_id"),
    )
    op.create_index("idx_episode_jobs_job_id", "episode_jobs", ["job_id"], unique=False)
    op.create_table(
        "episode_policies",
        sa.Column("episode_id", sa.Uuid(), nullable=False),
        sa.Column("policy_version_id", sa.Uuid(), nullable=False),
        sa.Column("num_agents", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["episode_id"], ["episodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["policy_version_id"], ["policy_versions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("episode_id", "policy_version_id"),
    )
    op.create_table(
        "episode_policy_metrics",
        sa.Column("episode_internal_id", sa.Integer(), nullable=False),
        sa.Column("pv_internal_id", sa.Integer(), nullable=False),
        sa.Column("metric_name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["episode_internal_id"], ["episodes.internal_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["pv_internal_id"], ["policy_versions.internal_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("episode_internal_id", "pv_internal_id", "metric_name"),
    )
    op.create_table(
        "episode_tags",
        sa.Column("episode_id", sa.Uuid(), nullable=False),
        sa.Column("key", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("value", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.ForeignKeyConstraint(["episode_id"], ["episodes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("episode_id", "key"),
    )
    op.create_index("idx_episode_tags_episode_key_value", "episode_tags", ["episode_id", "key", "value"], unique=False)
    op.create_index("idx_episode_tags_key_value", "episode_tags", ["key", "value"], unique=False)
    op.create_table(
        "match_players",
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("match_id", sa.Uuid(), nullable=False),
        sa.Column("pool_player_id", sa.Uuid(), nullable=False),
        sa.Column("policy_index", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["match_id"], ["matches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["pool_player_id"], ["pool_players.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_match_players_match_id"), "match_players", ["match_id"], unique=False)
    op.create_index(op.f("ix_match_players_pool_player_id"), "match_players", ["pool_player_id"], unique=False)
    op.create_table(
        "membership_changes",
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuid_generate_v4()"), nullable=False),
        sa.Column("pool_player_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.Enum("add", "remove", name="membership_action"), nullable=False),
        sa.Column("notes", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["pool_player_id"], ["pool_players.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_membership_changes_pool_player_id"), "membership_changes", ["pool_player_id"], unique=False
    )
    op.create_index(
        "idx_membership_changes_created_at", "membership_changes", [sa.text("created_at DESC")], unique=False
    )

    # Create eval_tasks_view (matches legacy migration v0)
    op.execute("""
        CREATE VIEW eval_tasks_view AS
        SELECT
            t.id, t.command, t.data_uri, t.git_hash, t.attributes,
            t.user_id, t.created_at, t.is_finished, t.latest_attempt_id,
            a.attempt_number, a.status, a.status_details, a.assigned_at,
            a.assignee, a.started_at, a.finished_at, a.output_log_path
        FROM eval_tasks t
        LEFT JOIN task_attempts a ON t.latest_attempt_id = a.id
    """)


def downgrade() -> None:
    """Downgrade schema."""
    # Drop the view first
    op.execute("DROP VIEW IF EXISTS eval_tasks_view")

    # Drop deferred FK from eval_tasks
    op.drop_constraint("eval_tasks_latest_attempt_fkey", "eval_tasks", type_="foreignkey")

    # Drop tables in reverse dependency order
    op.drop_index("idx_membership_changes_created_at", table_name="membership_changes")
    op.drop_index(op.f("ix_membership_changes_pool_player_id"), table_name="membership_changes")
    op.drop_table("membership_changes")
    op.drop_index(op.f("ix_match_players_pool_player_id"), table_name="match_players")
    op.drop_index(op.f("ix_match_players_match_id"), table_name="match_players")
    op.drop_table("match_players")
    op.drop_index("idx_episode_tags_key_value", table_name="episode_tags")
    op.drop_index("idx_episode_tags_episode_key_value", table_name="episode_tags")
    op.drop_table("episode_tags")
    op.drop_table("episode_policy_metrics")
    op.drop_table("episode_policies")
    op.drop_index("idx_episode_jobs_job_id", table_name="episode_jobs")
    op.drop_table("episode_jobs")
    op.drop_index(op.f("ix_pool_players_pool_id"), table_name="pool_players")
    op.drop_index(op.f("ix_pool_players_policy_version_id"), table_name="pool_players")
    op.drop_table("pool_players")
    op.drop_index("idx_policy_version_tags_key_value", table_name="policy_version_tags")
    op.drop_table("policy_version_tags")
    op.drop_index(op.f("ix_matches_pool_id"), table_name="matches")
    op.drop_index(op.f("ix_matches_job_id"), table_name="matches")
    op.drop_index("idx_matches_pool_created", table_name="matches")
    op.drop_index("idx_matches_pool_status", table_name="matches")
    op.drop_index("idx_matches_status", table_name="matches")
    op.drop_table("matches")
    op.drop_index("idx_job_policy_versions_policy_version_id", table_name="job_policy_versions")
    op.drop_table("job_policy_versions")
    op.drop_table("episodes")
    op.drop_index(op.f("ix_pools_season_id"), table_name="pools")
    op.drop_index("idx_pools_season_name", table_name="pools")
    op.drop_table("pools")
    op.drop_index(op.f("ix_policy_versions_policy_id"), table_name="policy_versions")
    op.drop_table("policy_versions")
    op.drop_table("task_attempts")
    op.drop_index("idx_sweeps_name", table_name="sweeps")
    op.drop_table("sweeps")
    op.drop_index("idx_seasons_canonical", table_name="seasons")
    op.drop_index(op.f("ix_seasons_name"), table_name="seasons")
    op.drop_table("seasons")
    op.drop_table("policies")
    op.drop_index(op.f("ix_mettagrid_env_configs_config_hash"), table_name="mettagrid_env_configs")
    op.drop_table("mettagrid_env_configs")
    op.drop_index("idx_k8s_events_unprocessed", table_name="k8s_events")
    op.drop_index("idx_k8s_events_cluster_event_time", table_name="k8s_events")
    op.drop_table("k8s_events")
    op.drop_index("idx_job_requests_created", table_name="job_requests")
    op.drop_index("idx_job_requests_type_created", table_name="job_requests")
    op.drop_index("idx_job_requests_type_status_created", table_name="job_requests")
    op.drop_index("idx_job_requests_user_id", table_name="job_requests")
    op.drop_index("idx_job_requests_status", table_name="job_requests")
    op.drop_table("job_requests")
    op.drop_table("eval_tasks")

    # Drop sequences
    op.execute("DROP SEQUENCE IF EXISTS policy_versions_internal_id_seq")
    op.execute("DROP SEQUENCE IF EXISTS episodes_internal_id_seq")

    # Drop ENUM types (must be after tables that use them are dropped)
    op.execute("DROP TYPE IF EXISTS membership_action")
    op.execute("DROP TYPE IF EXISTS match_status")
    op.execute("DROP TYPE IF EXISTS job_status")
    op.execute("DROP TYPE IF EXISTS jobtype")
