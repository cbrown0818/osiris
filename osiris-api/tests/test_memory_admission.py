import unittest

from osiris_core.memory_admission import (
    CanonicalMemoryAdmissionPolicy,
    MemoryAdmissionContext,
    MemoryAdmissionDisposition,
    MemoryEvidenceType,
)
from osiris_core.memory_models import (
    MemoryKind,
    MemoryRecord,
    MemorySourceType,
    MemoryStatus,
)


class MemoryAdmissionTests(
    unittest.TestCase
):
    def setUp(
        self,
    ) -> None:
        self.policy = (
            CanonicalMemoryAdmissionPolicy()
        )

    def record(
        self,
        *,
        kind=MemoryKind.SEMANTIC,
        source_type=MemorySourceType.USER,
        source_ref="synthetic:source",
    ):
        return MemoryRecord.new(
            kind=kind,
            content=(
                "Synthetic admission "
                "candidate."
            ),
            source_type=source_type,
            source_ref=source_ref,
        )

    def test_raw_conversation_is_rejected(
        self,
    ):
        decision = self.policy.evaluate(
            self.record(),
            MemoryAdmissionContext(
                evidence_type=(
                    MemoryEvidenceType.USER_EXPLICIT
                ),
                raw_conversation=True,
            ),
        )

        self.assertEqual(
            decision.disposition,
            MemoryAdmissionDisposition.REJECTED,
        )

        self.assertEqual(
            decision.reason_code,
            "raw_conversation",
        )

    def test_raw_event_is_rejected(
        self,
    ):
        decision = self.policy.evaluate(
            self.record(
                source_type=(
                    MemorySourceType.SYSTEM
                )
            ),
            MemoryAdmissionContext(
                evidence_type=(
                    MemoryEvidenceType.SYSTEM_VERIFIED
                ),
                raw_event=True,
                verified=True,
            ),
        )

        self.assertEqual(
            decision.disposition,
            MemoryAdmissionDisposition.REJECTED,
        )

    def test_non_active_candidate_is_rejected(
        self,
    ):
        record = (
            self.record()
            .with_status(
                MemoryStatus.INVALIDATED
            )
        )

        decision = self.policy.evaluate(
            record,
            MemoryAdmissionContext(
                evidence_type=(
                    MemoryEvidenceType.USER_EXPLICIT
                ),
            ),
        )

        self.assertEqual(
            decision.reason_code,
            "candidate_not_active",
        )

    def test_explicit_preference_is_admitted(
        self,
    ):
        decision = self.policy.evaluate(
            self.record(
                kind=MemoryKind.PREFERENCE,
            ),
            MemoryAdmissionContext(
                evidence_type=(
                    MemoryEvidenceType.USER_EXPLICIT
                ),
            ),
        )

        self.assertTrue(
            decision.admitted
        )

    def test_explicit_instruction_is_admitted(
        self,
    ):
        decision = self.policy.evaluate(
            self.record(
                kind=MemoryKind.INSTRUCTION,
            ),
            MemoryAdmissionContext(
                evidence_type=(
                    MemoryEvidenceType.USER_EXPLICIT
                ),
            ),
        )

        self.assertTrue(
            decision.admitted
        )

    def test_user_fact_requires_review(
        self,
    ):
        decision = self.policy.evaluate(
            self.record(),
            MemoryAdmissionContext(
                evidence_type=(
                    MemoryEvidenceType.USER_EXPLICIT
                ),
            ),
        )

        self.assertEqual(
            decision.disposition,
            MemoryAdmissionDisposition.REVIEW,
        )

    def test_user_explicit_persistence_admits_fact(
        self,
    ):
        decision = self.policy.evaluate(
            self.record(),
            MemoryAdmissionContext(
                evidence_type=(
                    MemoryEvidenceType.USER_EXPLICIT
                ),
                explicit_persistence=True,
            ),
        )

        self.assertTrue(
            decision.admitted
        )

    def test_missing_provenance_requires_review(
        self,
    ):
        decision = self.policy.evaluate(
            self.record(
                kind=MemoryKind.PREFERENCE,
                source_ref=None,
            ),
            MemoryAdmissionContext(
                evidence_type=(
                    MemoryEvidenceType.USER_EXPLICIT
                ),
            ),
        )

        self.assertEqual(
            decision.reason_code,
            "missing_provenance",
        )

    def test_inference_requires_review(
        self,
    ):
        decision = self.policy.evaluate(
            self.record(),
            MemoryAdmissionContext(
                evidence_type=(
                    MemoryEvidenceType.INFERRED
                ),
            ),
        )

        self.assertEqual(
            decision.disposition,
            MemoryAdmissionDisposition.REVIEW,
        )

    def test_verified_system_observation_is_admitted(
        self,
    ):
        decision = self.policy.evaluate(
            self.record(
                kind=MemoryKind.OBSERVATION,
                source_type=(
                    MemorySourceType.SYSTEM
                ),
            ),
            MemoryAdmissionContext(
                evidence_type=(
                    MemoryEvidenceType.SYSTEM_VERIFIED
                ),
                verified=True,
            ),
        )

        self.assertTrue(
            decision.admitted
        )

    def test_unverified_system_observation_requires_review(
        self,
    ):
        decision = self.policy.evaluate(
            self.record(
                kind=MemoryKind.OBSERVATION,
                source_type=(
                    MemorySourceType.SYSTEM
                ),
            ),
            MemoryAdmissionContext(
                evidence_type=(
                    MemoryEvidenceType.SYSTEM_VERIFIED
                ),
                verified=False,
            ),
        )

        self.assertEqual(
            decision.reason_code,
            "evidence_not_verified",
        )

    def test_verified_execution_learning_is_admitted(
        self,
    ):
        decision = self.policy.evaluate(
            self.record(
                kind=MemoryKind.LEARNING,
                source_type=(
                    MemorySourceType.AGENT
                ),
            ),
            MemoryAdmissionContext(
                evidence_type=(
                    MemoryEvidenceType.EXECUTION_LEARNING
                ),
                verified=True,
            ),
        )

        self.assertTrue(
            decision.admitted
        )

    def test_source_evidence_mismatch_requires_review(
        self,
    ):
        decision = self.policy.evaluate(
            self.record(
                kind=MemoryKind.OBSERVATION,
                source_type=(
                    MemorySourceType.USER
                ),
            ),
            MemoryAdmissionContext(
                evidence_type=(
                    MemoryEvidenceType.DEVICE_VERIFIED
                ),
                verified=True,
            ),
        )

        self.assertEqual(
            decision.reason_code,
            "source_evidence_mismatch",
        )

    def test_document_memory_requires_separate_policy(
        self,
    ):
        decision = self.policy.evaluate(
            self.record(
                source_type=(
                    MemorySourceType.DOCUMENT
                ),
            ),
            MemoryAdmissionContext(
                evidence_type=(
                    MemoryEvidenceType.DOCUMENT_DERIVED
                ),
                verified=True,
            ),
        )

        self.assertEqual(
            decision.reason_code,
            "document_requires_extraction_policy",
        )

        self.assertFalse(
            decision.admitted
        )


if __name__ == "__main__":
    unittest.main()
