from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import Column, ForeignKey, Integer, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, Relationship, SQLModel

TaskStatus = Literal["unprocessed", "running", "canceled", "done", "error", "system_error"]
FinishedTaskStatus = Literal["done", "error", "canceled", "system_error"]


class EvalTask(SQLModel, table=True):
    __tablename__ = "eval_tasks"  # type: ignore[assignment]

    id: int | None = Field(default=None, primary_key=True)
    command: str
    data_uri: str | None = None
    git_hash: str | None = None
    attributes: dict[str, Any] | None = Field(default=None, sa_column=Column(JSONB))
    user_id: str
    is_finished: bool = Field(default=False, sa_column_kwargs={"server_default": text("false")})
    latest_attempt_id: int | None = Field(
        default=None, sa_column=Column(Integer, ForeignKey("task_attempts.id", ondelete="CASCADE"), nullable=True)
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), sa_column_kwargs={"server_default": text("CURRENT_TIMESTAMP")}
    )

    attempts: list["TaskAttempt"] = Relationship(
        back_populates="task",
        sa_relationship_kwargs={"foreign_keys": "[TaskAttempt.task_id]"},
    )


class TaskAttempt(SQLModel, table=True):
    __tablename__ = "task_attempts"  # type: ignore[assignment]

    id: int | None = Field(default=None, primary_key=True)
    task_id: int = Field(sa_column=Column(Integer, ForeignKey("eval_tasks.id", ondelete="CASCADE"), nullable=False))
    attempt_number: int = Field(default=0, sa_column_kwargs={"server_default": text("0")})
    status: str = Field(default="unprocessed", sa_column_kwargs={"server_default": text("'unprocessed'::text")})
    status_details: dict[str, Any] | None = Field(default=None, sa_column=Column(JSONB))
    assignee: str | None = None
    assigned_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    output_log_path: str | None = None

    task: EvalTask = Relationship(
        back_populates="attempts",
        sa_relationship_kwargs={"foreign_keys": "[TaskAttempt.task_id]"},
    )
