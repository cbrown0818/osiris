from datetime import datetime
from typing import Any
import os
import json
import asyncpg


DATABASE_URL = os.getenv("DATABASE_URL")


class MemoryError(Exception):
    pass


async def ensure_memory_table(conn) -> None:
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS memory (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMP NOT NULL,
            memory_type TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb
        )
    """)


async def save_memory(
    memory_type: str,
    title: str,
    content: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    if not DATABASE_URL:
        raise MemoryError("DATABASE_URL is not set.")

    conn = await asyncpg.connect(DATABASE_URL)

    try:
        await ensure_memory_table(conn)
        await conn.execute(
            """
            INSERT INTO memory
            (timestamp, memory_type, title, content, metadata)
            VALUES ($1, $2, $3, $4, $5)
            """,
            datetime.utcnow(),
            memory_type,
            title,
            content,
            json.dumps(metadata or {}),
        )
    finally:
        await conn.close()


async def get_recent_memories(limit: int = 25) -> list[dict[str, Any]]:
    if not DATABASE_URL:
        raise MemoryError("DATABASE_URL is not set.")

    limit = max(1, min(limit, 100))
    conn = await asyncpg.connect(DATABASE_URL)

    try:
        await ensure_memory_table(conn)
        rows = await conn.fetch(
            """
            SELECT id, timestamp, memory_type, title, content, metadata
            FROM memory
            ORDER BY timestamp DESC
            LIMIT $1
            """,
            limit,
        )

        memories = []
        for row in rows:
            item = dict(row)
            item["timestamp"] = item["timestamp"].isoformat()

            if isinstance(item.get("metadata"), str):
                try:
                    item["metadata"] = json.loads(item["metadata"])
                except Exception:
                    pass

            memories.append(item)

        return memories
    finally:
        await conn.close()
