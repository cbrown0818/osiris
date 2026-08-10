import unittest

from osiris_core.memory_models import (
    MemoryKind,
    MemoryRecord,
    MemorySourceType,
    MemoryStatus,
)
from osiris_core.memory_resolution import (
    CanonicalMemoryResolutionPolicy,
    MemoryResolutionContext,
    MemoryResolutionType,
)


class MemoryResolutionTests(
    unittest.TestCase
):
    def setUp(
        self,
    ) -> None:
        self.policy = (
            CanonicalMemoryResolutionPolicy()
        )

    def record(
        self,
        *,
        content="Synthetic memory fact.",
        kind=MemoryKind.SEMANTIC,
        subject_entity_id="synthetic:subject",
    ) -> MemoryRecord:
        return MemoryRecord.new(
            kind=kind,
            content=content,
            source_type=MemorySourceType.SYSTEM,
            source_ref="synthetic:resolution",
            subject_entity_id=subject_entity_id,
        )

    def test_same_fingerprint_is_exact_duplicate(
        self,
    ):
        existing = self.record()

        candidate = self.record(
            content=existing.content
        )

        result = self.policy.compare(
            candidate,
            existing,
            MemoryResolutionContext(),
        )

        self.assertEqual(
            result.resolution,
            MemoryResolutionType.EXACT_DUPLICATE,
        )

        self.assertEqual(
            result.reason_code,
            "same_fingerprint",
        )

        self.assertFalse(
            result.may_create
        )

        self.assertFalse(
            result.may_supersede
        )

    def test_no_existing_memory_is_distinct(
        self,
    ):
        candidate = self.record()

        result = self.policy.compare(
            candidate,
            None,
            MemoryResolutionContext(),
        )

        self.assertEqual(
            result.resolution,
            MemoryResolutionType.DISTINCT,
        )

        self.assertEqual(
            result.reason_code,
            "no_existing_memory",
        )

        self.assertTrue(
            result.may_create
        )

    def test_same_subject_changed_content_is_conflict(
        self,
    ):
        existing = self.record(
            content="Old synthetic fact."
        )

        candidate = self.record(
            content="Different synthetic fact."
        )

        result = self.policy.compare(
            candidate,
            existing,
            MemoryResolutionContext(),
        )

        self.assertEqual(
            result.resolution,
            MemoryResolutionType.POTENTIAL_CONFLICT,
        )

        self.assertEqual(
            result.reason_code,
            "same_subject_changed_content",
        )

        self.assertFalse(
            result.may_create
        )

        self.assertFalse(
            result.may_supersede
        )

    def test_verified_explicit_correction_can_supersede(
        self,
    ):
        existing = self.record(
            content="Old synthetic fact."
        )

        candidate = self.record(
            content="Corrected synthetic fact."
        )

        result = self.policy.compare(
            candidate,
            existing,
            MemoryResolutionContext(
                correction_explicit=True,
                correction_verified=True,
            ),
        )

        self.assertEqual(
            result.resolution,
            (
                MemoryResolutionType
                .SUPERSESSION_CANDIDATE
            ),
        )

        self.assertEqual(
            result.reason_code,
            "verified_explicit_correction",
        )

        self.assertTrue(
            result.may_supersede
        )

        self.assertFalse(
            result.may_create
        )

    def test_unverified_correction_remains_conflict(
        self,
    ):
        existing = self.record(
            content="Old synthetic fact."
        )

        candidate = self.record(
            content="Unverified correction."
        )

        result = self.policy.compare(
            candidate,
            existing,
            MemoryResolutionContext(
                correction_explicit=True,
                correction_verified=False,
            ),
        )

        self.assertEqual(
            result.resolution,
            MemoryResolutionType.POTENTIAL_CONFLICT,
        )

        self.assertFalse(
            result.may_supersede
        )

    def test_correction_target_mismatch_is_insufficient(
        self,
    ):
        existing = self.record(
            content="Existing synthetic fact.",
            subject_entity_id="synthetic:subject:a",
        )

        candidate = self.record(
            content="Candidate synthetic fact.",
            subject_entity_id="synthetic:subject:b",
        )

        result = self.policy.compare(
            candidate,
            existing,
            MemoryResolutionContext(
                correction_explicit=True,
                correction_verified=True,
            ),
        )

        self.assertEqual(
            result.resolution,
            (
                MemoryResolutionType
                .INSUFFICIENT_CONTEXT
            ),
        )

        self.assertEqual(
            result.reason_code,
            "correction_target_mismatch",
        )

    def test_non_active_candidate_is_insufficient(
        self,
    ):
        existing = self.record()

        candidate = (
            self.record(
                content="Inactive candidate."
            )
            .with_status(
                MemoryStatus.INVALIDATED
            )
        )

        result = self.policy.compare(
            candidate,
            existing,
            MemoryResolutionContext(),
        )

        self.assertEqual(
            result.reason_code,
            "candidate_not_active",
        )

        self.assertEqual(
            result.resolution,
            (
                MemoryResolutionType
                .INSUFFICIENT_CONTEXT
            ),
        )

    def test_non_active_existing_is_insufficient(
        self,
    ):
        existing = (
            self.record(
                content="Inactive existing fact."
            )
            .with_status(
                MemoryStatus.INVALIDATED
            )
        )

        candidate = self.record(
            content="Candidate fact."
        )

        result = self.policy.compare(
            candidate,
            existing,
            MemoryResolutionContext(),
        )

        self.assertEqual(
            result.reason_code,
            "existing_not_active",
        )

    def test_different_scope_is_distinct(
        self,
    ):
        existing = self.record(
            kind=MemoryKind.SEMANTIC,
            subject_entity_id="synthetic:subject:a",
        )

        candidate = self.record(
            content="Different scoped memory.",
            kind=MemoryKind.PREFERENCE,
            subject_entity_id="synthetic:subject:b",
        )

        result = self.policy.compare(
            candidate,
            existing,
            MemoryResolutionContext(),
        )

        self.assertEqual(
            result.resolution,
            MemoryResolutionType.DISTINCT,
        )

        self.assertEqual(
            result.reason_code,
            "different_memory_scope",
        )

        self.assertTrue(
            result.may_create
        )


if __name__ == "__main__":
    unittest.main()
