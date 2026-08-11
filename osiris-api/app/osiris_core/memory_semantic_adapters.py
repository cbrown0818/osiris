from __future__ import annotations

import asyncio
import os
from typing import Sequence

import httpx
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    PointStruct,
    VectorParams,
)

from .memory_semantic_index import (
    MemorySemanticIndexError,
    SemanticMemoryHit,
)


DEFAULT_EMBEDDING_MODEL = (
    "nomic-embed-text"
)

DEFAULT_OLLAMA_URL = os.getenv(
    "OLLAMA_URL",
    "http://ollama:11434",
).rstrip("/")

DEFAULT_QDRANT_URL = os.getenv(
    "QDRANT_URL",
    "http://qdrant:6333",
)

DEFAULT_QDRANT_API_KEY = (
    os.getenv("QDRANT_API_KEY")
    or os.getenv(
        "QDRANT__SERVICE__API_KEY"
    )
)


class OllamaMemoryEmbedder:
    """
    Async Ollama embedding adapter.

    This adapter derives vectors only.
    It performs no canonical memory writes.
    """

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_OLLAMA_URL,
        model: str = DEFAULT_EMBEDDING_MODEL,
        timeout_seconds: float = 30.0,
    ) -> None:
        if not isinstance(
            base_url,
            str,
        ):
            raise TypeError(
                "base_url must be a string"
            )

        if not base_url.strip():
            raise ValueError(
                "base_url cannot be empty"
            )

        if not isinstance(
            model,
            str,
        ):
            raise TypeError(
                "model must be a string"
            )

        if not model.strip():
            raise ValueError(
                "model cannot be empty"
            )

        if (
            not isinstance(
                timeout_seconds,
                (int, float),
            )
            or isinstance(
                timeout_seconds,
                bool,
            )
            or timeout_seconds <= 0
        ):
            raise ValueError(
                "timeout_seconds must be positive"
            )

        self._base_url = (
            base_url.rstrip("/")
        )

        self._model = model.strip()

        self._timeout = float(
            timeout_seconds
        )

    @property
    def model(
        self,
    ) -> str:
        return self._model

    @property
    def base_url(
        self,
    ) -> str:
        return self._base_url

    async def embed(
        self,
        text: str,
    ) -> Sequence[float]:
        if not isinstance(
            text,
            str,
        ):
            raise TypeError(
                "text must be a string"
            )

        text = text.strip()

        if not text:
            raise ValueError(
                "text cannot be empty"
            )

        url = (
            f"{self._base_url}/api/embed"
        )

        try:
            async with httpx.AsyncClient(
                timeout=self._timeout,
            ) as client:
                response = await client.post(
                    url,
                    json={
                        "model": self._model,
                        "input": text,
                    },
                )

                response.raise_for_status()

        except httpx.HTTPError as exc:
            raise MemorySemanticIndexError(
                "Ollama embedding request failed"
            ) from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise MemorySemanticIndexError(
                "Ollama returned invalid JSON"
            ) from exc

        embeddings = payload.get(
            "embeddings"
        )

        if (
            not isinstance(
                embeddings,
                list,
            )
            or len(embeddings) != 1
            or not isinstance(
                embeddings[0],
                list,
            )
        ):
            raise MemorySemanticIndexError(
                "Ollama returned an invalid "
                "embedding response"
            )

        vector = embeddings[0]

        if not vector:
            raise MemorySemanticIndexError(
                "Ollama returned an empty "
                "embedding vector"
            )

        normalized = []

        for value in vector:
            if (
                not isinstance(
                    value,
                    (int, float),
                )
                or isinstance(
                    value,
                    bool,
                )
            ):
                raise MemorySemanticIndexError(
                    "Ollama embedding contains "
                    "non-numeric values"
                )

            normalized.append(
                float(value)
            )

        return normalized


class QdrantMemoryVectorStore:
    """
    Qdrant adapter for derived canonical
    semantic memory vectors.

    Collection contents are disposable and
    rebuildable from PostgreSQL.
    """

    def __init__(
        self,
        *,
        url: str = DEFAULT_QDRANT_URL,
        api_key: str | None = (
            DEFAULT_QDRANT_API_KEY
        ),
        distance: Distance = Distance.COSINE,
        client: QdrantClient | None = None,
    ) -> None:
        if not isinstance(
            url,
            str,
        ):
            raise TypeError(
                "url must be a string"
            )

        if not url.strip():
            raise ValueError(
                "url cannot be empty"
            )

        if not isinstance(
            distance,
            Distance,
        ):
            raise TypeError(
                "distance must be a "
                "qdrant Distance"
            )

        self._distance = distance

        self._client = (
            client
            if client is not None
            else QdrantClient(
                url=url.strip(),
                api_key=api_key,
            )
        )

        self._dimensions: dict[
            str,
            int,
        ] = {}

    @staticmethod
    def _validate_vector(
        vector: Sequence[float],
    ) -> list[float]:
        if not isinstance(
            vector,
            Sequence,
        ):
            raise TypeError(
                "vector must be a sequence"
            )

        if isinstance(
            vector,
            (str, bytes),
        ):
            raise TypeError(
                "vector must be numeric"
            )

        if not vector:
            raise ValueError(
                "vector cannot be empty"
            )

        normalized = []

        for value in vector:
            if (
                not isinstance(
                    value,
                    (int, float),
                )
                or isinstance(
                    value,
                    bool,
                )
            ):
                raise ValueError(
                    "vector values must "
                    "be numeric"
                )

            normalized.append(
                float(value)
            )

        return normalized

    @staticmethod
    def _validate_collection(
        collection: str,
    ) -> str:
        if not isinstance(
            collection,
            str,
        ):
            raise TypeError(
                "collection must be a string"
            )

        collection = collection.strip()

        if not collection:
            raise ValueError(
                "collection cannot be empty"
            )

        return collection

    async def _collection_exists(
        self,
        collection: str,
    ) -> bool:
        try:
            return await asyncio.to_thread(
                self._client.collection_exists,
                collection,
            )
        except Exception as exc:
            raise MemorySemanticIndexError(
                "Qdrant collection lookup failed"
            ) from exc

    async def _ensure_collection(
        self,
        *,
        collection: str,
        vector_size: int,
    ) -> None:
        known_size = self._dimensions.get(
            collection
        )

        if known_size is not None:
            if known_size != vector_size:
                raise MemorySemanticIndexError(
                    "embedding vector dimension "
                    "changed for existing collection"
                )

            return

        exists = await self._collection_exists(
            collection
        )

        if not exists:
            try:
                await asyncio.to_thread(
                    self._client.create_collection,
                    collection_name=collection,
                    vectors_config=VectorParams(
                        size=vector_size,
                        distance=self._distance,
                    ),
                )

            except Exception as exc:
                raise MemorySemanticIndexError(
                    "Qdrant collection creation "
                    "failed"
                ) from exc

        else:
            try:
                info = await asyncio.to_thread(
                    self._client.get_collection,
                    collection
                )

                vectors = (
                    info.config.params.vectors
                )

                existing_size = getattr(
                    vectors,
                    "size",
                    None,
                )

                if (
                    existing_size is not None
                    and existing_size
                    != vector_size
                ):
                    raise MemorySemanticIndexError(
                        "existing Qdrant collection "
                        "vector dimension does not "
                        "match embedding dimension"
                    )

            except MemorySemanticIndexError:
                raise

            except Exception as exc:
                raise MemorySemanticIndexError(
                    "Qdrant collection inspection "
                    "failed"
                ) from exc

        self._dimensions[
            collection
        ] = vector_size

    async def upsert(
        self,
        *,
        collection: str,
        point_id: str,
        vector: Sequence[float],
        payload: dict,
    ) -> None:
        collection = (
            self._validate_collection(
                collection
            )
        )

        if not isinstance(
            point_id,
            str,
        ):
            raise TypeError(
                "point_id must be a string"
            )

        point_id = point_id.strip()

        if not point_id:
            raise ValueError(
                "point_id cannot be empty"
            )

        if not isinstance(
            payload,
            dict,
        ):
            raise TypeError(
                "payload must be a dict"
            )

        normalized_vector = (
            self._validate_vector(
                vector
            )
        )

        await self._ensure_collection(
            collection=collection,
            vector_size=len(
                normalized_vector
            ),
        )

        try:
            await asyncio.to_thread(
                self._client.upsert,
                collection_name=collection,
                points=[
                    PointStruct(
                        id=point_id,
                        vector=normalized_vector,
                        payload=dict(
                            payload
                        ),
                    )
                ],
                wait=True,
            )

        except Exception as exc:
            raise MemorySemanticIndexError(
                "Qdrant vector upsert failed"
            ) from exc

    async def delete(
        self,
        *,
        collection: str,
        point_id: str,
    ) -> None:
        collection = (
            self._validate_collection(
                collection
            )
        )

        if not isinstance(
            point_id,
            str,
        ):
            raise TypeError(
                "point_id must be a string"
            )

        point_id = point_id.strip()

        if not point_id:
            raise ValueError(
                "point_id cannot be empty"
            )

        try:
            await asyncio.to_thread(
                self._client.delete,
                collection_name=collection,
                points_selector=[
                    point_id
                ],
                wait=True,
            )

        except Exception as exc:
            raise MemorySemanticIndexError(
                "Qdrant vector delete failed"
            ) from exc

    async def search(
        self,
        *,
        collection: str,
        vector: Sequence[float],
        limit: int,
    ) -> Sequence[
        SemanticMemoryHit
    ]:
        collection = (
            self._validate_collection(
                collection
            )
        )

        normalized_vector = (
            self._validate_vector(
                vector
            )
        )

        if (
            not isinstance(
                limit,
                int,
            )
            or isinstance(
                limit,
                bool,
            )
            or limit < 1
            or limit > 100
        ):
            raise ValueError(
                "limit must be an integer "
                "between 1 and 100"
            )

        await self._ensure_collection(
            collection=collection,
            vector_size=len(
                normalized_vector
            ),
        )

        try:
            response = await asyncio.to_thread(
                self._client.query_points,
                collection_name=collection,
                query=normalized_vector,
                limit=limit,
                with_payload=False,
                with_vectors=False,
            )

        except Exception as exc:
            raise MemorySemanticIndexError(
                "Qdrant semantic search failed"
            ) from exc

        points = getattr(
            response,
            "points",
            None,
        )

        if points is None:
            raise MemorySemanticIndexError(
                "Qdrant returned an invalid "
                "search response"
            )

        hits = []

        for point in points:
            point_id = getattr(
                point,
                "id",
                None,
            )

            score = getattr(
                point,
                "score",
                None,
            )

            if (
                point_id is None
                or score is None
            ):
                raise MemorySemanticIndexError(
                    "Qdrant search result "
                    "is missing id or score"
                )

            hits.append(
                SemanticMemoryHit(
                    memory_id=str(
                        point_id
                    ),
                    score=float(
                        score
                    ),
                )
            )

        return hits
