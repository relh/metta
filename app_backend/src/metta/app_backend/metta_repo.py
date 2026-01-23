import logging
import uuid
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Literal

from psycopg import Connection
from psycopg.rows import class_row
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool, PoolTimeout
from pydantic import BaseModel, Field

from metta.app_backend.config import settings
from metta.app_backend.migrations import MIGRATIONS
from metta.app_backend.schema_manager import run_migrations

TaskStatus = Literal["unprocessed", "running", "canceled", "done", "error", "system_error"]
FinishedTaskStatus = Literal["done", "error", "canceled", "system_error"]


class TaskStatusUpdate(BaseModel):
    status: TaskStatus
    clear_assignee: bool = False
    status_details: dict[str, Any] = Field(default_factory=dict)


class EvalTaskRow(BaseModel):
    """Row model that matches the eval_tasks table with latest attempt data."""

    model_config = {"from_attributes": True}

    id: int
    command: str
    data_uri: str | None
    git_hash: str | None
    attributes: dict[str, Any]
    user_id: str
    created_at: datetime
    is_finished: bool
    latest_attempt_id: int | None

    # Fields from the latest attempt (populated via JOIN)
    # Note: attempt_number will be 0 for new tasks, status will be 'unprocessed'
    attempt_number: int | None = 0
    status: TaskStatus = "unprocessed"
    status_details: dict[str, Any] | None = None
    assigned_at: datetime | None = None
    assignee: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    output_log_path: str | None = None


class TaskAttemptRow(BaseModel):
    """Row model for task_attempts table."""

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


class SweepRow(BaseModel):
    id: uuid.UUID
    name: str
    project: str
    entity: str
    wandb_sweep_id: str
    state: str
    run_counter: int
    user_id: str
    created_at: datetime
    updated_at: datetime


logger = logging.getLogger(name="metta_repo")


class MettaRepo:
    def __init__(self, db_uri: str) -> None:
        self.db_uri = db_uri
        self._pool: AsyncConnectionPool | None = None
        # Run migrations synchronously during initialization
        if settings.RUN_MIGRATIONS:
            with Connection.connect(self.db_uri) as con:
                run_migrations(con, MIGRATIONS)

    async def _ensure_pool(self) -> AsyncConnectionPool:
        if self._pool is None:
            self._pool = AsyncConnectionPool(self.db_uri, min_size=2, max_size=20, open=False)
            await self._pool.open()
        return self._pool

    @asynccontextmanager
    async def connect(self):
        pool = await self._ensure_pool()
        try:
            async with pool.connection(timeout=5) as conn:
                yield conn
        except PoolTimeout as e:
            stats = pool.get_stats()
            logger.error(f"Error connecting to database: {e}. Pool stats: {stats}", exc_info=True)

            await pool.check()
            async with pool.connection() as conn:
                yield conn

    async def close(self) -> None:
        if self._pool:
            try:
                await self._pool.close()
            except RuntimeError:
                # Event loop might be closed, ignore
                pass

    async def create_eval_task(
        self,
        command: str,
        user_id: str,
        attributes: dict[str, Any],
        git_hash: str | None = None,
        data_uri: str | None = None,
    ) -> EvalTaskRow:
        async with self.connect() as con:
            # Insert the task
            result = await con.execute(
                """
                INSERT INTO eval_tasks (command, data_uri, git_hash, attributes, user_id)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
                """,
                (command, data_uri, git_hash, Jsonb(attributes), user_id),
            )
            row = await result.fetchone()
            if row is None:
                raise RuntimeError("Failed to create eval task")
            task_id = row[0]

            # Create the first attempt
            result2 = await con.execute(
                """
                INSERT INTO task_attempts (task_id, attempt_number, status)
                VALUES (%s, 0, 'unprocessed')
                RETURNING id
                """,
                (task_id,),
            )
            row2 = await result2.fetchone()
            if row2 is None:
                raise RuntimeError("Failed to create first attempt")
            attempt_id = row2[0]

            # Update the task with the latest_attempt_id
            await con.execute(
                """
                UPDATE eval_tasks
                SET latest_attempt_id = %s
                WHERE id = %s
                """,
                (attempt_id, task_id),
            )

            # Fetch and return the complete task directly within the same transaction
            async with con.cursor(row_factory=class_row(EvalTaskRow)) as cur:
                await cur.execute("SELECT * FROM eval_tasks_view WHERE id = %s", (task_id,))
                task = await cur.fetchone()
                if task is None:
                    raise RuntimeError("Failed to retrieve created task")
                return task

    async def get_available_tasks(self, limit: int = 200) -> list[EvalTaskRow]:
        async with self.connect() as con:
            async with con.cursor(row_factory=class_row(EvalTaskRow)) as cur:
                await cur.execute(
                    """
                    SELECT * FROM eval_tasks_view
                    WHERE status = 'unprocessed' AND assignee IS NULL AND is_finished = FALSE
                    ORDER BY created_at ASC
                    LIMIT %s
                    """,
                    (limit,),
                )
                return await cur.fetchall()

    async def claim_tasks(
        self,
        task_ids: list[int],
        assignee: str,
    ) -> list[int]:
        if not task_ids:
            return []

        async with self.connect() as con:
            # Update the latest attempt for each task
            result = await con.execute(
                """
                UPDATE task_attempts
                SET assignee = %s, assigned_at = NOW()
                WHERE id IN (
                    SELECT latest_attempt_id FROM eval_tasks
                    WHERE id = ANY(%s) AND is_finished = FALSE
                )
                AND status = 'unprocessed'
                AND assignee IS NULL
                RETURNING task_id
                """,
                (assignee, task_ids),
            )
            rows = await result.fetchall()
            return [row[0] for row in rows]

    async def get_claimed_tasks(self, assignee: str | None = None) -> list[EvalTaskRow]:
        async with self.connect() as con:
            async with con.cursor(row_factory=class_row(EvalTaskRow)) as cur:
                if assignee is not None:
                    await cur.execute(
                        """
                        SELECT * FROM eval_tasks_view
                        WHERE assignee = %s AND is_finished = FALSE
                        ORDER BY created_at ASC
                        """,
                        (assignee,),
                    )
                else:
                    await cur.execute(
                        """
                        SELECT * FROM eval_tasks_view
                        WHERE assignee IS NOT NULL AND is_finished = FALSE
                        ORDER BY created_at ASC
                        """
                    )
                return await cur.fetchall()

    async def start_task(self, task_id: int) -> None:
        async with self.connect() as con:
            await con.execute(
                """
                UPDATE task_attempts
                SET status = 'running', started_at = NOW()
                WHERE id = (SELECT latest_attempt_id FROM eval_tasks WHERE id = %s)
                """,
                (task_id,),
            )

    async def finish_task(
        self, task_id: int, status: FinishedTaskStatus, status_details: dict[str, Any], log_path: str | None = None
    ) -> None:
        async with self.connect() as con:
            # Update the current attempt
            await con.execute(
                """
                UPDATE task_attempts
                SET status = %s, finished_at = NOW(), status_details = %s, output_log_path = %s
                WHERE id = (SELECT latest_attempt_id FROM eval_tasks WHERE id = %s)
                """,
                (status, Jsonb(status_details), log_path, task_id),
            )

            # Get the current attempt number
            result = await con.execute(
                """
                SELECT attempt_number FROM task_attempts
                WHERE id = (SELECT latest_attempt_id FROM eval_tasks WHERE id = %s)
                """,
                (task_id,),
            )
            row = await result.fetchone()
            if row is None:
                raise RuntimeError(f"Failed to get attempt number for task {task_id}")
            current_attempt = row[0]

            # Check if we should mark the task as finished or create a new attempt
            should_finish = status != "system_error" or current_attempt >= 2  # 0, 1, 2 = 3 attempts

            if should_finish:
                # Mark the task as finished
                await con.execute(
                    """
                    UPDATE eval_tasks
                    SET is_finished = TRUE
                    WHERE id = %s
                    """,
                    (task_id,),
                )
            else:
                # Create a new attempt for retry
                await con.execute(
                    """
                    INSERT INTO task_attempts (task_id, attempt_number, status)
                    VALUES (%s, %s, 'unprocessed')
                    """,
                    (task_id, current_attempt + 1),
                )

                # Update latest_attempt_id
                await con.execute(
                    """
                    UPDATE eval_tasks
                    SET latest_attempt_id = (
                        SELECT id FROM task_attempts WHERE task_id = %s ORDER BY attempt_number DESC LIMIT 1
                    )
                    WHERE id = %s
                    """,
                    (task_id, task_id),
                )

    async def create_sweep(self, name: str, project: str, entity: str, wandb_sweep_id: str, user_id: str) -> uuid.UUID:
        """Create a new sweep."""
        async with self.connect() as con:
            result = await con.execute(
                """
                INSERT INTO sweeps (name, project, entity, wandb_sweep_id, user_id)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
                """,
                (name, project, entity, wandb_sweep_id, user_id),
            )
            row = await result.fetchone()
            if row is None:
                raise ValueError("Failed to create sweep")
            return row[0]

    async def get_sweep_by_name(self, name: str) -> SweepRow | None:
        """Get sweep by name."""
        async with self.connect() as con:
            async with con.cursor(row_factory=class_row(SweepRow)) as cur:
                await cur.execute(
                    """
                    SELECT id, name, project, entity, wandb_sweep_id, state, run_counter,
                           user_id, created_at, updated_at
                    FROM sweeps
                    WHERE name = %s
                    """,
                    (name,),
                )
                return await cur.fetchone()

    async def get_next_sweep_run_counter(self, sweep_id: uuid.UUID) -> int:
        """Atomically increment and return the next run counter for a sweep."""
        async with self.connect() as con:
            result = await con.execute(
                """
                UPDATE sweeps
                SET run_counter = run_counter + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                RETURNING run_counter
                """,
                (sweep_id,),
            )
            row = await result.fetchone()
            if row is None:
                raise ValueError(f"Sweep {sweep_id} not found")
            return row[0]

    async def get_latest_assigned_task_for_worker(self, assignee: str) -> EvalTaskRow | None:
        async with self.connect() as con:
            async with con.cursor(row_factory=class_row(EvalTaskRow)) as cur:
                await cur.execute(
                    """
                    SELECT * FROM eval_tasks_view
                    WHERE assignee = %s AND assigned_at IS NOT NULL
                    ORDER BY assigned_at DESC
                    LIMIT 1
                    """,
                    (assignee,),
                )
                return await cur.fetchone()

    async def get_task_by_id(self, task_id: int) -> EvalTaskRow | None:
        async with self.connect() as con:
            async with con.cursor(row_factory=class_row(EvalTaskRow)) as cur:
                await cur.execute("SELECT * FROM eval_tasks_view WHERE id = %s", (task_id,))
                return await cur.fetchone()

    async def get_task_attempts(self, task_id: int) -> list[TaskAttemptRow]:
        """Get all attempts for a task, ordered by attempt_number."""
        async with self.connect() as con:
            async with con.cursor(row_factory=class_row(TaskAttemptRow)) as cur:
                await cur.execute(
                    """
                    SELECT * FROM task_attempts
                    WHERE task_id = %s
                    ORDER BY attempt_number ASC
                    """,
                    (task_id,),
                )
                return await cur.fetchall()

    async def get_all_tasks(
        self,
        limit: int = 500,
        statuses: list[TaskStatus] | None = None,
        git_hash: str | None = None,
    ) -> list[EvalTaskRow]:
        async with self.connect() as con:
            # Build the WHERE clause dynamically
            where_conditions = []
            params = []

            if statuses:
                placeholders = ", ".join(["%s"] * len(statuses))
                where_conditions.append(f"status IN ({placeholders})")
                params.extend(statuses)

            if git_hash:
                where_conditions.append("git_hash = %s")
                params.append(git_hash)

            where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"
            params.append(limit)

            async with con.cursor(row_factory=class_row(EvalTaskRow)) as cur:
                await cur.execute(
                    f"""
                    SELECT * FROM eval_tasks_view
                    WHERE {where_clause}
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    params,
                )
                return await cur.fetchall()

    async def get_tasks_paginated(
        self,
        page: int = 1,
        page_size: int = 50,
        status: str | None = None,
        assignee: str | None = None,
        user_id: str | None = None,
        command: str | None = None,
        created_at: str | None = None,
        assigned_at: str | None = None,
    ) -> tuple[list[EvalTaskRow], int]:
        async with self.connect() as con:
            where_conditions = []
            params = []

            # Add text-based filters using ILIKE for case-insensitive substring search
            if status:
                # Use exact match for status since it's an enum-like field
                where_conditions.append("status = %s")
                params.append(status)

            if assignee:
                where_conditions.append("assignee ILIKE %s")
                params.append(f"%{assignee}%")

            if user_id:
                where_conditions.append("user_id ILIKE %s")
                params.append(f"%{user_id}%")

            if command:
                where_conditions.append("command ILIKE %s")
                params.append(f"%{command}%")

            if created_at:
                where_conditions.append("CAST(created_at AS TEXT) ILIKE %s")
                params.append(f"%{created_at}%")

            if assigned_at:
                where_conditions.append("CAST(assigned_at AS TEXT) ILIKE %s")
                params.append(f"%{assigned_at}%")

            where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"

            # Get total count
            count_query = f"""
                SELECT COUNT(*)
                FROM eval_tasks_view
                WHERE {where_clause}
            """
            count_result = await con.execute(count_query, params)
            result_row = await count_result.fetchone()
            total_count: int = result_row[0] if result_row else 0

            # Get paginated results
            offset = (page - 1) * page_size
            params.extend([page_size, offset])

            async with con.cursor(row_factory=class_row(EvalTaskRow)) as cur:
                await cur.execute(
                    f"""
                    SELECT * FROM eval_tasks_view
                    WHERE {where_clause}
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    params,
                )
                tasks = await cur.fetchall()

            return tasks, total_count

    async def get_git_hashes_for_workers(self, assignees: list[str]) -> dict[str, list[str]]:
        async with self.connect() as con:
            if not assignees:
                return {}

            # Use ANY() for proper list handling in PostgreSQL
            queryRes = await con.execute(
                """
                SELECT DISTINCT assignee, git_hash
                FROM eval_tasks_view
                WHERE assignee = ANY(%s)
                """,
                (assignees,),
            )
            rows = await queryRes.fetchall()
            res: dict[str, list[str]] = defaultdict(list)
            for row in rows:
                if row[1]:  # Only add non-null git hashes
                    res[row[0]].append(row[1])
            return res
