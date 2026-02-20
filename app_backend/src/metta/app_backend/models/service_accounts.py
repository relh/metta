from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlmodel import Field, SQLModel, UniqueConstraint


class TokenPrefixType(StrEnum):
    """
    Defines types of service accounts.
    default = SOFTMAX; which is treated as an admin service account
    """

    SOFTMAX = "ssa_"


class ServiceAccount(SQLModel, table=True):
    __tablename__: str = "service_accounts"

    id: UUID = Field(
        default_factory=uuid4, primary_key=True, sa_column_kwargs={"server_default": text("uuid_generate_v4()")}
    )
    name: str
    user_id: str
    token_hash: str = Field(index=True)  # SHA256 hash of actual token excluding prefix, lookup column for auth
    token_preview: str  # Publicly safe snippet of actual token
    token_prefix: str = Field(default=TokenPrefixType.SOFTMAX, sa_column_kwargs={"server_default": text("'ssa_'")})
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), sa_column_kwargs={"server_default": text("CURRENT_TIMESTAMP")}
    )

    __table_args__ = (UniqueConstraint("name", "user_id", name="unique_user_sa_name"),)
