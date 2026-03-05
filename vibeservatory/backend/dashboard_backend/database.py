"""Dashboard DB wiring: dedicated URI + forced read-only sessions + write guard."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

import metta.app_backend.config as app_config
import metta.app_backend.database as app_db
from vibeservatory.backend.dashboard_backend.config import settings

_ORIGINAL_DB_SESSION = app_db.db_session
_CONFIGURED = False

_WRITE_PREFIXES = {
    "insert",
    "update",
    "delete",
    "alter",
    "drop",
    "create",
    "truncate",
    "grant",
    "revoke",
    "merge",
    "copy",
    "vacuum",
    "analyze",
}
_ALLOWED_NON_READ_PREFIXES = {"select", "with", "show", "set", "values", "explain", "commit", "rollback"}


def _first_sql_token(statement: str) -> str:
    sql = statement.lstrip()

    while sql.startswith("--"):
        nl = sql.find("\n")
        if nl == -1:
            return ""
        sql = sql[nl + 1 :].lstrip()

    while sql.startswith("/*"):
        end = sql.find("*/")
        if end == -1:
            return ""
        sql = sql[end + 2 :].lstrip()

    return sql.split(None, 1)[0].lower() if sql else ""


def _write_guard(
    conn,  # noqa: ANN001
    cursor,  # noqa: ANN001
    statement: str,
    parameters,  # noqa: ANN001
    context,  # noqa: ANN001
    executemany: bool,  # noqa: ANN001
) -> None:
    token = _first_sql_token(statement)
    if not token:
        return
    if token in _WRITE_PREFIXES:
        raise RuntimeError(f"Write statement blocked by dashboard read-only guard: {token.upper()}")
    if token not in _ALLOWED_NON_READ_PREFIXES:
        # Conservative default: block unknown mutating commands.
        raise RuntimeError(f"Potentially mutating statement blocked by dashboard guard: {token.upper()}")


def _validate_readonly_uri(uri: str) -> None:
    parsed = urlparse(uri)
    if parsed.username == "metta":
        raise RuntimeError("Dashboard DB URI must not use writer username 'metta'.")
    hostname = (parsed.hostname or "").lower()
    if hostname and hostname not in {"localhost", "127.0.0.1"} and "-pg-ro." not in hostname:
        raise RuntimeError("Dashboard DB URI must target the read-replica endpoint (expected '-pg-ro.' in hostname).")


@asynccontextmanager
async def _forced_readonly_db_session(read_only: bool = True) -> AsyncGenerator[AsyncSession, None]:
    del read_only
    async with _ORIGINAL_DB_SESSION(read_only=True) as session:
        yield session


def configure_dashboard_db() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    readonly_uri = settings.STATS_DB_READ_ONLY_URI
    _validate_readonly_uri(readonly_uri)

    # Point shared app_backend query/model stack at the dashboard-specific (read-only role) URI.
    app_config.settings.STATS_DB_READ_ONLY_URI = readonly_uri

    # Reset engine/session factory in case this process imported app_backend DB earlier.
    app_db._engine = None
    app_db._read_only_engine = None
    app_db._session_factory = None
    app_db._read_only_session_factory = None

    # Force all app_backend query decorators to use read-only sessions in this process.
    app_db.db_session = _forced_readonly_db_session

    engine = app_db._get_engine(read_only=True)
    if not getattr(engine.sync_engine, "_dashboard_write_guard_installed", False):
        event.listen(engine.sync_engine, "before_cursor_execute", _write_guard)
        engine.sync_engine._dashboard_write_guard_installed = True

    _CONFIGURED = True


@asynccontextmanager
async def db_session(read_only: bool = True) -> AsyncGenerator[AsyncSession, None]:
    del read_only
    configure_dashboard_db()
    async with app_db.db_session(read_only=True) as session:
        yield session
