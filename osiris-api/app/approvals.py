import json
import os
import uuid
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor


DATABASE_URL = os.getenv("DATABASE_URL")


def get_db_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


def init_approvals_table():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS approvals (
                    id UUID PRIMARY KEY,
                    status TEXT NOT NULL DEFAULT 'pending',
                    tool_name TEXT NOT NULL,
                    target TEXT,
                    action TEXT,
                    params JSONB NOT NULL DEFAULT '{}'::jsonb,
                    permission JSONB NOT NULL DEFAULT '{}'::jsonb,
                    result JSONB,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    decided_at TIMESTAMPTZ
                );
                """
            )

            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_approvals_status_created
                ON approvals (status, created_at DESC);
                """
            )

        conn.commit()


def create_approval(
    tool_name: str,
    params: dict[str, Any] | None = None,
    permission: dict[str, Any] | None = None,
    target: str | None = None,
    action: str | None = None,
) -> dict[str, Any]:
    init_approvals_table()

    approval_id = str(uuid.uuid4())
    params = params or {}
    permission = permission or {}

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO approvals
                (id, status, tool_name, target, action, params, permission)
                VALUES (%s, 'pending', %s, %s, %s, %s::jsonb, %s::jsonb)
                RETURNING *;
                """,
                (
                    approval_id,
                    tool_name,
                    target,
                    action,
                    json.dumps(params),
                    json.dumps(permission),
                ),
            )
            row = cur.fetchone()
        conn.commit()

    return dict(row)


def list_pending_approvals(limit: int = 50) -> list[dict[str, Any]]:
    init_approvals_table()
    limit = max(1, min(limit, 200))

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM approvals
                WHERE status = 'pending'
                ORDER BY created_at DESC
                LIMIT %s;
                """,
                (limit,),
            )
            rows = cur.fetchall()

    return [dict(row) for row in rows]


def get_approval(approval_id: str) -> dict[str, Any] | None:
    init_approvals_table()

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM approvals
                WHERE id = %s;
                """,
                (approval_id,),
            )
            row = cur.fetchone()

    return dict(row) if row else None


def mark_approval_decision(
    approval_id: str,
    status: str,
    result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    init_approvals_table()

    if status not in ["approved", "denied", "executed", "failed"]:
        raise ValueError("status must be approved, denied, executed, or failed")

    result = result or {}

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE approvals
                SET status = %s,
                    result = %s::jsonb,
                    decided_at = NOW()
                WHERE id = %s
                RETURNING *;
                """,
                (
                    status,
                    json.dumps(result),
                    approval_id,
                ),
            )
            row = cur.fetchone()
        conn.commit()

    if not row:
        raise ValueError(f"Unknown approval id: {approval_id}")

    return dict(row)
