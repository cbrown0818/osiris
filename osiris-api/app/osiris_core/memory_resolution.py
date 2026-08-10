from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .memory_models import (
    MemoryKind,
    MemoryRecord,
    MemoryStatus,
)


class MemoryResolutionType(
    str,
    Enum,
):
    EXACT_DUPLICATE = "exact_duplicate"
    DISTINCT = "distinct"
    POTENTIAL_CONFLICT = "potential_conflict"
    SUPERSESSION_CANDIDATE = (
        "supersession_candidate"
    )
    INSUFFICIENT_CONTEXT = (
        "insufficient_context"
    )


@dataclass(
    frozen=True,
    slots=True,
)
class MemoryResolutionContext:
    correction_explicit: bool = False
    correction_verified: bool = False

    def __post_init__(
        self,
    ) -> None:
        for field_name in (
            "correction_explicit",
            "correction_verified",
        ):
            if not isinstance(
                getattr(
                    self,
                    field_name,
                ),
                bool,
            ):
                raise TypeError(
                    f"{field_name} must "
                    "be a boolean"
                )


@dataclass(
    frozen=True,
    slots=True,
)
class MemoryResolution:
    resolution: MemoryResolutionType
    reason_code: str
    reason: str
    candidate_id: str
    existing_id: str | None = None

    @property
    def may_create(
        self,
    ) -> bool:
        return (
            self.resolution
            == MemoryResolutionType.DISTINCT
        )

    @property
    def may_supersede(
        self,
    ) -> bool:
        return (
            self.resolution
            == (
                MemoryResolutionType
                .SUPERSESSION_CANDIDATE
            )
        )


class CanonicalMemoryResolutionPolicy:
    """
    Pure comparison policy for admitted
    canonical memory candidates.

    This policy performs no persistence,
    mutation, retrieval, or model calls.
    """

    @staticmethod
    def _result(
        candidate: MemoryRecord,
        resolution: MemoryResolutionType,
        reason_code: str,
        reason: str,
        existing: MemoryRecord | None = None,
    ) -> MemoryResolution:
        return MemoryResolution(
            resolution=resolution,
            reason_code=reason_code,
            reason=reason,
            candidate_id=candidate.id,
            existing_id=(
                existing.id
                if existing is not None
                else None
            ),
        )

    def compare(
        self,
        candidate: MemoryRecord,
        existing: MemoryRecord | None,
        context: MemoryResolutionContext,
    ) -> MemoryResolution:
        if not isinstance(
            candidate,
            MemoryRecord,
        ):
            raise TypeError(
                "candidate must be a MemoryRecord"
            )

        if (
            existing is not None
            and not isinstance(
                existing,
                MemoryRecord,
            )
        ):
            raise TypeError(
                "existing must be a MemoryRecord "
                "or None"
            )

        if not isinstance(
            context,
            MemoryResolutionContext,
        ):
            raise TypeError(
                "context must be a "
                "MemoryResolutionContext"
            )

        if (
            candidate.status
            != MemoryStatus.ACTIVE
        ):
            return self._result(
                candidate,
                (
                    MemoryResolutionType
                    .INSUFFICIENT_CONTEXT
                ),
                "candidate_not_active",
                (
                    "Only active candidates "
                    "may be resolved."
                ),
                existing,
            )

        if existing is None:
            return self._result(
                candidate,
                MemoryResolutionType.DISTINCT,
                "no_existing_memory",
                (
                    "No existing canonical "
                    "memory was supplied."
                ),
            )

        if (
            existing.status
            != MemoryStatus.ACTIVE
        ):
            return self._result(
                candidate,
                (
                    MemoryResolutionType
                    .INSUFFICIENT_CONTEXT
                ),
                "existing_not_active",
                (
                    "Comparison requires an "
                    "active existing memory."
                ),
                existing,
            )

        if (
            candidate.fingerprint
            == existing.fingerprint
        ):
            return self._result(
                candidate,
                (
                    MemoryResolutionType
                    .EXACT_DUPLICATE
                ),
                "same_fingerprint",
                (
                    "Candidate and existing "
                    "memory have the same "
                    "canonical fingerprint."
                ),
                existing,
            )

        same_subject = (
            candidate.subject_entity_id
            is not None
            and existing.subject_entity_id
            is not None
            and candidate.subject_entity_id
            == existing.subject_entity_id
        )

        same_kind = (
            candidate.kind
            == existing.kind
        )

        if (
            context.correction_explicit
            and context.correction_verified
            and same_subject
            and same_kind
        ):
            return self._result(
                candidate,
                (
                    MemoryResolutionType
                    .SUPERSESSION_CANDIDATE
                ),
                "verified_explicit_correction",
                (
                    "A verified explicit "
                    "correction targets the same "
                    "subject and memory kind."
                ),
                existing,
            )

        if (
            same_subject
            and same_kind
        ):
            return self._result(
                candidate,
                (
                    MemoryResolutionType
                    .POTENTIAL_CONFLICT
                ),
                "same_subject_changed_content",
                (
                    "Different content exists "
                    "for the same subject and "
                    "memory kind."
                ),
                existing,
            )

        if (
            context.correction_explicit
            or context.correction_verified
        ):
            return self._result(
                candidate,
                (
                    MemoryResolutionType
                    .INSUFFICIENT_CONTEXT
                ),
                "correction_target_mismatch",
                (
                    "Correction evidence exists "
                    "but the candidate does not "
                    "match the existing subject "
                    "and memory kind."
                ),
                existing,
            )

        return self._result(
            candidate,
            MemoryResolutionType.DISTINCT,
            "different_memory_scope",
            (
                "Candidate does not occupy the "
                "same canonical memory scope."
            ),
            existing,
        )
