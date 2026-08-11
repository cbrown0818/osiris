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
    MemoryDuplicateError,
    MemoryRepositoryError,
    PostgresMemoryRepository,
)
from .memory_resolution import (
    CanonicalMemoryResolutionPolicy,
    MemoryResolution,
    MemoryResolutionContext,
    MemoryResolutionType,
)


@dataclass(
    frozen=True,
    slots=True,
)
class MemoryServiceResult:
    decision: MemoryAdmissionDecision

    stored: MemoryRecord | None = None
    duplicate: MemoryRecord | None = None

    resolution: MemoryResolution | None = None

    superseded: MemoryRecord | None = None
    replacement: MemoryRecord | None = None

    @property
    def written(
        self,
    ) -> bool:
        return (
            self.stored is not None
            or self.replacement is not None
        )

    @property
    def duplicate_found(
        self,
    ) -> bool:
        return self.duplicate is not None

    @property
    def supersession_performed(
        self,
    ) -> bool:
        return (
            self.superseded is not None
            and self.replacement is not None
        )


class CanonicalMemoryService:
    """
    Canonical memory admission and resolution
    gateway.

    REJECTED and REVIEW admission decisions
    never write.

    Exact active fingerprint duplicates never
    create a second canonical memory.

    Conflicting memories never mutate existing
    state unless the resolution policy identifies
    a verified explicit correction.

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
        resolution_policy: (
            CanonicalMemoryResolutionPolicy
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

        if resolution_policy is None:
            resolution_policy = (
                CanonicalMemoryResolutionPolicy()
            )

        if not isinstance(
            resolution_policy,
            CanonicalMemoryResolutionPolicy,
        ):
            raise TypeError(
                "resolution_policy must be a "
                "CanonicalMemoryResolutionPolicy"
            )

        self._repository = repository
        self._policy = policy
        self._resolution_policy = (
            resolution_policy
        )

    async def _find_existing_scope(
        self,
        record: MemoryRecord,
    ) -> list[MemoryRecord]:
        if record.subject_entity_id is None:
            return []

        active_records = (
            await self._repository.list(
                kind=record.kind,
                status=MemoryStatus.ACTIVE,
                limit=500,
                offset=0,
            )
        )

        return [
            existing
            for existing in active_records
            if (
                existing.subject_entity_id
                == record.subject_entity_id
            )
        ]

    async def admit(
        self,
        record: MemoryRecord,
        context: MemoryAdmissionContext,
        *,
        resolution_context: (
            MemoryResolutionContext
            | None
        ) = None,
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
            duplicate = duplicates[0]

            resolution = (
                self._resolution_policy.compare(
                    record,
                    duplicate,
                    (
                        resolution_context
                        or MemoryResolutionContext()
                    ),
                )
            )

            return MemoryServiceResult(
                decision=decision,
                duplicate=duplicate,
                resolution=resolution,
            )

        if resolution_context is None:
            resolution_context = (
                MemoryResolutionContext()
            )

        scoped = await self._find_existing_scope(
            record
        )

        if len(scoped) > 1:
            resolution = MemoryResolution(
                resolution=(
                    MemoryResolutionType
                    .INSUFFICIENT_CONTEXT
                ),
                reason_code=(
                    "ambiguous_existing_scope"
                ),
                reason=(
                    "Multiple active memories "
                    "occupy the same canonical "
                    "subject and kind."
                ),
                candidate_id=record.id,
                existing_id=None,
            )

            return MemoryServiceResult(
                decision=decision,
                resolution=resolution,
            )

        existing = (
            scoped[0]
            if scoped
            else None
        )

        resolution = (
            self._resolution_policy.compare(
                record,
                existing,
                resolution_context,
            )
        )

        if (
            resolution.resolution
            == MemoryResolutionType.DISTINCT
        ):
            try:
                stored = (
                    await self._repository.create(
                        record
                    )
                )
            except MemoryDuplicateError:
                concurrent_duplicates = (
                    await self._repository
                    .find_by_fingerprint(
                        record.fingerprint,
                        status=(
                            MemoryStatus.ACTIVE
                        ),
                        limit=1,
                    )
                )

                if not concurrent_duplicates:
                    raise MemoryRepositoryError(
                        "duplicate constraint "
                        "was raised but no active "
                        "canonical winner could "
                        "be read"
                    )

                duplicate = (
                    concurrent_duplicates[0]
                )

                duplicate_resolution = (
                    self._resolution_policy
                    .compare(
                        record,
                        duplicate,
                        resolution_context,
                    )
                )

                return MemoryServiceResult(
                    decision=decision,
                    duplicate=duplicate,
                    resolution=(
                        duplicate_resolution
                    ),
                )

            return MemoryServiceResult(
                decision=decision,
                stored=stored,
                resolution=resolution,
            )

        if (
            resolution.resolution
            == (
                MemoryResolutionType
                .SUPERSESSION_CANDIDATE
            )
        ):
            if existing is None:
                raise RuntimeError(
                    "supersession resolution "
                    "requires existing memory"
                )

            old_record, new_record = (
                await self._repository.supersede(
                    existing.id,
                    record,
                )
            )

            return MemoryServiceResult(
                decision=decision,
                resolution=resolution,
                superseded=old_record,
                replacement=new_record,
            )

        return MemoryServiceResult(
            decision=decision,
            resolution=resolution,
        )
