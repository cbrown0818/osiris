from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Protocol, Sequence

from .memory_models import (
    MemoryRecord,
    MemoryStatus,
)
from .memory_semantic_index import (
    SemanticMemoryHit,
)


class MemoryRepositoryReader(Protocol):
    def get(
        self,
        memory_id: str,
    ) -> MemoryRecord | None:
        ...


class SemanticMemorySearcher(Protocol):
    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
    ) -> Sequence[
        SemanticMemoryHit
    ]:
        ...


@dataclass(
    frozen=True,
    slots=True,
)
class HydratedSemanticMemory:
    record: MemoryRecord
    score: float

    def __post_init__(self) -> None:
        if not isinstance(
            self.record,
            MemoryRecord,
        ):
            raise TypeError(
                "record must be a MemoryRecord"
            )

        if (
            not isinstance(
                self.score,
                (int, float),
            )
            or isinstance(
                self.score,
                bool,
            )
        ):
            raise TypeError(
                "score must be numeric"
            )

        score = float(
            self.score
        )

        if not math.isfinite(
            score
        ):
            raise ValueError(
                "score must be finite"
            )

        object.__setattr__(
            self,
            "score",
            score,
        )


class CanonicalSemanticMemoryRecall:
    """
    Hydrates derived semantic hits from the
    authoritative PostgreSQL memory repository.

    Qdrant supplies only ranked memory IDs.
    PostgreSQL remains the source of truth.
    """

    def __init__(
        self,
        *,
        semantic_index: SemanticMemorySearcher,
        repository: MemoryRepositoryReader,
    ) -> None:
        if semantic_index is None:
            raise ValueError(
                "semantic_index is required"
            )

        if repository is None:
            raise ValueError(
                "repository is required"
            )

        self._semantic_index = (
            semantic_index
        )

        self._repository = repository

    async def recall(
        self,
        query: str,
        *,
        limit: int = 10,
    ) -> list[
        HydratedSemanticMemory
    ]:
        hits = await self._semantic_index.search(
            query,
            limit=limit,
        )

        hydrated = []

        seen_ids: set[str] = set()

        for hit in hits:
            if hit.memory_id in seen_ids:
                continue

            seen_ids.add(
                hit.memory_id
            )

            record = self._repository.get(
                hit.memory_id
            )

            if record is None:
                continue

            if (
                record.status
                is not MemoryStatus.ACTIVE
            ):
                continue

            hydrated.append(
                HydratedSemanticMemory(
                    record=record,
                    score=float(
                        hit.score
                    ),
                )
            )

        return hydrated
