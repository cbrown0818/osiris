import unittest

from osiris_core.memory_models import (
    MemoryKind,
    MemoryRecord,
    MemorySourceType,
    MemoryStatus,
)
from osiris_core.memory_semantic_rebuild import (
    CanonicalSemanticIndexRebuilder,
    SemanticRebuildReport,
)


class FakeRepository:
    def __init__(
        self,
        pages,
    ):
        self.pages = list(pages)
        self.calls = []

    async def list(
        self,
        *,
        status=None,
        limit=100,
        offset=0,
        **kwargs,
    ):
        self.calls.append(
            {
                "status": status,
                "limit": limit,
                "offset": offset,
            }
        )

        if not self.pages:
            return []

        return list(
            self.pages.pop(0)
        )


class FakeSemanticIndex:
    def __init__(self):
        self.indexed = []
        self.fail_ids = set()
        self.skip_ids = set()

    def is_indexable(
        self,
        record,
    ):
        return (
            record.id
            not in self.skip_ids
        )

    async def index(
        self,
        record,
    ):
        if record.id in self.fail_ids:
            raise RuntimeError(
                "synthetic indexing failure"
            )

        self.indexed.append(
            record.id
        )

        return True


class SemanticIndexRebuildTests(
    unittest.IsolatedAsyncioTestCase
):
    def record(
        self,
        content,
    ):
        return MemoryRecord.new(
            kind=MemoryKind.SEMANTIC,
            content=content,
            source_type=MemorySourceType.SYSTEM,
            source_ref="synthetic:rebuild",
            subject_entity_id=(
                "synthetic:subject"
            ),
        )

    async def test_rebuild_indexes_active_records(
        self,
    ):
        first = self.record(
            "First memory."
        )

        second = self.record(
            "Second memory."
        )

        repository = FakeRepository(
            [
                [
                    first,
                    second,
                ]
            ]
        )

        index = FakeSemanticIndex()

        rebuilder = (
            CanonicalSemanticIndexRebuilder(
                repository=repository,
                semantic_index=index,
                batch_size=500,
            )
        )

        report = await rebuilder.rebuild()

        self.assertEqual(
            report,
            SemanticRebuildReport(
                scanned=2,
                indexed=2,
                skipped=0,
                failed=0,
            ),
        )

        self.assertEqual(
            index.indexed,
            [
                first.id,
                second.id,
            ],
        )

    async def test_rebuild_requests_active_only(
        self,
    ):
        repository = FakeRepository(
            [[]]
        )

        rebuilder = (
            CanonicalSemanticIndexRebuilder(
                repository=repository,
                semantic_index=(
                    FakeSemanticIndex()
                ),
            )
        )

        await rebuilder.rebuild()

        self.assertEqual(
            repository.calls,
            [
                {
                    "status": (
                        MemoryStatus.ACTIVE
                    ),
                    "limit": 500,
                    "offset": 0,
                }
            ],
        )

    async def test_rebuild_paginates_all_records(
        self,
    ):
        first_page = [
            self.record(
                f"Memory {i}"
            )
            for i in range(3)
        ]

        second_page = [
            self.record(
                "Final memory"
            )
        ]

        repository = FakeRepository(
            [
                first_page,
                second_page,
            ]
        )

        rebuilder = (
            CanonicalSemanticIndexRebuilder(
                repository=repository,
                semantic_index=(
                    FakeSemanticIndex()
                ),
                batch_size=3,
            )
        )

        report = await rebuilder.rebuild()

        self.assertEqual(
            report.scanned,
            4,
        )

        self.assertEqual(
            repository.calls,
            [
                {
                    "status": (
                        MemoryStatus.ACTIVE
                    ),
                    "limit": 3,
                    "offset": 0,
                },
                {
                    "status": (
                        MemoryStatus.ACTIVE
                    ),
                    "limit": 3,
                    "offset": 3,
                },
            ],
        )

    async def test_rebuild_skips_non_indexable(
        self,
    ):
        record = self.record(
            "Skip me."
        )

        repository = FakeRepository(
            [[record]]
        )

        index = FakeSemanticIndex()
        index.skip_ids.add(
            record.id
        )

        rebuilder = (
            CanonicalSemanticIndexRebuilder(
                repository=repository,
                semantic_index=index,
            )
        )

        report = await rebuilder.rebuild()

        self.assertEqual(
            report,
            SemanticRebuildReport(
                scanned=1,
                indexed=0,
                skipped=1,
                failed=0,
            ),
        )

    async def test_rebuild_counts_failures_and_continues(
        self,
    ):
        bad = self.record(
            "Bad memory."
        )

        good = self.record(
            "Good memory."
        )

        repository = FakeRepository(
            [[bad, good]]
        )

        index = FakeSemanticIndex()
        index.fail_ids.add(
            bad.id
        )

        rebuilder = (
            CanonicalSemanticIndexRebuilder(
                repository=repository,
                semantic_index=index,
            )
        )

        report = await rebuilder.rebuild()

        self.assertEqual(
            report,
            SemanticRebuildReport(
                scanned=2,
                indexed=1,
                skipped=0,
                failed=1,
            ),
        )

        self.assertEqual(
            index.indexed,
            [
                good.id
            ],
        )

    def test_rejects_bad_batch_size(
        self,
    ):
        for value in (
            0,
            501,
            True,
        ):
            with self.subTest(
                value=value
            ):
                with self.assertRaises(
                    ValueError
                ):
                    CanonicalSemanticIndexRebuilder(
                        repository=(
                            FakeRepository(
                                [[]]
                            )
                        ),
                        semantic_index=(
                            FakeSemanticIndex()
                        ),
                        batch_size=value,
                    )

    def test_report_requires_balanced_counts(
        self,
    ):
        with self.assertRaises(
            ValueError
        ):
            SemanticRebuildReport(
                scanned=2,
                indexed=2,
                skipped=1,
                failed=0,
            )


if __name__ == "__main__":
    unittest.main()
