from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

from .memory_models import (
    MemoryRecord,
    MemoryStatus,
)


CANONICAL_MEMORY_COLLECTION = (
    "osiris_canonical_memories"
)


class MemorySemanticIndexError(
    RuntimeError
):
    pass


@dataclass(
    frozen=True,
    slots=True,
)
class SemanticMemoryHit:
    memory_id: str
    score: float

    def __post_init__(
        self,
    ) -> None:
        if not isinstance(
            self.memory_id,
            str,
        ):
            raise TypeError(
                "memory_id must be a string"
            )

        if not self.memory_id:
            raise ValueError(
                "memory_id cannot be empty"
            )

        if not isinstance(
            self.score,
            (int, float),
        ):
            raise TypeError(
                "score must be numeric"
            )


class MemoryEmbedder(
    Protocol
):
    async def embed(
        self,
        text: str,
    ) -> Sequence[float]:
        ...


class SemanticVectorStore(
    Protocol
):
    async def upsert(
        self,
        *,
        collection: str,
        point_id: str,
        vector: Sequence[float],
        payload: dict,
    ) -> None:
        ...

    async def delete(
        self,
        *,
        collection: str,
        point_id: str,
    ) -> None:
        ...

    async def search(
        self,
        *,
        collection: str,
        vector: Sequence[float],
        limit: int,
    ) -> Sequence[
        SemanticMemoryHit
    ]:
        ...


class CanonicalMemorySemanticIndex:
    """
    Derived semantic index for canonical OSIRIS
    memory.

    PostgreSQL remains authoritative.

    The semantic index is rebuildable and must
    never be treated as canonical memory state.
    """

    def __init__(
        self,
        *,
        embedder: MemoryEmbedder,
        vector_store: SemanticVectorStore,
        collection: str = (
            CANONICAL_MEMORY_COLLECTION
        ),
    ) -> None:
        if embedder is None:
            raise TypeError(
                "embedder is required"
            )

        if vector_store is None:
            raise TypeError(
                "vector_store is required"
            )

        if not isinstance(
            collection,
            str,
        ):
            raise TypeError(
                "collection must be a string"
            )

        if not collection.strip():
            raise ValueError(
                "collection cannot be empty"
            )

        self._embedder = embedder
        self._vector_store = vector_store
        self._collection = (
            collection.strip()
        )

    @property
    def collection(
        self,
    ) -> str:
        return self._collection

    @staticmethod
    def is_indexable(
        record: MemoryRecord,
    ) -> bool:
        if not isinstance(
            record,
            MemoryRecord,
        ):
            raise TypeError(
                "record must be a MemoryRecord"
            )

        return (
            record.status
            == MemoryStatus.ACTIVE
            and bool(
                record.content.strip()
            )
        )

    @staticmethod
    def build_payload(
        record: MemoryRecord,
    ) -> dict:
        if not isinstance(
            record,
            MemoryRecord,
        ):
            raise TypeError(
                "record must be a MemoryRecord"
            )

        return {
            "memory_id": record.id,
            "kind": record.kind.value,
            "status": record.status.value,
            "source_type": (
                record.source_type.value
            ),
            "subject_entity_id": (
                record.subject_entity_id
            ),
            "fingerprint": (
                record.fingerprint
            ),
        }

    async def index(
        self,
        record: MemoryRecord,
    ) -> bool:
        if not self.is_indexable(
            record
        ):
            return False

        vector = await self._embedder.embed(
            record.content
        )

        if not vector:
            raise MemorySemanticIndexError(
                "embedding vector is empty"
            )

        await self._vector_store.upsert(
            collection=self._collection,
            point_id=record.id,
            vector=vector,
            payload=self.build_payload(
                record
            ),
        )

        return True

    async def remove(
        self,
        memory_id: str,
    ) -> None:
        if not isinstance(
            memory_id,
            str,
        ):
            raise TypeError(
                "memory_id must be a string"
            )

        if not memory_id.strip():
            raise ValueError(
                "memory_id cannot be empty"
            )

        await self._vector_store.delete(
            collection=self._collection,
            point_id=memory_id,
        )

    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
    ) -> list[
        SemanticMemoryHit
    ]:
        if not isinstance(
            query,
            str,
        ):
            raise TypeError(
                "query must be a string"
            )

        query = query.strip()

        if not query:
            raise ValueError(
                "query cannot be empty"
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

        vector = await self._embedder.embed(
            query
        )

        if not vector:
            raise MemorySemanticIndexError(
                "embedding vector is empty"
            )

        hits = await self._vector_store.search(
            collection=self._collection,
            vector=vector,
            limit=limit,
        )

        return list(
            hits
        )
