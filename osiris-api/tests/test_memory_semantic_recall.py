import unittest

from osiris_core.memory_models import (
    MemoryKind,
    MemoryRecord,
    MemorySourceType,
    MemoryStatus,
)
from osiris_core.memory_semantic_index import (
    SemanticMemoryHit,
)
from osiris_core.memory_semantic_recall import (
    CanonicalSemanticMemoryRecall,
    HydratedSemanticMemory,
)


class FakeSemanticIndex:
    def __init__(self):
        self.hits = []
        self.calls = []

    async def search(
        self,
        query,
        *,
        limit=10,
    ):
        self.calls.append(
            {
                "query": query,
                "limit": limit,
            }
        )

        return list(
            self.hits
        )


class FakeRepository:
    def __init__(self):
        self.records = {}
        self.get_calls = []

    def get(
        self,
        memory_id,
    ):
        self.get_calls.append(
            memory_id
        )

        return self.records.get(
            memory_id
        )


class SemanticMemoryRecallTests(
    unittest.IsolatedAsyncioTestCase
):
    def setUp(self):
        self.index = FakeSemanticIndex()
        self.repository = (
            FakeRepository()
        )

        self.recall = (
            CanonicalSemanticMemoryRecall(
                semantic_index=self.index,
                repository=self.repository,
            )
        )

    def record(
        self,
        *,
        content="Synthetic canonical memory.",
    ):
        return MemoryRecord.new(
            kind=MemoryKind.SEMANTIC,
            content=content,
            source_type=MemorySourceType.SYSTEM,
            source_ref="synthetic:recall",
            subject_entity_id=(
                "synthetic:subject"
            ),
        )

    async def test_hydrates_active_memory(self):
        record = self.record()

        self.repository.records[
            record.id
        ] = record

        self.index.hits = [
            SemanticMemoryHit(
                memory_id=record.id,
                score=0.91,
            )
        ]

        results = await self.recall.recall(
            "synthetic query",
            limit=5,
        )

        self.assertEqual(
            len(results),
            1,
        )

        self.assertIs(
            results[0].record,
            record,
        )

        self.assertEqual(
            results[0].score,
            0.91,
        )

    async def test_missing_memory_is_discarded(self):
        self.index.hits = [
            SemanticMemoryHit(
                memory_id="missing-id",
                score=0.8,
            )
        ]

        results = await self.recall.recall(
            "query"
        )

        self.assertEqual(
            results,
            [],
        )

    async def test_invalidated_memory_is_discarded(self):
        record = (
            self.record()
            .with_status(
                MemoryStatus.INVALIDATED
            )
        )

        self.repository.records[
            record.id
        ] = record

        self.index.hits = [
            SemanticMemoryHit(
                memory_id=record.id,
                score=0.8,
            )
        ]

        results = await self.recall.recall(
            "query"
        )

        self.assertEqual(
            results,
            [],
        )

    async def test_superseded_memory_is_discarded(self):
        original = self.record(
            content="Old memory."
        )

        replacement = self.record(
            content="Replacement memory."
        )

        superseded = (
            original.with_status(
                MemoryStatus.SUPERSEDED,
                superseded_by_id=(
                    replacement.id
                ),
            )
        )

        self.repository.records[
            superseded.id
        ] = superseded

        self.index.hits = [
            SemanticMemoryHit(
                memory_id=superseded.id,
                score=0.9,
            )
        ]

        results = await self.recall.recall(
            "query"
        )

        self.assertEqual(
            results,
            [],
        )

    async def test_duplicate_hits_are_hydrated_once(self):
        record = self.record()

        self.repository.records[
            record.id
        ] = record

        self.index.hits = [
            SemanticMemoryHit(
                memory_id=record.id,
                score=0.95,
            ),
            SemanticMemoryHit(
                memory_id=record.id,
                score=0.70,
            ),
        ]

        results = await self.recall.recall(
            "query"
        )

        self.assertEqual(
            len(results),
            1,
        )

        self.assertEqual(
            self.repository.get_calls,
            [
                record.id
            ],
        )

        self.assertEqual(
            results[0].score,
            0.95,
        )

    async def test_preserves_semantic_rank_order(self):
        first = self.record(
            content="First."
        )

        second = self.record(
            content="Second."
        )

        self.repository.records[
            first.id
        ] = first

        self.repository.records[
            second.id
        ] = second

        self.index.hits = [
            SemanticMemoryHit(
                memory_id=first.id,
                score=0.92,
            ),
            SemanticMemoryHit(
                memory_id=second.id,
                score=0.81,
            ),
        ]

        results = await self.recall.recall(
            "query"
        )

        self.assertEqual(
            [
                item.record.id
                for item in results
            ],
            [
                first.id,
                second.id,
            ],
        )

    async def test_passes_query_and_limit_to_index(self):
        await self.recall.recall(
            "canonical query",
            limit=7,
        )

        self.assertEqual(
            self.index.calls,
            [
                {
                    "query": (
                        "canonical query"
                    ),
                    "limit": 7,
                }
            ],
        )

    def test_result_requires_memory_record(self):
        with self.assertRaises(
            TypeError
        ):
            HydratedSemanticMemory(
                record="not-a-memory",
                score=0.5,
            )

    def test_result_rejects_boolean_score(self):
        with self.assertRaises(
            TypeError
        ):
            HydratedSemanticMemory(
                record=self.record(),
                score=True,
            )

    def test_result_rejects_nonfinite_score(self):
        for score in (
            float("nan"),
            float("inf"),
            float("-inf"),
        ):
            with self.subTest(
                score=score
            ):
                with self.assertRaises(
                    ValueError
                ):
                    HydratedSemanticMemory(
                        record=self.record(),
                        score=score,
                    )


if __name__ == "__main__":
    unittest.main()
