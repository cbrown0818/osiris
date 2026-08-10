from __future__ import annotations

from dataclasses import dataclass

from .memory_admission import (
    CanonicalMemoryAdmissionPolicy,
    MemoryAdmissionContext,
    MemoryAdmissionDecision,
    MemoryAdmissionDisposition,
)
from .memory_models import (
    MemoryRecord,
    MemoryStatus,
)
from .memory_repository import (
    PostgresMemoryRepository,
)


@dataclass(
    frozen=True,
    slots=True,
)
class MemoryServiceResult:
    decision: MemoryAdmissionDecision
    stored: MemoryRecord | None = None
    duplicate: MemoryRecord | None = None

    @property
    def written(
        self,
    ) -> bool:
        return self.stored is not None

    @property
    def duplicate_found(
        self,
    ) -> bool:
        return self.duplicate is not None


class CanonicalMemoryService:
    """
    Canonical admission-to-persistence gateway.

    REJECTED and REVIEW decisions never write.

    ADMITTED candidates are checked for an
    active fingerprint duplicate before creation.

    PostgreSQL remains authoritative.
    """

    def __init__(
        self,
        repository: PostgresMemoryRepository,
        *,
        policy: (
            CanonicalMemoryAdmissionPolicy
            | None
        ) = None,
    ) -> None:
        if not isinstance(
            repository,
            PostgresMemoryRepository,
        ):
            raise TypeError(
                "repository must be a "
                "PostgresMemoryRepository"
            )

        if policy is None:
            policy = (
                CanonicalMemoryAdmissionPolicy()
            )

        if not isinstance(
            policy,
            CanonicalMemoryAdmissionPolicy,
        ):
            raise TypeError(
                "policy must be a "
                "CanonicalMemoryAdmissionPolicy"
            )

        self._repository = repository
        self._policy = policy

    async def admit(
        self,
        record: MemoryRecord,
        context: MemoryAdmissionContext,
    ) -> MemoryServiceResult:
        decision = self._policy.evaluate(
            record,
            context,
        )

        if (
            decision.disposition
            != MemoryAdmissionDisposition.ADMITTED
        ):
            return MemoryServiceResult(
                decision=decision,
            )

        duplicates = (
            await self._repository
            .find_by_fingerprint(
                record.fingerprint,
                status=MemoryStatus.ACTIVE,
                limit=1,
            )
        )

        if duplicates:
            return MemoryServiceResult(
                decision=decision,
                duplicate=duplicates[0],
            )

        stored = await self._repository.create(
            record
        )

        return MemoryServiceResult(
            decision=decision,
            stored=stored,
        )
