"""SQL query routes for self-service database access."""

import asyncio
import json
import logging
import time
from typing import Any

from fastapi import APIRouter, HTTPException
from psycopg import errors as pg_errors
from pydantic import BaseModel
from sqlalchemy import text

from metta.app_backend.anthropic_client import (
    AnthropicConnectionError,
    AnthropicHTTPError,
    AnthropicResponseFormatError,
    AnthropicTimeoutError,
    request_bedrock_message,
)
from metta.app_backend.auth import SoftmaxUser
from metta.app_backend.database import db_session
from metta.app_backend.route_logger import timed_route

query_logger = logging.getLogger("db_performance")


class SQLQueryRequest(BaseModel):
    query: str


class SQLQueryResponse(BaseModel):
    columns: list[str]
    rows: list[list[Any]]
    row_count: int


class TableInfo(BaseModel):
    table_name: str
    column_count: int
    row_count: int


class TableSchema(BaseModel):
    table_name: str
    columns: list[dict[str, Any]]


class AIQueryRequest(BaseModel):
    description: str


class AIQueryResponse(BaseModel):
    query: str


def create_sql_router() -> APIRouter:
    router = APIRouter(prefix="/sql", tags=["sql"])

    @router.get("/tables")
    @timed_route("list_tables")
    async def list_tables(user: SoftmaxUser) -> list[TableInfo]:
        try:
            async with db_session(read_only=True) as session:
                tables_query = text("""
                    SELECT
                        t.table_name,
                        COUNT(c.column_name) as column_count
                    FROM information_schema.tables t
                    LEFT JOIN information_schema.columns c
                        ON t.table_name = c.table_name
                        AND t.table_schema = c.table_schema
                    WHERE t.table_schema = 'public'
                        AND t.table_type = 'BASE TABLE'
                        AND t.table_name != 'schema_migrations'
                    GROUP BY t.table_name
                    ORDER BY t.table_name
                """)

                start = time.time()
                result = await session.execute(tables_query)
                tables = result.fetchall()
                query_logger.info(f"list_tables_metadata completed in {time.time() - start:.3f}s")

                table_info = []
                for table_name, column_count in tables:
                    row_count_query = text("SELECT reltuples::bigint AS estimate FROM pg_class where relname = :name")
                    start = time.time()
                    row_count_result = await session.execute(row_count_query, {"name": table_name})
                    query_logger.info(f"count_rows_{table_name} completed in {time.time() - start:.3f}s")
                    row = row_count_result.fetchone()
                    row_count = row[0] if row else 0

                    table_info.append(TableInfo(table_name=table_name, column_count=column_count, row_count=row_count))

                return table_info

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error listing tables: {str(e)}") from e

    @router.get("/tables/{table_name}/schema")
    @timed_route("get_table_schema")
    async def get_table_schema(table_name: str, user: SoftmaxUser) -> TableSchema:
        try:
            if table_name == "schema_migrations":
                raise HTTPException(status_code=403, detail="Access to schema_migrations table is not allowed")

            async with db_session(read_only=True) as session:
                schema_query = text("""
                    SELECT
                        column_name,
                        data_type,
                        is_nullable,
                        column_default,
                        character_maximum_length
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                        AND table_name = :table_name
                    ORDER BY ordinal_position
                """)

                start = time.time()
                result = await session.execute(schema_query, {"table_name": table_name})
                columns = result.fetchall()
                query_logger.info(f"get_schema_{table_name} completed in {time.time() - start:.3f}s")

                if not columns:
                    raise HTTPException(status_code=404, detail=f"Table '{table_name}' not found")

                column_info = []
                for col in columns:
                    column_info.append(
                        {
                            "name": col[0],
                            "type": col[1],
                            "nullable": col[2] == "YES",
                            "default": col[3],
                            "max_length": col[4],
                        }
                    )

                return TableSchema(table_name=table_name, columns=column_info)

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error getting table schema: {str(e)}") from e

    @router.post("/query")
    @timed_route("execute_sql_query")
    async def execute_query(request: SQLQueryRequest, user: SoftmaxUser) -> SQLQueryResponse:
        try:
            query_lower = request.query.lower()
            if "schema_migrations" in query_lower:
                raise HTTPException(status_code=403, detail="Access to schema_migrations table is not allowed")

            write_keywords = ["insert", "update", "delete", "drop", "create", "alter", "truncate", "grant", "revoke"]
            first_word = query_lower.strip().split()[0] if query_lower.strip() else ""
            if first_word in write_keywords:
                raise HTTPException(
                    status_code=403, detail="Only read-only queries are allowed. Write operations are not permitted."
                )

            async def run_query():
                async with db_session(read_only=True) as session:
                    await session.execute(text("SET statement_timeout = '20s'"))
                    result = await session.execute(text(request.query))

                    if not result.returns_rows:  # type: ignore[union-attr]
                        return SQLQueryResponse(columns=[], rows=[], row_count=0)

                    columns = list(result.keys()) if result.keys() else []
                    rows = result.fetchmany(1000)
                    rows_list = [list(row) for row in rows]

                    return SQLQueryResponse(columns=columns, rows=rows_list, row_count=len(rows_list))

            return await asyncio.wait_for(run_query(), timeout=21.0)

        except asyncio.TimeoutError as e:
            raise HTTPException(status_code=408, detail="Query execution timed out after 20 seconds") from e
        except pg_errors.QueryCanceled as e:
            raise HTTPException(status_code=408, detail="Query execution timed out after 20 seconds") from e
        except pg_errors.SyntaxError as e:
            raise HTTPException(status_code=400, detail=f"SQL syntax error: {str(e)}") from e
        except pg_errors.UndefinedTable as e:
            raise HTTPException(status_code=400, detail=f"Table not found: {str(e)}") from e
        except pg_errors.UndefinedColumn as e:
            raise HTTPException(status_code=400, detail=f"Column not found: {str(e)}") from e
        except pg_errors.InsufficientPrivilege as e:
            raise HTTPException(status_code=403, detail=f"Insufficient privileges: {str(e)}") from e
        except HTTPException:
            raise
        except Exception as e:
            error_type = type(e).__name__
            raise HTTPException(status_code=500, detail=f"Query execution failed ({error_type}): {str(e)}") from e

    @router.post("/generate-query")
    @timed_route("generate_ai_query")
    async def generate_ai_query(request: AIQueryRequest, user: SoftmaxUser) -> AIQueryResponse:
        """Generate a SQL query from natural language description using Claude."""
        # Fetch all table schemas in parallel
        tables = await list_tables(user)
        schemas = await asyncio.gather(*[get_table_schema(table.table_name, user) for table in tables])

        # Build schema description
        schema_lines = []
        for schema in schemas:
            schema_lines.append(f"Table: {schema.table_name}")
            for col in schema.columns:
                col_desc = f"    {col['name']} {col['type']}"
                if not col["nullable"]:
                    col_desc += " NOT NULL"
                if col["default"]:
                    col_desc += f" DEFAULT {col['default']}"
                schema_lines.append(col_desc)
            schema_lines.append("")  # Empty line between tables

        schema_description = "\n".join(schema_lines)

        prompt = (
            f"You are a SQL query generator. Given the following database schema "
            f"and a user's description, generate a SQL query that answers their request.\n\n"
            f"Database Schema:\n{schema_description}\n"
            f"User's request: {request.description}\n\n"
            f"Please respond with ONLY the SQL query, no explanation or markdown. "
            f"The query should be ready to execute."
        )

        try:
            generated_query = await request_bedrock_message(
                prompt=prompt,
                model="us.anthropic.claude-opus-4-20250514-v1:0",
                max_tokens=1000,
                timeout=30.0,
            )
            return AIQueryResponse(query=generated_query)
        except AnthropicTimeoutError as e:
            raise HTTPException(status_code=408, detail="Request to Claude API timed out") from e
        except AnthropicHTTPError as e:
            detail = f"API request failed: {e.status_code}"
            if e.response_text:
                try:
                    error_data = json.loads(e.response_text)
                    detail = error_data.get("error", {}).get("message", detail)
                except ValueError:
                    pass
            raise HTTPException(status_code=e.status_code, detail=detail) from e
        except AnthropicConnectionError as e:
            raise HTTPException(status_code=503, detail=f"Failed to connect to Claude API: {str(e)}") from e
        except AnthropicResponseFormatError as e:
            raise HTTPException(status_code=502, detail="Unexpected Claude API response format") from e
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to generate query: {str(e)}") from e

    return router
