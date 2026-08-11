import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from qdrant_client.models import Distance

from osiris_core.memory_semantic_adapters import (
    DEFAULT_EMBEDDING_MODEL,
    OllamaMemoryEmbedder,
    QdrantMemoryVectorStore,
)
from osiris_core.memory_semantic_index import (
    MemorySemanticIndexError,
)


class FakeHTTPResponse:
    def __init__(
        self,
        *,
        payload=None,
        status_code=200,
        json_error=None,
    ):
        self._payload = payload
        self.status_code = status_code
        self._json_error = json_error

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request(
                "POST",
                "http://synthetic/api/embed",
            )
            response = httpx.Response(
                self.status_code,
                request=request,
            )
            raise httpx.HTTPStatusError(
                "synthetic HTTP error",
                request=request,
                response=response,
            )

    def json(self):
        if self._json_error is not None:
            raise self._json_error

        return self._payload


class FakeAsyncHTTPClient:
    response = None
    posts = []

    def __init__(
        self,
        *,
        timeout,
    ):
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(
        self,
        exc_type,
        exc,
        tb,
    ):
        return False

    async def post(
        self,
        url,
        *,
        json,
    ):
        type(self).posts.append(
            {
                "url": url,
                "json": json,
                "timeout": self.timeout,
            }
        )

        return type(self).response


class FakeQdrantClient:
    def __init__(self):
        self.collection_exists_result = False

        self.create_calls = []
        self.get_calls = []
        self.upsert_calls = []
        self.delete_calls = []
        self.query_calls = []

        self.collection_size = None
        self.query_points_result = (
            SimpleNamespace(
                points=[]
            )
        )

    def collection_exists(
        self,
        collection_name,
    ):
        return self.collection_exists_result

    def create_collection(
        self,
        *,
        collection_name,
        vectors_config,
    ):
        self.create_calls.append(
            {
                "collection_name": collection_name,
                "vectors_config": vectors_config,
            }
        )

    def get_collection(
        self,
        collection_name,
    ):
        self.get_calls.append(
            collection_name
        )

        return SimpleNamespace(
            config=SimpleNamespace(
                params=SimpleNamespace(
                    vectors=SimpleNamespace(
                        size=self.collection_size
                    )
                )
            )
        )

    def upsert(
        self,
        *,
        collection_name,
        points,
        wait,
    ):
        self.upsert_calls.append(
            {
                "collection_name": collection_name,
                "points": points,
                "wait": wait,
            }
        )

    def delete(
        self,
        *,
        collection_name,
        points_selector,
        wait,
    ):
        self.delete_calls.append(
            {
                "collection_name": collection_name,
                "points_selector": points_selector,
                "wait": wait,
            }
        )

    def query_points(
        self,
        *,
        collection_name,
        query,
        limit,
        with_payload,
        with_vectors,
    ):
        self.query_calls.append(
            {
                "collection_name": collection_name,
                "query": list(query),
                "limit": limit,
                "with_payload": with_payload,
                "with_vectors": with_vectors,
            }
        )

        return self.query_points_result


class OllamaMemoryEmbedderTests(
    unittest.IsolatedAsyncioTestCase
):
    def setUp(self):
        FakeAsyncHTTPClient.posts = []
        FakeAsyncHTTPClient.response = None

    async def test_embed_uses_api_embed(self):
        FakeAsyncHTTPClient.response = (
            FakeHTTPResponse(
                payload={
                    "embeddings": [
                        [0.1, 0.2, 0.3]
                    ]
                }
            )
        )

        embedder = OllamaMemoryEmbedder(
            base_url="http://synthetic:11434/",
            model="synthetic-embedder",
            timeout_seconds=12,
        )

        with patch(
            "osiris_core."
            "memory_semantic_adapters."
            "httpx.AsyncClient",
            FakeAsyncHTTPClient,
        ):
            vector = await embedder.embed(
                "synthetic text"
            )

        self.assertEqual(
            vector,
            [0.1, 0.2, 0.3],
        )

        self.assertEqual(
            FakeAsyncHTTPClient.posts,
            [
                {
                    "url": (
                        "http://synthetic:11434"
                        "/api/embed"
                    ),
                    "json": {
                        "model": (
                            "synthetic-embedder"
                        ),
                        "input": (
                            "synthetic text"
                        ),
                    },
                    "timeout": 12.0,
                }
            ],
        )

    def test_default_model_is_nomic(self):
        embedder = OllamaMemoryEmbedder(
            base_url="http://synthetic"
        )

        self.assertEqual(
            embedder.model,
            DEFAULT_EMBEDDING_MODEL,
        )

        self.assertEqual(
            embedder.model,
            "nomic-embed-text",
        )

    async def test_embed_rejects_empty_text(self):
        embedder = OllamaMemoryEmbedder(
            base_url="http://synthetic"
        )

        with self.assertRaises(
            ValueError
        ):
            await embedder.embed(
                "   "
            )

    async def test_http_failure_is_translated(self):
        FakeAsyncHTTPClient.response = (
            FakeHTTPResponse(
                status_code=500,
            )
        )

        embedder = OllamaMemoryEmbedder(
            base_url="http://synthetic"
        )

        with patch(
            "osiris_core."
            "memory_semantic_adapters."
            "httpx.AsyncClient",
            FakeAsyncHTTPClient,
        ):
            with self.assertRaises(
                MemorySemanticIndexError
            ):
                await embedder.embed(
                    "synthetic text"
                )

    async def test_invalid_json_is_translated(self):
        FakeAsyncHTTPClient.response = (
            FakeHTTPResponse(
                json_error=ValueError(
                    "synthetic json failure"
                )
            )
        )

        embedder = OllamaMemoryEmbedder(
            base_url="http://synthetic"
        )

        with patch(
            "osiris_core."
            "memory_semantic_adapters."
            "httpx.AsyncClient",
            FakeAsyncHTTPClient,
        ):
            with self.assertRaises(
                MemorySemanticIndexError
            ):
                await embedder.embed(
                    "synthetic text"
                )

    async def test_invalid_embedding_shape_is_rejected(self):
        FakeAsyncHTTPClient.response = (
            FakeHTTPResponse(
                payload={
                    "embeddings": []
                }
            )
        )

        embedder = OllamaMemoryEmbedder(
            base_url="http://synthetic"
        )

        with patch(
            "osiris_core."
            "memory_semantic_adapters."
            "httpx.AsyncClient",
            FakeAsyncHTTPClient,
        ):
            with self.assertRaises(
                MemorySemanticIndexError
            ):
                await embedder.embed(
                    "synthetic text"
                )

    async def test_non_numeric_embedding_is_rejected(self):
        FakeAsyncHTTPClient.response = (
            FakeHTTPResponse(
                payload={
                    "embeddings": [
                        [0.1, "bad", 0.3]
                    ]
                }
            )
        )

        embedder = OllamaMemoryEmbedder(
            base_url="http://synthetic"
        )

        with patch(
            "osiris_core."
            "memory_semantic_adapters."
            "httpx.AsyncClient",
            FakeAsyncHTTPClient,
        ):
            with self.assertRaises(
                MemorySemanticIndexError
            ):
                await embedder.embed(
                    "synthetic text"
                )


class QdrantMemoryVectorStoreTests(
    unittest.IsolatedAsyncioTestCase
):
    def setUp(self):
        self.client = FakeQdrantClient()

        self.store = QdrantMemoryVectorStore(
            url="http://synthetic:6333",
            client=self.client,
        )

    async def test_upsert_creates_collection_lazily(self):
        await self.store.upsert(
            collection="synthetic_collection",
            point_id="memory-1",
            vector=[0.1, 0.2, 0.3],
            payload={
                "memory_id": "memory-1"
            },
        )

        self.assertEqual(
            len(self.client.create_calls),
            1,
        )

        create_call = (
            self.client.create_calls[0]
        )

        self.assertEqual(
            create_call["collection_name"],
            "synthetic_collection",
        )

        self.assertEqual(
            create_call[
                "vectors_config"
            ].size,
            3,
        )

        self.assertEqual(
            create_call[
                "vectors_config"
            ].distance,
            Distance.COSINE,
        )

        self.assertEqual(
            len(self.client.upsert_calls),
            1,
        )

        point = (
            self.client
            .upsert_calls[0]["points"][0]
        )

        self.assertEqual(
            str(point.id),
            "memory-1",
        )

        self.assertEqual(
            point.vector,
            [0.1, 0.2, 0.3],
        )

        self.assertEqual(
            point.payload,
            {
                "memory_id": "memory-1"
            },
        )

    async def test_existing_collection_dimension_is_checked(
        self,
    ):
        self.client.collection_exists_result = True
        self.client.collection_size = 3

        await self.store.upsert(
            collection="synthetic_collection",
            point_id="memory-1",
            vector=[0.1, 0.2, 0.3],
            payload={},
        )

        self.assertEqual(
            self.client.create_calls,
            [],
        )

        self.assertEqual(
            self.client.get_calls,
            [
                "synthetic_collection"
            ],
        )

    async def test_existing_collection_dimension_mismatch_fails(
        self,
    ):
        self.client.collection_exists_result = True
        self.client.collection_size = 768

        with self.assertRaises(
            MemorySemanticIndexError
        ):
            await self.store.upsert(
                collection=(
                    "synthetic_collection"
                ),
                point_id="memory-1",
                vector=[
                    0.1,
                    0.2,
                    0.3,
                ],
                payload={},
            )

        self.assertEqual(
            self.client.upsert_calls,
            [],
        )

    async def test_cached_dimension_mismatch_fails(
        self,
    ):
        await self.store.upsert(
            collection="synthetic_collection",
            point_id="memory-1",
            vector=[0.1, 0.2, 0.3],
            payload={},
        )

        with self.assertRaises(
            MemorySemanticIndexError
        ):
            await self.store.upsert(
                collection=(
                    "synthetic_collection"
                ),
                point_id="memory-2",
                vector=[
                    0.1,
                    0.2,
                ],
                payload={},
            )

        self.assertEqual(
            len(self.client.create_calls),
            1,
        )

    async def test_cached_collection_is_rechecked_if_deleted(
        self,
    ):
        await self.store.upsert(
            collection="synthetic_collection",
            point_id="memory-1",
            vector=[0.1, 0.2, 0.3],
            payload={},
        )

        self.assertEqual(
            len(self.client.create_calls),
            1,
        )

        self.client.collection_exists_result = False

        await self.store.upsert(
            collection="synthetic_collection",
            point_id="memory-2",
            vector=[0.1, 0.2, 0.3],
            payload={},
        )

        self.assertEqual(
            len(self.client.create_calls),
            2,
        )

    async def test_delete_removes_point(self):
        await self.store.delete(
            collection="synthetic_collection",
            point_id="memory-1",
        )

        self.assertEqual(
            self.client.delete_calls,
            [
                {
                    "collection_name": (
                        "synthetic_collection"
                    ),
                    "points_selector": [
                        "memory-1"
                    ],
                    "wait": True,
                }
            ],
        )

    async def test_search_returns_ids_and_scores(self):
        self.client.collection_exists_result = True
        self.client.collection_size = 3

        self.client.query_points_result = (
            SimpleNamespace(
                points=[
                    SimpleNamespace(
                        id="memory-1",
                        score=0.91,
                    ),
                    SimpleNamespace(
                        id="memory-2",
                        score=0.73,
                    ),
                ]
            )
        )

        hits = await self.store.search(
            collection="synthetic_collection",
            vector=[0.1, 0.2, 0.3],
            limit=2,
        )

        self.assertEqual(
            [
                hit.memory_id
                for hit in hits
            ],
            [
                "memory-1",
                "memory-2",
            ],
        )

        self.assertEqual(
            [
                hit.score
                for hit in hits
            ],
            [
                0.91,
                0.73,
            ],
        )

        self.assertEqual(
            self.client.query_calls[0][
                "with_payload"
            ],
            False,
        )

        self.assertEqual(
            self.client.query_calls[0][
                "with_vectors"
            ],
            False,
        )

    async def test_search_rejects_invalid_limit(self):
        with self.assertRaises(
            ValueError
        ):
            await self.store.search(
                collection=(
                    "synthetic_collection"
                ),
                vector=[
                    0.1,
                    0.2,
                    0.3,
                ],
                limit=0,
            )

    async def test_vector_rejects_non_numeric_values(self):
        with self.assertRaises(
            ValueError
        ):
            await self.store.upsert(
                collection=(
                    "synthetic_collection"
                ),
                point_id="memory-1",
                vector=[
                    0.1,
                    "bad",
                ],
                payload={},
            )


if __name__ == "__main__":
    unittest.main()
