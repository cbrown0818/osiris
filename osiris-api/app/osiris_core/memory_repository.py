from __future__ import annotations

import json
import os
from collections.abc import (
    Awaitable,
    Callable,
)
from typing import Any
from uuid import UUID

from .memory_models import (
    MemoryKind,
    MemoryRecord,
    MemoryStatus,
)
from .memory_store import (
    MEMORY_TABLE,
    memory_record_from_db,
    memory_record_to_db,
)


ConnectFunction = Callable[
    [str],
    Awaitable[Any],
]


class MemoryRepositoryError(
    RuntimeError
):
    """Canonical memory persistence error."""


class MemoryNotFoundError(
    MemoryRepositoryError
):
    """Requested canonical memory does not exist."""


class MemoryStateConflictError(
    MemoryRepositoryError
):
    """Requested memory lifecycle change is invalid."""


_MEMORY_COLUMNS = """
id,
kind,
content,
title,
status,
source_type,
source_ref,
confidence,
importance,
sensitivity,
retention,
subject_entity_id,
superseded_by_id,
created_at,
updated_at,
observed_at,
valid_from,
valid_until,
metadata,
fingerprint
""".strip()


def _normalize_uuid(
    value: str,
) -> str:
    try:
        return str(
            UUID(
                str(value)
            )
        )
    except Exception as exc:
        raise ValueError(
            "memory id must be a valid UUID"
        ) from exc


def _normalize_fingerprint(
    value: str,
) -> str:
    if not isinstance(
        value,
        str,
    ):
        raise TypeError(
            "memory fingerprint must be a string"
        )

    normalized = (
        value
        .strip()
        .lower()
    )

    if (
        len(normalized) != 64
        or any(
            character
            not in "0123456789abcdef"
            for character in normalized
        )
    ):
        raise ValueError(
            "memory fingerprint must be "
            "64 lowercase hexadecimal characters"
        )

    return normalized


def _normalize_limit(
    value: int,
) -> int:
    if (
        isinstance(
            value,
            bool,
        )
        or not isinstance(
            value,
            int,
        )
        or value < 1
        or value > 500
    ):
        raise ValueError(
            "limit must be between 1 and 500"
        )

    return value


def _normalize_offset(
    value: int,
) -> int:
    if (
        isinstance(
            value,
            bool,
        )
        or not isinstance(
            value,
            int,
        )
        or value < 0
    ):
        raise ValueError(
            "offset must be zero or greater"
        )

    return value


class PostgresMemoryRepository:
    """
    Canonical PostgreSQL persistence boundary
    for OSIRIS Memory Core.

    PostgreSQL remains authoritative.

    This repository does not write to Qdrant
    or any legacy memory store.
    """

    def __init__(
        self,
        database_url: str | None = None,
        *,
        connect: (
            ConnectFunction | None
        ) = None,
    ) -> None:
        if database_url is None:
            database_url = os.getenv(
                "DATABASE_URL",
                "",
            )

        self._database_url = (
            database_url.strip()
        )

        self._connect_function = connect

    async def _open(
        self,
    ) -> Any:
        if not self._database_url:
            raise MemoryRepositoryError(
                "DATABASE_URL is not configured"
            )

        if (
            self._connect_function
            is not None
        ):
            return await (
                self._connect_function(
                    self._database_url
                )
            )

        try:
            import asyncpg
        except ImportError as exc:
            raise MemoryRepositoryError(
                "asyncpg is required for "
                "PostgreSQL memory persistence"
            ) from exc

        return await asyncpg.connect(
            self._database_url
        )

    async def _insert_on_connection(
        self,
        connection: Any,
        record: MemoryRecord,
    ) -> MemoryRecord:
        data = memory_record_to_db(
            record
        )

        metadata_json = json.dumps(
            data["metadata"],
            ensure_ascii=False,
            sort_keys=True,
            separators=(
                ",",
                ":",
            ),
        )

        sql = f"""
        INSERT INTO {MEMORY_TABLE} (
            {_MEMORY_COLUMNS}
        )
        VALUES (
            $1::uuid,
            $2,
            $3,
            $4,
            $5,
            $6,
            $7,
            $8,
            $9,
            $10,
            $11,
            $12,
            $13::uuid,
            $14,
            $15,
            $16,
            $17,
            $18,
            $19::jsonb,
            $20
        )
        RETURNING
            {_MEMORY_COLUMNS};
        """

        row = await connection.fetchrow(
            sql,
            data["id"],
            data["kind"],
            data["content"],
            data["title"],
            data["status"],
            data["source_type"],
            data["source_ref"],
            data["confidence"],
            data["importance"],
            data["sensitivity"],
            data["retention"],
            data["subject_entity_id"],
            data["superseded_by_id"],
            data["created_at"],
            data["updated_at"],
            data["observed_at"],
            data["valid_from"],
            data["valid_until"],
            metadata_json,
            data["fingerprint"],
        )

        if row is None:
            raise MemoryRepositoryError(
                "memory insert returned no row"
            )

        return memory_record_from_db(
            row
        )

    async def _current_status(
        self,
        connection: Any,
        memory_id: str,
    ) -> MemoryStatus | None:
        row = await connection.fetchrow(
            f"""
            SELECT status
            FROM {MEMORY_TABLE}
            WHERE id = $1::uuid;
            """,
            memory_id,
        )

        if row is None:
            return None

        return MemoryStatus(
            row["status"]
        )

    async def create(
        self,
        record: MemoryRecord,
    ) -> MemoryRecord:
        if not isinstance(
            record,
            MemoryRecord,
        ):
            raise TypeError(
                "record must be a MemoryRecord"
            )

        connection = await self._open()

        try:
            return await (
                self._insert_on_connection(
                    connection,
                    record,
                )
            )
        finally:
            await connection.close()

    async def get(
        self,
        memory_id: str,
    ) -> MemoryRecord | None:
        memory_id = _normalize_uuid(
            memory_id
        )

        sql = f"""
        SELECT
            {_MEMORY_COLUMNS}
        FROM {MEMORY_TABLE}
        WHERE id = $1::uuid;
        """

        connection = await self._open()

        try:
            row = await connection.fetchrow(
                sql,
                memory_id,
            )

            if row is None:
                return None

            return memory_record_from_db(
                row
            )
        finally:
            await connection.close()

    async def list(
        self,
        *,
        kind: (
            MemoryKind | str | None
        ) = None,
        status: (
            MemoryStatus | str | None
        ) = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[MemoryRecord]:
        limit = _normalize_limit(
            limit
        )

        offset = _normalize_offset(
            offset
        )

        kind_value = (
            MemoryKind(kind).value
            if kind is not None
            else None
        )

        status_value = (
            MemoryStatus(status).value
            if status is not None
            else None
        )

        sql = f"""
        SELECT
            {_MEMORY_COLUMNS}
        FROM {MEMORY_TABLE}
        WHERE (
            $1::text IS NULL
            OR kind = $1
        )
        AND (
            $2::text IS NULL
            OR status = $2
        )
        ORDER BY
            created_at DESC,
            id DESC
        LIMIT $3
        OFFSET $4;
        """

        connection = await self._open()

        try:
            rows = await connection.fetch(
                sql,
                kind_value,
                status_value,
                limit,
                offset,
            )

            return [
                memory_record_from_db(
                    row
                )
                for row in rows
            ]
        finally:
            await connection.close()

    async def find_by_fingerprint(
        self,
        fingerprint: str,
        *,
        status: (
            MemoryStatus | str | None
        ) = None,
        limit: int = 20,
    ) -> list[MemoryRecord]:
        fingerprint = (
            _normalize_fingerprint(
                fingerprint
            )
        )

        limit = _normalize_limit(
            limit
        )

        status_value = (
            MemoryStatus(status).value
            if status is not None
            else None
        )

        sql = f"""
        SELECT
            {_MEMORY_COLUMNS}
        FROM {MEMORY_TABLE}
        WHERE fingerprint = $1
        AND (
            $2::text IS NULL
            OR status = $2
        )
        ORDER BY
            created_at DESC,
            id DESC
        LIMIT $3;
        """

        connection = await self._open()

        try:
            rows = await connection.fetch(
                sql,
                fingerprint,
                status_value,
                limit,
            )

            return [
                memory_record_from_db(
                    row
                )
                for row in rows
            ]
        finally:
            await connection.close()

    async def invalidate(
        self,
        memory_id: str,
    ) -> MemoryRecord:
        memory_id = _normalize_uuid(
            memory_id
        )

        sql = f"""
        UPDATE {MEMORY_TABLE}
        SET
            status = 'invalidated',
            superseded_by_id = NULL,
            updated_at = NOW()
        WHERE id = $1::uuid
        AND status = 'active'
        RETURNING
            {_MEMORY_COLUMNS};
        """

        connection = await self._open()

        try:
            row = await connection.fetchrow(
                sql,
                memory_id,
            )

            if row is not None:
                return memory_record_from_db(
                    row
                )

            status = await (
                self._current_status(
                    connection,
                    memory_id,
                )
            )

            if status is None:
                raise MemoryNotFoundError(
                    "memory does not exist"
                )

            raise MemoryStateConflictError(
                "only active memory may be "
                "invalidated; current status "
                f"is {status.value}"
            )
        finally:
            await connection.close()

    async def supersede(
        self,
        memory_id: str,
        replacement: MemoryRecord,
    ) -> tuple[
        MemoryRecord,
        MemoryRecord,
    ]:
        memory_id = _normalize_uuid(
            memory_id
        )

        if not isinstance(
            replacement,
            MemoryRecord,
        ):
            raise TypeError(
                "replacement must be "
                "a MemoryRecord"
            )

        if replacement.id == memory_id:
            raise ValueError(
                "replacement memory must "
                "have a different id"
            )

        if (
            replacement.status
            != MemoryStatus.ACTIVE
        ):
            raise ValueError(
                "replacement memory must "
                "be active"
            )

        connection = await self._open()

        try:
            async with (
                connection.transaction()
            ):
                current_row = (
                    await connection.fetchrow(
                        f"""
                        SELECT
                            {_MEMORY_COLUMNS}
                        FROM {MEMORY_TABLE}
                        WHERE id = $1::uuid
                        FOR UPDATE;
                        """,
                        memory_id,
                    )
                )

                if current_row is None:
                    raise MemoryNotFoundError(
                        "memory does not exist"
                    )

                current = (
                    memory_record_from_db(
                        current_row
                    )
                )

                if (
                    current.status
                    != MemoryStatus.ACTIVE
                ):
                    raise (
                        MemoryStateConflictError(
                            "only active memory "
                            "may be superseded; "
                            "current status is "
                            f"{current.status.value}"
                        )
                    )

                created_replacement = (
                    await self
                    ._insert_on_connection(
                        connection,
                        replacement,
                    )
                )

                superseded_row = (
                    await connection.fetchrow(
                        f"""
                        UPDATE {MEMORY_TABLE}
                        SET
                            status =
                                'superseded',
                            superseded_by_id =
                                $2::uuid,
                            updated_at = NOW()
                        WHERE id = $1::uuid
                        AND status = 'active'
                        RETURNING
                            {_MEMORY_COLUMNS};
                        """,
                        memory_id,
                        replacement.id,
                    )
                )

                if superseded_row is None:
                    raise (
                        MemoryStateConflictError(
                            "memory state changed "
                            "during supersession"
                        )
                    )

                superseded = (
                    memory_record_from_db(
                        superseded_row
                    )
                )

            return (
                superseded,
                created_replacement,
            )
        finally:
            await connection.close()
