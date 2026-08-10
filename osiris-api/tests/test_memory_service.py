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
)
from osiris_core.memory_repository import (
    PostgresMemoryRepository,
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
        self.create_calls = []

        self.duplicates = []
        self.created_result = None

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

    async def create(
        self,
        record,
    ):
        self.create_calls.append(
            record
        )

        if self.created_result is not None:
            return self.created_result

        return record


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
        kind=MemoryKind.PREFERENCE,
        source_type=MemorySourceType.USER,
        source_ref="synthetic:memory-service",
        content="Synthetic memory service fact.",
    ):
        return MemoryRecord.new(
            kind=kind,
            content=content,
            source_type=source_type,
            source_ref=source_ref,
        )

    async def test_rejected_candidate_does_not_query_or_write(
        self,
    ):
        record = self.record()

        result = await self.service.admit(
            record,
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

        self.assertFalse(
            result.written
        )

        self.assertFalse(
            result.duplicate_found
        )

        self.assertEqual(
            self.repository.find_calls,
            [],
        )

        self.assertEqual(
            self.repository.create_calls,
            [],
        )

    async def test_review_candidate_does_not_query_or_write(
        self,
    ):
        record = self.record(
            kind=MemoryKind.SEMANTIC
        )

        result = await self.service.admit(
            record,
            MemoryAdmissionContext(
                evidence_type=(
                    MemoryEvidenceType
                    .USER_EXPLICIT
                ),
            ),
        )

        self.assertEqual(
            result.decision.disposition,
            MemoryAdmissionDisposition.REVIEW,
        )

        self.assertFalse(
            result.written
        )

        self.assertFalse(
            result.duplicate_found
        )

        self.assertEqual(
            self.repository.find_calls,
            [],
        )

        self.assertEqual(
            self.repository.create_calls,
            [],
        )

    async def test_admitted_candidate_checks_duplicate(
        self,
    ):
        record = self.record()

        await self.service.admit(
            record,
            MemoryAdmissionContext(
                evidence_type=(
                    MemoryEvidenceType
                    .USER_EXPLICIT
                ),
            ),
        )

        self.assertEqual(
            len(
                self.repository.find_calls
            ),
            1,
        )

        call = (
            self.repository.find_calls[0]
        )

        self.assertEqual(
            call["fingerprint"],
            record.fingerprint,
        )

        self.assertEqual(
            call["limit"],
            1,
        )

    async def test_duplicate_returns_existing_without_insert(
        self,
    ):
        record = self.record()

        existing = self.record(
            content=record.content
        )

        self.repository.duplicates = [
            existing
        ]

        result = await self.service.admit(
            record,
            MemoryAdmissionContext(
                evidence_type=(
                    MemoryEvidenceType
                    .USER_EXPLICIT
                ),
            ),
        )

        self.assertTrue(
            result.duplicate_found
        )

        self.assertFalse(
            result.written
        )

        self.assertEqual(
            result.duplicate,
            existing,
        )

        self.assertEqual(
            self.repository.create_calls,
            [],
        )

    async def test_non_duplicate_is_created_once(
        self,
    ):
        record = self.record()

        result = await self.service.admit(
            record,
            MemoryAdmissionContext(
                evidence_type=(
                    MemoryEvidenceType
                    .USER_EXPLICIT
                ),
            ),
        )

        self.assertTrue(
            result.written
        )

        self.assertFalse(
            result.duplicate_found
        )

        self.assertEqual(
            result.stored,
            record,
        )

        self.assertEqual(
            len(
                self.repository.create_calls
            ),
            1,
        )

        self.assertIs(
            self.repository.create_calls[0],
            record,
        )

    async def test_explicit_semantic_memory_can_be_written(
        self,
    ):
        record = self.record(
            kind=MemoryKind.SEMANTIC,
        )

        result = await self.service.admit(
            record,
            MemoryAdmissionContext(
                evidence_type=(
                    MemoryEvidenceType
                    .USER_EXPLICIT
                ),
                explicit_persistence=True,
            ),
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

    async def test_verified_system_observation_can_be_written(
        self,
    ):
        record = self.record(
            kind=MemoryKind.OBSERVATION,
            source_type=(
                MemorySourceType.SYSTEM
            ),
        )

        result = await self.service.admit(
            record,
            MemoryAdmissionContext(
                evidence_type=(
                    MemoryEvidenceType
                    .SYSTEM_VERIFIED
                ),
                verified=True,
            ),
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


if __name__ == "__main__":
    unittest.main()
