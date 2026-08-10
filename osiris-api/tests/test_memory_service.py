import unittest

from osiris_core.memory_admission import (
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
from osiris_core.memory_repository import (
    PostgresMemoryRepository,
)
from osiris_core.memory_resolution import (
    MemoryResolutionContext,
    MemoryResolutionType,
)
from osiris_core.memory_service import (
    CanonicalMemoryService,
)


class FakeRepository(
    PostgresMemoryRepository
):
    def __init__(
        self,
    ):
        super().__init__(
            database_url="synthetic://memory"
        )

        self.find_calls = []
        self.list_calls = []
        self.create_calls = []
        self.supersede_calls = []

        self.duplicates = []
        self.active_records = []

    async def find_by_fingerprint(
        self,
        fingerprint,
        *,
        status=None,
        limit=20,
    ):
        self.find_calls.append(
            {
                "fingerprint": fingerprint,
                "status": status,
                "limit": limit,
            }
        )

        return list(
            self.duplicates
        )

    async def list(
        self,
        *,
        kind=None,
        status=None,
        limit=100,
        offset=0,
    ):
        self.list_calls.append(
            {
                "kind": kind,
                "status": status,
                "limit": limit,
                "offset": offset,
            }
        )

        return list(
            self.active_records
        )

    async def create(
        self,
        record,
    ):
        self.create_calls.append(
            record
        )

        return record

    async def supersede(
        self,
        memory_id,
        replacement,
    ):
        self.supersede_calls.append(
            {
                "memory_id": memory_id,
                "replacement": replacement,
            }
        )

        old = next(
            record
            for record in self.active_records
            if record.id == memory_id
        )

        superseded = old.with_status(
            MemoryStatus.SUPERSEDED,
            superseded_by_id=(
                replacement.id
            ),
        )

        return (
            superseded,
            replacement,
        )


class MemoryServiceTests(
    unittest.IsolatedAsyncioTestCase
):
    def setUp(
        self,
    ):
        self.repository = (
            FakeRepository()
        )

        self.service = (
            CanonicalMemoryService(
                self.repository
            )
        )

    def record(
        self,
        *,
        content="Synthetic memory fact.",
        kind=MemoryKind.PREFERENCE,
        source_type=MemorySourceType.USER,
        source_ref="synthetic:memory-service",
        subject_entity_id=None,
    ):
        return MemoryRecord.new(
            kind=kind,
            content=content,
            source_type=source_type,
            source_ref=source_ref,
            subject_entity_id=(
                subject_entity_id
            ),
        )

    def user_context(
        self,
        *,
        explicit_persistence=False,
    ):
        return MemoryAdmissionContext(
            evidence_type=(
                MemoryEvidenceType
                .USER_EXPLICIT
            ),
            explicit_persistence=(
                explicit_persistence
            ),
        )

    async def test_rejected_candidate_causes_no_repository_access(
        self,
    ):
        result = await self.service.admit(
            self.record(),
            MemoryAdmissionContext(
                evidence_type=(
                    MemoryEvidenceType
                    .USER_EXPLICIT
                ),
                raw_conversation=True,
            ),
        )

        self.assertEqual(
            result.decision.disposition,
            MemoryAdmissionDisposition.REJECTED,
        )

        self.assertEqual(
            self.repository.find_calls,
            [],
        )

        self.assertEqual(
            self.repository.list_calls,
            [],
        )

        self.assertEqual(
            self.repository.create_calls,
            [],
        )

        self.assertEqual(
            self.repository.supersede_calls,
            [],
        )

    async def test_review_candidate_causes_no_repository_access(
        self,
    ):
        result = await self.service.admit(
            self.record(
                kind=MemoryKind.SEMANTIC
            ),
            self.user_context(),
        )

        self.assertEqual(
            result.decision.disposition,
            MemoryAdmissionDisposition.REVIEW,
        )

        self.assertEqual(
            self.repository.find_calls,
            [],
        )

        self.assertEqual(
            self.repository.list_calls,
            [],
        )

    async def test_exact_duplicate_does_not_write(
        self,
    ):
        candidate = self.record()

        existing = self.record(
            content=candidate.content
        )

        self.repository.duplicates = [
            existing
        ]

        result = await self.service.admit(
            candidate,
            self.user_context(),
        )

        self.assertTrue(
            result.duplicate_found
        )

        self.assertEqual(
            result.resolution.resolution,
            MemoryResolutionType.EXACT_DUPLICATE,
        )

        self.assertFalse(
            result.written
        )

        self.assertEqual(
            self.repository.create_calls,
            [],
        )

        self.assertEqual(
            self.repository.supersede_calls,
            [],
        )

    async def test_distinct_memory_is_created(
        self,
    ):
        candidate = self.record(
            subject_entity_id=(
                "synthetic:subject:new"
            )
        )

        result = await self.service.admit(
            candidate,
            self.user_context(),
        )

        self.assertEqual(
            result.resolution.resolution,
            MemoryResolutionType.DISTINCT,
        )

        self.assertTrue(
            result.written
        )

        self.assertEqual(
            len(
                self.repository.create_calls
            ),
            1,
        )

    async def test_conflict_does_not_write(
        self,
    ):
        existing = self.record(
            content="Old preference.",
            subject_entity_id=(
                "synthetic:user:cad"
            ),
        )

        candidate = self.record(
            content="Different preference.",
            subject_entity_id=(
                "synthetic:user:cad"
            ),
        )

        self.repository.active_records = [
            existing
        ]

        result = await self.service.admit(
            candidate,
            self.user_context(),
        )

        self.assertEqual(
            result.resolution.resolution,
            (
                MemoryResolutionType
                .POTENTIAL_CONFLICT
            ),
        )

        self.assertFalse(
            result.written
        )

        self.assertEqual(
            self.repository.create_calls,
            [],
        )

        self.assertEqual(
            self.repository.supersede_calls,
            [],
        )

    async def test_verified_correction_supersedes(
        self,
    ):
        existing = self.record(
            content="Old preference.",
            subject_entity_id=(
                "synthetic:user:cad"
            ),
        )

        candidate = self.record(
            content="Corrected preference.",
            subject_entity_id=(
                "synthetic:user:cad"
            ),
        )

        self.repository.active_records = [
            existing
        ]

        result = await self.service.admit(
            candidate,
            self.user_context(),
            resolution_context=(
                MemoryResolutionContext(
                    correction_explicit=True,
                    correction_verified=True,
                )
            ),
        )

        self.assertEqual(
            result.resolution.resolution,
            (
                MemoryResolutionType
                .SUPERSESSION_CANDIDATE
            ),
        )

        self.assertTrue(
            result.supersession_performed
        )

        self.assertTrue(
            result.written
        )

        self.assertEqual(
            len(
                self.repository.supersede_calls
            ),
            1,
        )

        call = (
            self.repository
            .supersede_calls[0]
        )

        self.assertEqual(
            call["memory_id"],
            existing.id,
        )

        self.assertIs(
            call["replacement"],
            candidate,
        )

        self.assertEqual(
            self.repository.create_calls,
            [],
        )

    async def test_unverified_correction_does_not_supersede(
        self,
    ):
        existing = self.record(
            content="Old preference.",
            subject_entity_id=(
                "synthetic:user:cad"
            ),
        )

        candidate = self.record(
            content="Claimed correction.",
            subject_entity_id=(
                "synthetic:user:cad"
            ),
        )

        self.repository.active_records = [
            existing
        ]

        result = await self.service.admit(
            candidate,
            self.user_context(),
            resolution_context=(
                MemoryResolutionContext(
                    correction_explicit=True,
                    correction_verified=False,
                )
            ),
        )

        self.assertEqual(
            result.resolution.resolution,
            (
                MemoryResolutionType
                .POTENTIAL_CONFLICT
            ),
        )

        self.assertFalse(
            result.supersession_performed
        )

        self.assertEqual(
            self.repository.supersede_calls,
            [],
        )

    async def test_ambiguous_scope_does_not_mutate(
        self,
    ):
        first = self.record(
            content="Existing fact A.",
            subject_entity_id=(
                "synthetic:ambiguous"
            ),
        )

        second = self.record(
            content="Existing fact B.",
            subject_entity_id=(
                "synthetic:ambiguous"
            ),
        )

        candidate = self.record(
            content="Candidate fact.",
            subject_entity_id=(
                "synthetic:ambiguous"
            ),
        )

        self.repository.active_records = [
            first,
            second,
        ]

        result = await self.service.admit(
            candidate,
            self.user_context(),
        )

        self.assertEqual(
            result.resolution.resolution,
            (
                MemoryResolutionType
                .INSUFFICIENT_CONTEXT
            ),
        )

        self.assertEqual(
            result.resolution.reason_code,
            "ambiguous_existing_scope",
        )

        self.assertFalse(
            result.written
        )

        self.assertEqual(
            self.repository.create_calls,
            [],
        )

        self.assertEqual(
            self.repository.supersede_calls,
            [],
        )

    async def test_no_subject_memory_can_be_created(
        self,
    ):
        candidate = self.record(
            subject_entity_id=None
        )

        result = await self.service.admit(
            candidate,
            self.user_context(),
        )

        self.assertEqual(
            result.resolution.resolution,
            MemoryResolutionType.DISTINCT,
        )

        self.assertEqual(
            self.repository.list_calls,
            [],
        )

        self.assertTrue(
            result.written
        )


if __name__ == "__main__":
    unittest.main()
