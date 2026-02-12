from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import Column, ForeignKey, Index, UniqueConstraint, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from metta.app_backend.models.tournament import PoolPlayer


class Policy(SQLModel, table=True):
    __tablename__ = "policies"  # type: ignore[assignment]

    id: UUID = Field(
        default_factory=uuid4, primary_key=True, sa_column_kwargs={"server_default": text("uuid_generate_v4()")}
    )
    name: str = Field(unique=True)
    user_id: str
    attributes: dict[str, Any] | None = Field(default=None, sa_column=Column(JSONB))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), sa_column_kwargs={"server_default": text("CURRENT_TIMESTAMP")}
    )

    versions: list["PolicyVersion"] = Relationship(back_populates="policy")


class PolicyVersion(SQLModel, table=True):
    __tablename__ = "policy_versions"  # type: ignore[assignment]
    __table_args__ = (UniqueConstraint("policy_id", "version", name="policy_versions_policy_id_version_key"),)

    id: UUID = Field(
        default_factory=uuid4, primary_key=True, sa_column_kwargs={"server_default": text("uuid_generate_v4()")}
    )
    internal_id: int | None = Field(
        default=None,
        sa_column_kwargs={
            "autoincrement": True,
            "unique": True,
            "server_default": text("nextval('policy_versions_internal_id_seq')"),
        },
    )
    policy_id: UUID = Field(
        sa_column=Column(Uuid, ForeignKey("policies.id", ondelete="CASCADE"), index=True, nullable=False)
    )
    version: int
    s3_path: str | None = None
    git_hash: str | None = None
    policy_spec: dict[str, Any] | None = Field(default=None, sa_column=Column(JSONB))  # deprecated
    attributes: dict[str, Any] | None = Field(default=None, sa_column=Column(JSONB))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), sa_column_kwargs={"server_default": text("CURRENT_TIMESTAMP")}
    )

    policy: Policy = Relationship(back_populates="versions")
    pool_players: list["PoolPlayer"] = Relationship(back_populates="policy_version")
    tags: list["PolicyVersionTag"] = Relationship(back_populates="policy_version")


class PolicyVersionTag(SQLModel, table=True):
    __tablename__ = "policy_version_tags"  # type: ignore[assignment]
    __table_args__ = (Index("idx_policy_version_tags_key_value", "key", "value"),)

    policy_version_id: UUID = Field(
        sa_column=Column(Uuid, ForeignKey("policy_versions.id", ondelete="CASCADE"), primary_key=True)
    )
    key: str = Field(primary_key=True)
    value: str

    policy_version: PolicyVersion = Relationship(back_populates="tags")


# Import tournament after all models are defined to resolve forward references.
# This ensures PoolPlayer is available when SQLAlchemy configures the PolicyVersion.pool_players relationship.
from metta.app_backend.models import tournament as _tournament  # noqa: E402, F401
