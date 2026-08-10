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


def claim_approval_for_execution(
    approval_id: str,
    *,
    tool_name: str,
    target: str,
    action: str,
    request_hash: str,
) -> dict[str, Any]:
    """
    Atomically consume an approved request for one execution.

    The approval must match the exact capability, target, action,
    and request fingerprint. Once claimed, its status becomes
    'executing' so the same approval cannot be reused concurrently.
    """
    init_approvals_table()

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM approvals
                WHERE id = %s
                FOR UPDATE;
                """,
                (approval_id,),
            )

            row = cur.fetchone()

            if not row:
                raise ValueError(
                    f"Unknown approval id: {approval_id}"
                )

            approval = dict(row)

            if approval.get("status") != "approved":
                raise ValueError(
                    "Approval is not in approved state. "
                    f"Current status: {approval.get('status')}"
                )

            if approval.get("tool_name") != tool_name:
                raise ValueError(
                    "Approval tool does not match request."
                )

            if approval.get("target") != target:
                raise ValueError(
                    "Approval target does not match request."
                )

            if approval.get("action") != action:
                raise ValueError(
                    "Approval action does not match request."
                )

            permission = approval.get("permission") or {}

            if permission.get("request_hash") != request_hash:
                raise ValueError(
                    "Approval request fingerprint does not match."
                )

            cur.execute(
                """
                UPDATE approvals
                SET status = 'executing'
                WHERE id = %s
                RETURNING *;
                """,
                (approval_id,),
            )

            claimed = cur.fetchone()

        conn.commit()

    return dict(claimed)



def decide_pending_approval(
    approval_id: str,
    status: str,
    result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Atomically transition one pending approval to approved or denied.

    Existing executed, executing, failed, denied, or approved records
    cannot be moved backward into another decision state.
    """
    init_approvals_table()

    if status not in {
        "approved",
        "denied",
    }:
        raise ValueError(
            "status must be approved or denied"
        )

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
                  AND status = 'pending'
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

    if row:
        return dict(row)

    existing = get_approval(
        approval_id
    )

    if not existing:
        raise ValueError(
            f"Unknown approval id: {approval_id}"
        )

    raise ValueError(
        "Approval is not pending. "
        f"Current status: {existing.get('status')}"
    )
