import unittest

from osiris_core.memory_models import (
    MemoryKind,
    MemoryRecord,
    MemorySourceType,
    MemoryStatus,
)
from osiris_core.memory_semantic_index import (
    CANONICAL_MEMORY_COLLECTION,
    CanonicalMemorySemanticIndex,
    MemorySemanticIndexError,
    SemanticMemoryHit,
)


class FakeEmbedder:
    def __init__(self):
        self.calls = []
        self.vector = [0.1, 0.2, 0.3]

    async def embed(self, text):
        self.calls.append(text)
        return list(self.vector)


class FakeVectorStore:
    def __init__(self):
        self.upserts = []
        self.deletes = []
        self.searches = []
        self.search_results = []

    async def upsert(
        self,
        *,
        collection,
        point_id,
        vector,
        payload,
    ):
        self.upserts.append(
            {
                "collection": collection,
                "point_id": point_id,
                "vector": list(vector),
                "payload": dict(payload),
            }
        )

    async def delete(
        self,
        *,
        collection,
        point_id,
    ):
        self.deletes.append(
            {
                "collection": collection,
                "point_id": point_id,
            }
        )

    async def search(
        self,
        *,
        collection,
        vector,
        limit,
    ):
        self.searches.append(
            {
                "collection": collection,
                "vector": list(vector),
                "limit": limit,
            }
        )

        return list(
            self.search_results
        )


class MemorySemanticIndexTests(
    unittest.IsolatedAsyncioTestCase
):
    def setUp(self):
        self.embedder = FakeEmbedder()
        self.vector_store = FakeVectorStore()

        self.index = CanonicalMemorySemanticIndex(
            embedder=self.embedder,
            vector_store=self.vector_store,
        )

    def record(
        self,
        *,
        content="Synthetic canonical memory.",
        kind=MemoryKind.SEMANTIC,
        subject_entity_id="synthetic:subject",
    ):
        return MemoryRecord.new(
            kind=kind,
            content=content,
            source_type=MemorySourceType.SYSTEM,
            source_ref="synthetic:semantic-index",
            subject_entity_id=subject_entity_id,
        )

    def test_default_collection_is_canonical(self):
        self.assertEqual(
            self.index.collection,
            CANONICAL_MEMORY_COLLECTION,
        )

        self.assertEqual(
            self.index.collection,
            "osiris_canonical_memories",
        )

    def test_active_memory_is_indexable(self):
        record = self.record()

        self.assertTrue(
            self.index.is_indexable(record)
        )

    def test_non_active_memory_is_not_indexable(self):
        record = (
            self.record()
            .with_status(
                MemoryStatus.INVALIDATED
            )
        )

        self.assertFalse(
            self.index.is_indexable(record)
        )

    async def test_index_embeds_memory_content(self):
        record = self.record(
            content="Synthetic indexed content."
        )

        result = await self.index.index(
            record
        )

        self.assertTrue(result)

        self.assertEqual(
            self.embedder.calls,
            [
                "Synthetic indexed content."
            ],
        )

        self.assertEqual(
            len(self.vector_store.upserts),
            1,
        )

        call = (
            self.vector_store.upserts[0]
        )

        self.assertEqual(
            call["collection"],
            CANONICAL_MEMORY_COLLECTION,
        )

        self.assertEqual(
            call["point_id"],
            record.id,
        )

        self.assertEqual(
            call["vector"],
            [0.1, 0.2, 0.3],
        )

    async def test_non_active_memory_does_not_embed_or_write(
        self,
    ):
        record = (
            self.record()
            .with_status(
                MemoryStatus.INVALIDATED
            )
        )

        result = await self.index.index(
            record
        )

        self.assertFalse(result)

        self.assertEqual(
            self.embedder.calls,
            [],
        )

        self.assertEqual(
            self.vector_store.upserts,
            [],
        )

    def test_payload_contains_reference_metadata_only(
        self,
    ):
        record = self.record(
            kind=MemoryKind.PREFERENCE,
            subject_entity_id=(
                "synthetic:user"
            ),
        )

        payload = (
            self.index.build_payload(
                record
            )
        )

        self.assertEqual(
            payload["memory_id"],
            record.id,
        )

        self.assertEqual(
            payload["kind"],
            MemoryKind.PREFERENCE.value,
        )

        self.assertEqual(
            payload["status"],
            MemoryStatus.ACTIVE.value,
        )

        self.assertEqual(
            payload["source_type"],
            MemorySourceType.SYSTEM.value,
        )

        self.assertEqual(
            payload["subject_entity_id"],
            "synthetic:user",
        )

        self.assertEqual(
            payload["fingerprint"],
            record.fingerprint,
        )

        self.assertNotIn(
            "content",
            payload,
        )

        self.assertNotIn(
            "metadata",
            payload,
        )

        self.assertNotIn(
            "title",
            payload,
        )

    async def test_empty_embedding_is_rejected(self):
        self.embedder.vector = []

        with self.assertRaises(
            MemorySemanticIndexError
        ):
            await self.index.index(
                self.record()
            )

        self.assertEqual(
            self.vector_store.upserts,
            [],
        )

    async def test_remove_deletes_only_point_id(self):
        await self.index.remove(
            "synthetic-memory-id"
        )

        self.assertEqual(
            self.vector_store.deletes,
            [
                {
                    "collection": (
                        CANONICAL_MEMORY_COLLECTION
                    ),
                    "point_id": (
                        "synthetic-memory-id"
                    ),
                }
            ],
        )

    async def test_search_embeds_query_and_returns_hits(
        self,
    ):
        self.vector_store.search_results = [
            SemanticMemoryHit(
                memory_id="memory-1",
                score=0.95,
            ),
            SemanticMemoryHit(
                memory_id="memory-2",
                score=0.75,
            ),
        ]

        hits = await self.index.search(
            "synthetic query",
            limit=2,
        )

        self.assertEqual(
            self.embedder.calls,
            ["synthetic query"],
        )

        self.assertEqual(
            self.vector_store.searches,
            [
                {
                    "collection": (
                        CANONICAL_MEMORY_COLLECTION
                    ),
                    "vector": [
                        0.1,
                        0.2,
                        0.3,
                    ],
                    "limit": 2,
                }
            ],
        )

        self.assertEqual(
            [hit.memory_id for hit in hits],
            [
                "memory-1",
                "memory-2",
            ],
        )

        self.assertEqual(
            [hit.score for hit in hits],
            [
                0.95,
                0.75,
            ],
        )

    async def test_search_does_not_return_memory_content(
        self,
    ):
        self.vector_store.search_results = [
            SemanticMemoryHit(
                memory_id="memory-1",
                score=0.8,
            )
        ]

        hits = await self.index.search(
            "query"
        )

        self.assertEqual(
            len(hits),
            1,
        )

        self.assertFalse(
            hasattr(
                hits[0],
                "content",
            )
        )

    async def test_search_rejects_empty_query(self):
        with self.assertRaises(
            ValueError
        ):
            await self.index.search(
                "   "
            )

        self.assertEqual(
            self.embedder.calls,
            [],
        )

    async def test_search_rejects_bad_limit(self):
        for bad_limit in (
            0,
            -1,
            101,
            True,
        ):
            with self.assertRaises(
                ValueError
            ):
                await self.index.search(
                    "query",
                    limit=bad_limit,
                )

    async def test_remove_rejects_empty_id(self):
        with self.assertRaises(
            ValueError
        ):
            await self.index.remove(
                "   "
            )

    async def test_custom_collection_is_supported(self):
        custom = (
            CanonicalMemorySemanticIndex(
                embedder=self.embedder,
                vector_store=(
                    self.vector_store
                ),
                collection=(
                    "synthetic_collection"
                ),
            )
        )

        await custom.index(
            self.record()
        )

        self.assertEqual(
            self.vector_store
            .upserts[0]["collection"],
            "synthetic_collection",
        )


if __name__ == "__main__":
    unittest.main()
