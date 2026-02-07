# pyright: reportArgumentType=false
# pyright: reportCallIssue=false
# pyright: reportAttributeAccessIssue=false
# pyright: reportOptionalMemberAccess=false

from collections import defaultdict
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import String, cast, func, update
from sqlalchemy.sql import Select
from sqlmodel import select

from metta.app_backend.database import get_db, with_db
from metta.app_backend.models.eval_task import EvalTask, FinishedTaskStatus, TaskAttempt, TaskStatus
from metta.app_backend.user_data import Ownable


class EvalTaskRow(Ownable):
    model_config = {"from_attributes": True}

    id: int
    command: str
    data_uri: str | None
    git_hash: str | None
    attributes: dict[str, Any]
    created_at: datetime
    is_finished: bool
    latest_attempt_id: int | None
    attempt_number: int | None = 0
    status: TaskStatus = "unprocessed"
    status_details: dict[str, Any] | None = None
    assigned_at: datetime | None = None
    assignee: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    output_log_path: str | None = None

    @classmethod
    def from_task_and_attempt(cls, task: EvalTask, attempt: TaskAttempt | None) -> "EvalTaskRow":
        return cls(
            id=task.id,  # type: ignore[arg-type]
            command=task.command,
            data_uri=task.data_uri,
            git_hash=task.git_hash,
            attributes=task.attributes or {},
            user_id=task.user_id,
            created_at=task.created_at,
            is_finished=task.is_finished,
            latest_attempt_id=task.latest_attempt_id,
            attempt_number=attempt.attempt_number if attempt else 0,
            status=attempt.status if attempt else "unprocessed",  # type: ignore[arg-type]
            status_details=attempt.status_details if attempt else None,
            assigned_at=attempt.assigned_at if attempt else None,
            assignee=attempt.assignee if attempt else None,
            started_at=attempt.started_at if attempt else None,
            finished_at=attempt.finished_at if attempt else None,
            output_log_path=attempt.output_log_path if attempt else None,
        )


class TaskAttemptRow(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    task_id: int
    attempt_number: int
    assigned_at: datetime | None
    assignee: str | None
    started_at: datetime | None
    finished_at: datetime | None
    output_log_path: str | None
    status: TaskStatus
    status_details: dict[str, Any] | None

    @classmethod
    def from_model(cls, attempt: TaskAttempt) -> "TaskAttemptRow":
        return cls(
            id=attempt.id,  # type: ignore[arg-type]
            task_id=attempt.task_id,
            attempt_number=attempt.attempt_number,
            assigned_at=attempt.assigned_at,
            assignee=attempt.assignee,
            started_at=attempt.started_at,
            finished_at=attempt.finished_at,
            output_log_path=attempt.output_log_path,
            status=attempt.status,  # type: ignore[arg-type]
            status_details=attempt.status_details,
        )


class TaskStatusUpdate(BaseModel):
    status: TaskStatus
    clear_assignee: bool = False
    status_details: dict[str, Any] = Field(default_factory=dict)


def _eval_task_row_stmt() -> Select:
    return select(EvalTask, TaskAttempt).outerjoin(TaskAttempt, TaskAttempt.id == EvalTask.latest_attempt_id)


def _rows_to_eval_task_rows(rows: list[tuple[EvalTask, TaskAttempt | None]]) -> list[EvalTaskRow]:
    return [EvalTaskRow.from_task_and_attempt(task, attempt) for task, attempt in rows]


def _latest_attempt_id_subquery(task_id: int) -> Select:
    return select(EvalTask.latest_attempt_id).where(EvalTask.id == task_id)


@with_db
async def create_eval_task(
    command: str,
    user_id: str,
    attributes: dict[str, Any],
    git_hash: str | None = None,
    data_uri: str | None = None,
) -> EvalTaskRow:
    session = get_db()

    task = EvalTask(
        command=command,
        data_uri=data_uri,
        git_hash=git_hash,
        attributes=attributes,
        user_id=user_id,
    )
    session.add(task)
    await session.flush()

    attempt = TaskAttempt(task_id=task.id, attempt_number=0, status="unprocessed")  # type: ignore[arg-type]
    session.add(attempt)
    await session.flush()

    task.latest_attempt_id = attempt.id
    await session.flush()

    return EvalTaskRow.from_task_and_attempt(task, attempt)


@with_db
async def get_available_tasks(limit: int = 200) -> list[EvalTaskRow]:
    session = get_db()
    stmt = (
        _eval_task_row_stmt()
        .where(
            TaskAttempt.status == "unprocessed",
            TaskAttempt.assignee.is_(None),
            EvalTask.is_finished.is_(False),
        )
        .order_by(EvalTask.created_at.asc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    return _rows_to_eval_task_rows(rows)


@with_db
async def claim_tasks(task_ids: list[int], assignee: str) -> list[int]:
    if not task_ids:
        return []

    session = get_db()
    latest_attempts = select(EvalTask.latest_attempt_id).where(
        EvalTask.id.in_(task_ids),
        EvalTask.is_finished.is_(False),
    )
    stmt = (
        update(TaskAttempt)
        .where(
            TaskAttempt.id.in_(latest_attempts),
            TaskAttempt.status == "unprocessed",
            TaskAttempt.assignee.is_(None),
        )
        .values(assignee=assignee, assigned_at=func.now())
        .returning(TaskAttempt.task_id)
    )
    rows = (await session.execute(stmt)).all()
    return [row[0] for row in rows]


@with_db
async def get_claimed_tasks(assignee: str | None = None) -> list[EvalTaskRow]:
    session = get_db()
    stmt = _eval_task_row_stmt().where(EvalTask.is_finished.is_(False))
    if assignee is not None:
        stmt = stmt.where(TaskAttempt.assignee == assignee)
    else:
        stmt = stmt.where(TaskAttempt.assignee.is_not(None))
    stmt = stmt.order_by(EvalTask.created_at.asc())
    rows = (await session.execute(stmt)).all()
    return _rows_to_eval_task_rows(rows)


@with_db
async def start_task(task_id: int) -> None:
    session = get_db()
    latest_attempt_id = _latest_attempt_id_subquery(task_id).scalar_subquery()
    stmt = (
        update(TaskAttempt).where(TaskAttempt.id == latest_attempt_id).values(status="running", started_at=func.now())
    )
    await session.execute(stmt)


@with_db
async def finish_task(
    task_id: int, status: FinishedTaskStatus, status_details: dict[str, Any], log_path: str | None = None
) -> None:
    session = get_db()

    latest_attempt_id = _latest_attempt_id_subquery(task_id).scalar_subquery()
    stmt = (
        update(TaskAttempt)
        .where(TaskAttempt.id == latest_attempt_id)
        .values(status=status, finished_at=func.now(), status_details=status_details, output_log_path=log_path)
    )
    await session.execute(stmt)

    result = await session.execute(select(TaskAttempt.attempt_number).where(TaskAttempt.id == latest_attempt_id))
    row = result.first()
    if row is None:
        raise RuntimeError(f"Failed to get attempt number for task {task_id}")
    current_attempt = row[0]

    should_finish = status != "system_error" or current_attempt >= 2

    if should_finish:
        await session.execute(update(EvalTask).where(EvalTask.id == task_id).values(is_finished=True))
    else:
        new_attempt = TaskAttempt(task_id=task_id, attempt_number=current_attempt + 1, status="unprocessed")
        session.add(new_attempt)
        await session.flush()
        await session.execute(update(EvalTask).where(EvalTask.id == task_id).values(latest_attempt_id=new_attempt.id))


@with_db
async def get_latest_assigned_task_for_worker(assignee: str) -> EvalTaskRow | None:
    session = get_db()
    stmt = (
        _eval_task_row_stmt()
        .where(TaskAttempt.assignee == assignee, TaskAttempt.assigned_at.is_not(None))
        .order_by(TaskAttempt.assigned_at.desc())
        .limit(1)
    )
    row = (await session.execute(stmt)).first()
    return EvalTaskRow.from_task_and_attempt(*row) if row else None


@with_db
async def get_task_by_id(task_id: int) -> EvalTaskRow | None:
    session = get_db()
    stmt = _eval_task_row_stmt().where(EvalTask.id == task_id)
    row = (await session.execute(stmt)).first()
    return EvalTaskRow.from_task_and_attempt(*row) if row else None


@with_db
async def get_task_attempts(task_id: int) -> list[TaskAttemptRow]:
    session = get_db()
    attempts = list(
        (
            await session.execute(
                select(TaskAttempt).where(TaskAttempt.task_id == task_id).order_by(TaskAttempt.attempt_number.asc())
            )
        )
        .scalars()
        .all()
    )
    return [TaskAttemptRow.from_model(attempt) for attempt in attempts]


@with_db
async def get_all_tasks(
    limit: int = 500,
    statuses: list[TaskStatus] | None = None,
    git_hash: str | None = None,
) -> list[EvalTaskRow]:
    session = get_db()

    where_parts = []

    if statuses:
        where_parts.append(TaskAttempt.status.in_(statuses))

    if git_hash:
        where_parts.append(EvalTask.git_hash == git_hash)

    stmt = _eval_task_row_stmt()
    if where_parts:
        stmt = stmt.where(*where_parts)
    stmt = stmt.order_by(EvalTask.created_at.desc()).limit(limit)

    rows = (await session.execute(stmt)).all()
    return _rows_to_eval_task_rows(rows)


@with_db
async def get_tasks_paginated(
    page: int = 1,
    page_size: int = 50,
    status: str | None = None,
    assignee: str | None = None,
    user_id: str | None = None,
    command: str | None = None,
    created_at: str | None = None,
    assigned_at: str | None = None,
) -> tuple[list[EvalTaskRow], int]:
    session = get_db()

    where_parts = []

    if status:
        where_parts.append(TaskAttempt.status == status)

    if assignee:
        where_parts.append(TaskAttempt.assignee.ilike(f"%{assignee}%"))

    if user_id:
        where_parts.append(EvalTask.user_id.ilike(f"%{user_id}%"))

    if command:
        where_parts.append(EvalTask.command.ilike(f"%{command}%"))

    if created_at:
        where_parts.append(cast(EvalTask.created_at, String).ilike(f"%{created_at}%"))

    if assigned_at:
        where_parts.append(cast(TaskAttempt.assigned_at, String).ilike(f"%{assigned_at}%"))

    count_stmt = (
        select(func.count()).select_from(EvalTask).outerjoin(TaskAttempt, TaskAttempt.id == EvalTask.latest_attempt_id)
    )
    if where_parts:
        count_stmt = count_stmt.where(*where_parts)
    total_count: int = (await session.execute(count_stmt)).scalar_one()

    offset = (page - 1) * page_size

    stmt = _eval_task_row_stmt()
    if where_parts:
        stmt = stmt.where(*where_parts)
    stmt = stmt.order_by(EvalTask.created_at.desc()).limit(page_size).offset(offset)

    rows = (await session.execute(stmt)).all()
    return _rows_to_eval_task_rows(rows), total_count


@with_db
async def get_git_hashes_for_workers(assignees: list[str]) -> dict[str, list[str]]:
    if not assignees:
        return {}

    session = get_db()
    stmt = (
        select(TaskAttempt.assignee, EvalTask.git_hash)
        .distinct()
        .select_from(EvalTask)
        .join(TaskAttempt, TaskAttempt.id == EvalTask.latest_attempt_id)
        .where(TaskAttempt.assignee.in_(assignees))
    )
    rows = (await session.execute(stmt)).all()

    res: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        if row[1]:
            res[row[0]].append(row[1])
    return dict(res)
