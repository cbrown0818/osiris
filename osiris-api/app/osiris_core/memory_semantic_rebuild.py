from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

from .memory_models import (
    MemoryRecord,
    MemoryStatus,
)


class MemoryRepositoryLister(Protocol):
    async def list(
        self,
        *,
        status: MemoryStatus | None = None,
        limit: int = 100,
        offset: int = 0,
        **kwargs,
    ) -> Sequence[
        MemoryRecord
    ]:
        ...


class SemanticMemoryIndexer(Protocol):
    def is_indexable(
        self,
        record: MemoryRecord,
    ) -> bool:
        ...

    async def index(
        self,
        record: MemoryRecord,
    ) -> bool:
        ...


@dataclass(
    frozen=True,
    slots=True,
)
class SemanticRebuildReport:
    scanned: int
    indexed: int
    skipped: int
    failed: int

    def __post_init__(self) -> None:
        for name in (
            "scanned",
            "indexed",
            "skipped",
            "failed",
        ):
            value = getattr(
                self,
                name,
            )

            if (
                not isinstance(
                    value,
                    int,
                )
                or isinstance(
                    value,
                    bool,
                )
                or value < 0
            ):
                raise ValueError(
                    f"{name} must be a "
                    "non-negative integer"
                )

        if (
            self.indexed
            + self.skipped
            + self.failed
            != self.scanned
        ):
            raise ValueError(
                "rebuild report counts "
                "do not balance"
            )


class CanonicalSemanticIndexRebuilder:
    """
    Rebuild the derived semantic index from
    authoritative PostgreSQL memory records.

    PostgreSQL remains the source of truth.
    """

    MAX_BATCH_SIZE = 500

    def __init__(
        self,
        *,
        repository: MemoryRepositoryLister,
        semantic_index: SemanticMemoryIndexer,
        batch_size: int = MAX_BATCH_SIZE,
    ) -> None:
        if repository is None:
            raise ValueError(
                "repository is required"
            )

        if semantic_index is None:
            raise ValueError(
                "semantic_index is required"
            )

        if (
            not isinstance(
                batch_size,
                int,
            )
            or isinstance(
                batch_size,
                bool,
            )
            or batch_size < 1
            or batch_size
            > self.MAX_BATCH_SIZE
        ):
            raise ValueError(
                "batch_size must be between "
                "1 and 500"
            )

        self._repository = repository
        self._semantic_index = (
            semantic_index
        )
        self._batch_size = batch_size

    @property
    def batch_size(
        self,
    ) -> int:
        return self._batch_size

    async def rebuild(
        self,
    ) -> SemanticRebuildReport:
        scanned = 0
        indexed = 0
        skipped = 0
        failed = 0

        offset = 0

        while True:
            records = list(
                await self._repository.list(
                    status=MemoryStatus.ACTIVE,
                    limit=self._batch_size,
                    offset=offset,
                )
            )

            for record in records:
                scanned += 1

                if not self._semantic_index.is_indexable(
                    record
                ):
                    skipped += 1
                    continue

                try:
                    result = (
                        await self._semantic_index.index(
                            record
                        )
                    )

                except Exception:
                    failed += 1
                    continue

                if result:
                    indexed += 1
                else:
                    skipped += 1

            if len(records) < self._batch_size:
                break

            offset += self._batch_size

        return SemanticRebuildReport(
            scanned=scanned,
            indexed=indexed,
            skipped=skipped,
            failed=failed,
        )
