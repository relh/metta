from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import Column, ForeignKey, Index, UniqueConstraint, Uuid, text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import ARRAY, INTEGER, JSONB
from sqlmodel import Field, Relationship, SQLModel

from metta.app_backend.models.policies import PolicyVersion

if TYPE_CHECKING:
    from metta.app_backend.models.job_request import JobRequest


class MatchStatus(str, Enum):
    pending = "pending"
    scheduled = "scheduled"
    running = "running"
    completed = "completed"
    failed = "failed"


class MembershipAction(str, Enum):
    add = "add"
    remove = "remove"


class MettagridEnvConfig(SQLModel, table=True):
    __tablename__ = "mettagrid_env_configs"  # type: ignore[assignment]

    id: UUID = Field(
        default_factory=uuid4, primary_key=True, sa_column_kwargs={"server_default": text("uuid_generate_v4()")}
    )
    config_hash: str = Field(index=True, unique=True)
    config: dict[str, Any] = Field(sa_column=Column(JSONB, nullable=False))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), sa_column_kwargs={"server_default": text("CURRENT_TIMESTAMP")}
    )


class Season(SQLModel, table=True):
    __tablename__ = "seasons"  # type: ignore[assignment]
    __table_args__ = (
        UniqueConstraint("name", "version", name="seasons_name_version_key"),
        Index("idx_seasons_canonical", "name", unique=True, postgresql_where=text("canonical = true")),
    )

    id: UUID = Field(
        default_factory=uuid4, primary_key=True, sa_column_kwargs={"server_default": text("uuid_generate_v4()")}
    )
    name: str = Field(index=True)
    version: int = Field(default=1, sa_column_kwargs={"server_default": text("1")})
    canonical: bool = Field(default=False, sa_column_kwargs={"server_default": text("false")})
    disabled_at: datetime | None = Field(default=None)
    description: str | None = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), sa_column_kwargs={"server_default": text("CURRENT_TIMESTAMP")}
    )

    pools: list["Pool"] = Relationship(back_populates="season")


class Pool(SQLModel, table=True):
    __tablename__ = "pools"  # type: ignore[assignment]
    __table_args__ = (Index("idx_pools_season_name", "season_id", "name"),)

    id: UUID = Field(
        default_factory=uuid4, primary_key=True, sa_column_kwargs={"server_default": text("uuid_generate_v4()")}
    )
    season_id: UUID | None = Field(
        default=None,
        sa_column=Column(Uuid, ForeignKey("seasons.id", ondelete="CASCADE"), nullable=True, index=True),
    )
    env_config_id: UUID | None = Field(
        default=None, sa_column=Column(Uuid, ForeignKey("mettagrid_env_configs.id"), nullable=True)
    )
    name: str | None = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), sa_column_kwargs={"server_default": text("CURRENT_TIMESTAMP")}
    )

    season: Season | None = Relationship(back_populates="pools")
    env_config: MettagridEnvConfig | None = Relationship()
    matches: list["Match"] = Relationship(back_populates="pool")
    players: list["PoolPlayer"] = Relationship(
        back_populates="pool",
        sa_relationship_kwargs={"lazy": "selectin"},
    )

    @property
    def active_players(self) -> list["PoolPlayer"]:
        return [p for p in self.players if not p.retired]

    @property
    def active_member_ids(self) -> set[UUID]:
        return {p.policy_version_id for p in self.players if not p.retired}


class PoolPlayer(SQLModel, table=True):
    __tablename__ = "pool_players"  # type: ignore[assignment]
    __table_args__ = (
        UniqueConstraint("pool_id", "policy_version_id", name="pool_players_pool_id_policy_version_id_key"),
    )

    id: UUID = Field(
        default_factory=uuid4, primary_key=True, sa_column_kwargs={"server_default": text("uuid_generate_v4()")}
    )
    pool_id: UUID = Field(
        sa_column=Column(Uuid, ForeignKey("pools.id", ondelete="CASCADE"), index=True, nullable=False)
    )
    policy_version_id: UUID = Field(
        sa_column=Column(Uuid, ForeignKey("policy_versions.id", ondelete="CASCADE"), index=True, nullable=False)
    )
    retired: bool = Field(default=False, sa_column_kwargs={"server_default": text("false")})
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), sa_column_kwargs={"server_default": text("CURRENT_TIMESTAMP")}
    )

    pool: "Pool" = Relationship(back_populates="players")
    policy_version: PolicyVersion = Relationship(back_populates="pool_players")
    membership_changes: list["MembershipChange"] = Relationship(back_populates="pool_player")


class Match(SQLModel, table=True):
    __tablename__ = "matches"  # type: ignore[assignment]
    __table_args__ = (
        Index("idx_matches_status", "status"),
        Index("idx_matches_pool_status", "pool_id", "status"),
        Index("idx_matches_pool_created", "pool_id", text("created_at DESC")),
    )

    id: UUID = Field(
        default_factory=uuid4, primary_key=True, sa_column_kwargs={"server_default": text("uuid_generate_v4()")}
    )
    pool_id: UUID = Field(
        sa_column=Column(Uuid, ForeignKey("pools.id", ondelete="CASCADE"), index=True, nullable=False)
    )
    job_id: UUID | None = Field(
        default=None,
        sa_column=Column(Uuid, ForeignKey("job_requests.id", ondelete="SET NULL"), nullable=True, index=True),
    )
    assignments: list[int] = Field(sa_column=Column(ARRAY(INTEGER), nullable=False))
    status: MatchStatus = Field(
        default=MatchStatus.pending,
        sa_type=SQLEnum(MatchStatus, name="match_status"),
        sa_column_kwargs={"server_default": text("'pending'::match_status")},
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), sa_column_kwargs={"server_default": text("CURRENT_TIMESTAMP")}
    )
    completed_at: datetime | None = None

    pool: Pool = Relationship(back_populates="matches")
    players: list["MatchPlayer"] = Relationship(back_populates="match", sa_relationship_kwargs={"lazy": "selectin"})
    job: Optional["JobRequest"] = Relationship(back_populates="matches")


class MatchPlayer(SQLModel, table=True):
    __tablename__ = "match_players"  # type: ignore[assignment]

    id: UUID = Field(
        default_factory=uuid4, primary_key=True, sa_column_kwargs={"server_default": text("uuid_generate_v4()")}
    )
    match_id: UUID = Field(
        sa_column=Column(Uuid, ForeignKey("matches.id", ondelete="CASCADE"), index=True, nullable=False)
    )
    pool_player_id: UUID = Field(
        sa_column=Column(Uuid, ForeignKey("pool_players.id", ondelete="CASCADE"), index=True, nullable=False)
    )
    policy_index: int = Field(default=0, sa_column_kwargs={"server_default": text("0")})
    score: float | None = None

    match: Match = Relationship(back_populates="players")
    pool_player: PoolPlayer = Relationship()


class MembershipChange(SQLModel, table=True):
    __tablename__ = "membership_changes"  # type: ignore[assignment]
    __table_args__ = (Index("idx_membership_changes_created_at", text("created_at DESC")),)

    id: UUID = Field(
        default_factory=uuid4, primary_key=True, sa_column_kwargs={"server_default": text("uuid_generate_v4()")}
    )
    pool_player_id: UUID = Field(
        sa_column=Column(Uuid, ForeignKey("pool_players.id", ondelete="CASCADE"), index=True, nullable=False)
    )
    action: MembershipAction = Field(sa_type=SQLEnum(MembershipAction, name="membership_action"))
    notes: str | None = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), sa_column_kwargs={"server_default": text("CURRENT_TIMESTAMP")}
    )

    pool_player: PoolPlayer = Relationship(back_populates="membership_changes")
