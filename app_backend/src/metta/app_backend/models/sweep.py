from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlmodel import Field, SQLModel


class Sweep(SQLModel, table=True):
    __tablename__ = "sweeps"  # type: ignore[assignment]

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(unique=True)
    project: str
    entity: str
    wandb_sweep_id: str
    state: str = Field(default="active")
    run_counter: int = Field(default=0)
    user_id: str
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), sa_column_kwargs={"server_default": text("now()")}
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), sa_column_kwargs={"server_default": text("now()")}
    )
