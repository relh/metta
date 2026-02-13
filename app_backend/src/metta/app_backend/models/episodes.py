from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Column, ForeignKey, Index, Integer, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, Relationship, SQLModel


class Episode(SQLModel, table=True):
    __tablename__ = "episodes"  # type: ignore[assignment]

    id: UUID = Field(
        default_factory=uuid4, primary_key=True, sa_column_kwargs={"server_default": text("uuid_generate_v4()")}
    )
    internal_id: int | None = Field(
        default=None,
        sa_column_kwargs={
            "autoincrement": True,
            "unique": True,
            "nullable": False,
            "server_default": text("nextval('episodes_internal_id_seq')"),
        },
    )
    data_uri: str
    replay_url: str | None = None
    thumbnail_url: str | None = None
    attributes: dict[str, Any] | None = Field(default=None, sa_column=Column(JSONB))
    eval_task_id: UUID | None = None
    primary_pv_id: UUID | None = Field(
        default=None, sa_column=Column(Uuid, ForeignKey("policy_versions.id", ondelete="CASCADE"), nullable=True)
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), sa_column_kwargs={"server_default": text("CURRENT_TIMESTAMP")}
    )

    episode_policies: list["EpisodePolicy"] = Relationship(back_populates="episode")
    episode_jobs: list["EpisodeJob"] = Relationship(back_populates="episode")
    tags: list["EpisodeTag"] = Relationship(back_populates="episode")


class EpisodePolicy(SQLModel, table=True):
    __tablename__ = "episode_policies"  # type: ignore[assignment]

    episode_id: UUID = Field(sa_column=Column(Uuid, ForeignKey("episodes.id", ondelete="CASCADE"), primary_key=True))
    policy_version_id: UUID = Field(
        sa_column=Column(Uuid, ForeignKey("policy_versions.id", ondelete="CASCADE"), primary_key=True)
    )
    num_agents: int

    episode: Episode = Relationship(back_populates="episode_policies")


class EpisodePolicyMetric(SQLModel, table=True):
    __tablename__ = "episode_policy_metrics"  # type: ignore[assignment]

    episode_internal_id: int = Field(
        sa_column=Column(Integer, ForeignKey("episodes.internal_id", ondelete="CASCADE"), primary_key=True)
    )
    pv_internal_id: int = Field(
        sa_column=Column(Integer, ForeignKey("policy_versions.internal_id", ondelete="CASCADE"), primary_key=True)
    )
    metric_name: str = Field(primary_key=True)
    value: float


class EpisodeTag(SQLModel, table=True):
    __tablename__ = "episode_tags"  # type: ignore[assignment]
    __table_args__ = (
        Index("idx_episode_tags_key_value", "key", "value"),
        Index("idx_episode_tags_episode_key_value", "episode_id", "key", "value"),
    )

    episode_id: UUID = Field(sa_column=Column(Uuid, ForeignKey("episodes.id", ondelete="CASCADE"), primary_key=True))
    key: str = Field(primary_key=True)
    value: str

    episode: Episode = Relationship(back_populates="tags")


class EpisodeJob(SQLModel, table=True):
    __tablename__ = "episode_jobs"  # type: ignore[assignment]
    __table_args__ = (Index("idx_episode_jobs_job_id", "job_id"),)

    episode_id: UUID = Field(sa_column=Column(Uuid, ForeignKey("episodes.id", ondelete="CASCADE"), primary_key=True))
    job_id: UUID = Field(sa_column=Column(Uuid, ForeignKey("job_requests.id", ondelete="CASCADE"), primary_key=True))

    episode: Episode = Relationship(back_populates="episode_jobs")
    job: "JobRequest" = Relationship(back_populates="episode_jobs")


# Import after classes are defined to avoid circular imports
from metta.app_backend.models.job_request import JobRequest as JobRequest  # noqa: E402, F401
