from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import Index, text
from sqlmodel import Field, SQLModel


class Sweep(SQLModel, table=True):
    __tablename__ = "sweeps"  # type: ignore[assignment]
    __table_args__ = (Index("idx_sweeps_name", "name"),)

    id: UUID = Field(
        default_factory=uuid4, primary_key=True, sa_column_kwargs={"server_default": text("uuid_generate_v4()")}
    )
    name: str = Field(unique=True)
    project: str
    entity: str
    wandb_sweep_id: str
    state: str = Field(default="active", sa_column_kwargs={"server_default": text("'running'::text")})
    run_counter: int = Field(default=0, sa_column_kwargs={"server_default": text("0")})
    user_id: str
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), sa_column_kwargs={"server_default": text("CURRENT_TIMESTAMP")}
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), sa_column_kwargs={"server_default": text("CURRENT_TIMESTAMP")}
    )
