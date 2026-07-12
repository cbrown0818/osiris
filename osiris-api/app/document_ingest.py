from pathlib import Path
from datetime import datetime
from typing import Any
import os
import json
import uuid
import asyncpg
import httpx
from pypdf import PdfReader
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct


DATABASE_URL = os.getenv("DATABASE_URL")
PROJECT_ROOT = Path("/workspace").resolve()

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")
QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY") or os.getenv("QDRANT__SERVICE__API_KEY")

COLLECTION = "lilith_documents"
EMBED_MODEL = "nomic-embed-text:latest"
VECTOR_SIZE = 768

ALLOWED_DOC_EXTENSIONS = {".pdf", ".txt", ".md"}


class DocumentIngestError(Exception):
    pass


def qdrant_client() -> QdrantClient:
    return QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)


def ensure_collection() -> None:
    client = qdrant_client()
    collections = client.get_collections().collections
    names = {c.name for c in collections}

    if COLLECTION not in names:
        client.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )


def safe_document_path(relative_path: str) -> Path:
    relative_path = relative_path.strip().lstrip("/")
    path = (PROJECT_ROOT / relative_path).resolve()

    if not str(path).startswith(str(PROJECT_ROOT)):
        raise DocumentIngestError("Path escapes project root.")
    if not path.exists():
        raise DocumentIngestError(f"Document does not exist: {relative_path}")
    if not path.is_file():
        raise DocumentIngestError(f"Path is not a file: {relative_path}")
    if path.suffix.lower() not in ALLOWED_DOC_EXTENSIONS:
        raise DocumentIngestError(f"Unsupported document type: {path.suffix}")

    return path


def extract_text(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        reader = PdfReader(str(path))
        return "\n\n".join((page.extract_text() or "") for page in reader.pages).strip()

    return path.read_text(encoding="utf-8", errors="replace")


def is_low_quality_chunk(chunk: str) -> bool:
    lowered = chunk.lower()

    junk_markers = [
        "bibliography",
        "references",
        "isbn",
        "cit. on p.",
        "visited on",
        "doi:",
        "url:https://",
        "url: https://",
        "license",
        "report repository",
        "no releases published",
        "no packages published",
        "table of contents",
    ]

    marker_hits = sum(1 for marker in junk_markers if marker in lowered)

    if marker_hits >= 2:
        return True

    # Reject chunks that are mostly dotted table-of-contents lines.
    dot_ratio = chunk.count(".") / max(len(chunk), 1)
    if dot_ratio > 0.08 and "summary" in lowered and len(chunk) > 500:
        return True

    return False


def chunk_text(text: str, chunk_size: int = 1800, overlap: int = 200) -> list[str]:
    text = text.strip()
    if not text:
        return []

    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end].strip()
        if chunk and not is_low_quality_chunk(chunk):
            chunks.append(chunk)
        start = end - overlap

    return chunks


async def embed_text(text: str) -> list[float]:
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{OLLAMA_URL}/api/embeddings",
            json={
                "model": EMBED_MODEL,
                "prompt": text,
            },
        )
        response.raise_for_status()
        data = response.json()

    embedding = data.get("embedding")
    if not embedding:
        raise DocumentIngestError("Ollama returned no embedding.")

    return embedding


async def ensure_document_table(conn) -> None:
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS document_chunks (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMP NOT NULL,
            source_path TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            content TEXT NOT NULL,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb
        )
    """)

    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_document_chunks_source
        ON document_chunks(source_path)
    """)


async def ingest_document(relative_path: str) -> dict[str, Any]:
    if not DATABASE_URL:
        raise DocumentIngestError("DATABASE_URL is not set.")

    ensure_collection()

    path = safe_document_path(relative_path)
    source_path = str(path.relative_to(PROJECT_ROOT))
    text = extract_text(path)

    if not text:
        raise DocumentIngestError("No text could be extracted from document.")

    chunks = chunk_text(text)

    conn = await asyncpg.connect(DATABASE_URL)
    client = qdrant_client()

    try:
        await ensure_document_table(conn)
        await conn.execute("DELETE FROM document_chunks WHERE source_path = $1", source_path)

        old_points, _ = client.scroll(
            collection_name=COLLECTION,
            scroll_filter={
                "must": [
                    {
                        "key": "source_path",
                        "match": {"value": source_path}
                    }
                ]
            },
            limit=10000,
        )

        if old_points:
            client.delete(
                collection_name=COLLECTION,
                points_selector=[p.id for p in old_points],
            )

        points = []

        for index, chunk in enumerate(chunks):
            row = await conn.fetchrow(
                """
                INSERT INTO document_chunks
                (timestamp, source_path, chunk_index, content, metadata)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id
                """,
                datetime.utcnow(),
                source_path,
                index,
                chunk,
                json.dumps({
                    "filename": path.name,
                    "extension": path.suffix.lower(),
                    "size_bytes": path.stat().st_size,
                }),
            )

            embedding = await embed_text(chunk)

            points.append(
                PointStruct(
                    id=str(uuid.uuid4()),
                    vector=embedding,
                    payload={
                        "db_id": row["id"],
                        "source_path": source_path,
                        "chunk_index": index,
                        "preview": chunk[:500],
                    },
                )
            )

            if len(points) >= 32:
                client.upsert(collection_name=COLLECTION, points=points)
                points = []

        if points:
            client.upsert(collection_name=COLLECTION, points=points)

        return {
            "source_path": source_path,
            "chunks": len(chunks),
            "characters": len(text),
            "semantic_indexed": True,
            "collection": COLLECTION,
        }
    finally:
        await conn.close()


async def search_documents(query: str, limit: int = 10) -> dict[str, Any]:
    if not DATABASE_URL:
        raise DocumentIngestError("DATABASE_URL is not set.")

    query = query.strip()
    if not query:
        raise DocumentIngestError("Search query cannot be empty.")

    limit = max(1, min(limit, 50))

    ensure_collection()
    embedding = await embed_text(query)

    client = qdrant_client()
    response = client.query_points(
        collection_name=COLLECTION,
        query=embedding,
        limit=limit,
    )

    hits = response.points

    results = []
    for hit in hits:
        payload = hit.payload or {}
        results.append({
            "score": hit.score,
            "source_path": payload.get("source_path"),
            "chunk_index": payload.get("chunk_index"),
            "db_id": payload.get("db_id"),
            "preview": payload.get("preview"),
        })

    return {
        "query": query,
        "count": len(results),
        "mode": "semantic_qdrant",
        "results": results,
    }


async def get_latest_document() -> dict[str, Any] | None:
    if not DATABASE_URL:
        raise DocumentIngestError("DATABASE_URL is not set.")

    conn = await asyncpg.connect(DATABASE_URL)

    try:
        await ensure_document_table(conn)

        row = await conn.fetchrow(
            """
            SELECT source_path, MAX(timestamp) AS latest_time, COUNT(*) AS chunks
            FROM document_chunks
            GROUP BY source_path
            ORDER BY latest_time DESC
            LIMIT 1
            """
        )

        if not row:
            return None

        return dict(row)
    finally:
        await conn.close()


async def get_document_intro_chunks(source_path: str, limit: int = 5) -> dict[str, Any]:
    if not DATABASE_URL:
        raise DocumentIngestError("DATABASE_URL is not set.")

    limit = max(1, min(limit, 20))
    conn = await asyncpg.connect(DATABASE_URL)

    try:
        await ensure_document_table(conn)

        rows = await conn.fetch(
            """
            SELECT id, source_path, chunk_index, content, metadata
            FROM document_chunks
            WHERE source_path = $1
            ORDER BY chunk_index ASC
            LIMIT $2
            """,
            source_path,
            limit,
        )

        results = []
        for row in rows:
            item = dict(row)
            if isinstance(item.get("metadata"), str):
                try:
                    item["metadata"] = json.loads(item["metadata"])
                except Exception:
                    pass
            item["preview"] = item["content"][:900]
            item.pop("content", None)
            results.append(item)

        return {
            "query": "document_intro",
            "count": len(results),
            "mode": "latest_document_intro",
            "results": results,
        }
    finally:
        await conn.close()
