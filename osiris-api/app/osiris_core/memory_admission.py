from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .memory_models import (
    MemoryKind,
    MemoryRecord,
    MemorySourceType,
    MemoryStatus,
)


class MemoryAdmissionDisposition(
    str,
    Enum,
):
    REJECTED = "rejected"
    REVIEW = "review"
    ADMITTED = "admitted"


class MemoryEvidenceType(
    str,
    Enum,
):
    UNSPECIFIED = "unspecified"
    USER_EXPLICIT = "user_explicit"
    SYSTEM_VERIFIED = "system_verified"
    DEVICE_VERIFIED = "device_verified"
    EXECUTION_LEARNING = "execution_learning"
    DOCUMENT_DERIVED = "document_derived"
    INFERRED = "inferred"


@dataclass(
    frozen=True,
    slots=True,
)
class MemoryAdmissionContext:
    evidence_type: MemoryEvidenceType = (
        MemoryEvidenceType.UNSPECIFIED
    )

    explicit_persistence: bool = False
    verified: bool = False
    raw_conversation: bool = False
    raw_event: bool = False

    def __post_init__(
        self,
    ) -> None:
        if not isinstance(
            self.evidence_type,
            MemoryEvidenceType,
        ):
            object.__setattr__(
                self,
                "evidence_type",
                MemoryEvidenceType(
                    self.evidence_type
                ),
            )

        for field_name in (
            "explicit_persistence",
            "verified",
            "raw_conversation",
            "raw_event",
        ):
            value = getattr(
                self,
                field_name,
            )

            if not isinstance(
                value,
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
class MemoryAdmissionDecision:
    disposition: (
        MemoryAdmissionDisposition
    )

    reason_code: str
    reason: str
    fingerprint: str

    @property
    def admitted(
        self,
    ) -> bool:
        return (
            self.disposition
            == MemoryAdmissionDisposition.ADMITTED
        )


class CanonicalMemoryAdmissionPolicy:
    """
    Deterministic admission policy for
    canonical OSIRIS memory candidates.

    This policy makes no database writes.

    Raw conversations and raw execution
    events are never directly admitted.
    """

    @staticmethod
    def _decision(
        record: MemoryRecord,
        disposition: (
            MemoryAdmissionDisposition
        ),
        reason_code: str,
        reason: str,
    ) -> MemoryAdmissionDecision:
        return MemoryAdmissionDecision(
            disposition=disposition,
            reason_code=reason_code,
            reason=reason,
            fingerprint=record.fingerprint,
        )

    @staticmethod
    def _source_matches_evidence(
        record: MemoryRecord,
        context: MemoryAdmissionContext,
    ) -> bool:
        expected = {
            MemoryEvidenceType.USER_EXPLICIT: {
                MemorySourceType.USER,
            },
            MemoryEvidenceType.SYSTEM_VERIFIED: {
                MemorySourceType.SYSTEM,
            },
            MemoryEvidenceType.DEVICE_VERIFIED: {
                MemorySourceType.DEVICE,
            },
            MemoryEvidenceType.EXECUTION_LEARNING: {
                MemorySourceType.AGENT,
                MemorySourceType.SYSTEM,
            },
            MemoryEvidenceType.DOCUMENT_DERIVED: {
                MemorySourceType.DOCUMENT,
            },
        }

        allowed = expected.get(
            context.evidence_type
        )

        if allowed is None:
            return True

        return (
            record.source_type
            in allowed
        )

    def evaluate(
        self,
        record: MemoryRecord,
        context: MemoryAdmissionContext,
    ) -> MemoryAdmissionDecision:
        if not isinstance(
            record,
            MemoryRecord,
        ):
            raise TypeError(
                "record must be a MemoryRecord"
            )

        if not isinstance(
            context,
            MemoryAdmissionContext,
        ):
            raise TypeError(
                "context must be a "
                "MemoryAdmissionContext"
            )

        if (
            record.status
            != MemoryStatus.ACTIVE
        ):
            return self._decision(
                record,
                MemoryAdmissionDisposition.REJECTED,
                "candidate_not_active",
                (
                    "Only active memory "
                    "candidates may be admitted."
                ),
            )

        if context.raw_conversation:
            return self._decision(
                record,
                MemoryAdmissionDisposition.REJECTED,
                "raw_conversation",
                (
                    "Raw conversation content "
                    "is not canonical memory."
                ),
            )

        if context.raw_event:
            return self._decision(
                record,
                MemoryAdmissionDisposition.REJECTED,
                "raw_event",
                (
                    "Raw execution or system "
                    "events are not canonical "
                    "memory."
                ),
            )

        if not record.source_ref:
            return self._decision(
                record,
                MemoryAdmissionDisposition.REVIEW,
                "missing_provenance",
                (
                    "Canonical memory requires "
                    "a source reference before "
                    "automatic admission."
                ),
            )

        if not self._source_matches_evidence(
            record,
            context,
        ):
            return self._decision(
                record,
                MemoryAdmissionDisposition.REVIEW,
                "source_evidence_mismatch",
                (
                    "Memory source type does "
                    "not match its claimed "
                    "evidence."
                ),
            )

        evidence = context.evidence_type

        if (
            evidence
            == MemoryEvidenceType.USER_EXPLICIT
        ):
            if record.kind in {
                MemoryKind.PREFERENCE,
                MemoryKind.INSTRUCTION,
            }:
                return self._decision(
                    record,
                    MemoryAdmissionDisposition.ADMITTED,
                    "explicit_user_memory",
                    (
                        "Explicit user preference "
                        "or instruction is eligible "
                        "for canonical memory."
                    ),
                )

            if context.explicit_persistence:
                return self._decision(
                    record,
                    MemoryAdmissionDisposition.ADMITTED,
                    "explicit_user_persistence",
                    (
                        "The user explicitly "
                        "requested durable memory."
                    ),
                )

            return self._decision(
                record,
                MemoryAdmissionDisposition.REVIEW,
                "user_fact_requires_review",
                (
                    "A user-originated fact is "
                    "not automatically durable "
                    "without explicit persistence."
                ),
            )

        if evidence in {
            MemoryEvidenceType.SYSTEM_VERIFIED,
            MemoryEvidenceType.DEVICE_VERIFIED,
        }:
            if not context.verified:
                return self._decision(
                    record,
                    MemoryAdmissionDisposition.REVIEW,
                    "evidence_not_verified",
                    (
                        "System or device evidence "
                        "must be verified before "
                        "automatic admission."
                    ),
                )

            if record.kind in {
                MemoryKind.SEMANTIC,
                MemoryKind.OBSERVATION,
                MemoryKind.LEARNING,
            }:
                return self._decision(
                    record,
                    MemoryAdmissionDisposition.ADMITTED,
                    "verified_evidence",
                    (
                        "Verified system or device "
                        "evidence is eligible for "
                        "canonical memory."
                    ),
                )

            return self._decision(
                record,
                MemoryAdmissionDisposition.REVIEW,
                "evidence_kind_requires_review",
                (
                    "The memory kind requires "
                    "review for this evidence "
                    "type."
                ),
            )

        if (
            evidence
            == MemoryEvidenceType.EXECUTION_LEARNING
        ):
            if (
                context.verified
                and record.kind
                == MemoryKind.LEARNING
            ):
                return self._decision(
                    record,
                    MemoryAdmissionDisposition.ADMITTED,
                    "verified_learning",
                    (
                        "Verified execution "
                        "learning is eligible for "
                        "canonical memory."
                    ),
                )

            return self._decision(
                record,
                MemoryAdmissionDisposition.REVIEW,
                "learning_requires_verification",
                (
                    "Execution learning requires "
                    "verified learning evidence."
                ),
            )

        if (
            evidence
            == MemoryEvidenceType.DOCUMENT_DERIVED
        ):
            return self._decision(
                record,
                MemoryAdmissionDisposition.REVIEW,
                "document_requires_extraction_policy",
                (
                    "Document-derived knowledge "
                    "requires a dedicated "
                    "extraction policy."
                ),
            )

        if (
            evidence
            == MemoryEvidenceType.INFERRED
        ):
            return self._decision(
                record,
                MemoryAdmissionDisposition.REVIEW,
                "inference_requires_review",
                (
                    "Inferred memory is never "
                    "automatically admitted."
                ),
            )

        return self._decision(
            record,
            MemoryAdmissionDisposition.REVIEW,
            "insufficient_evidence",
            (
                "The candidate lacks sufficient "
                "evidence for automatic "
                "canonical admission."
            ),
        )
