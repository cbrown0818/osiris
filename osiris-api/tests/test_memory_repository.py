import json
import unittest

from osiris_core.memory_models import (
    MemoryKind,
    MemoryRecord,
    MemoryStatus,
)
from osiris_core.memory_repository import (
    MemoryNotFoundError,
    MemoryStateConflictError,
    PostgresMemoryRepository,
)
from osiris_core.memory_store import (
    memory_record_to_db,
)


class FakeTransaction:
    def __init__(
        self,
        connection,
    ):
        self.connection = connection

    async def __aenter__(
        self,
    ):
        self.connection.transaction_entries += 1
        return self

    async def __aexit__(
        self,
        exc_type,
        exc,
        traceback,
    ):
        self.connection.transaction_exits += 1
        self.connection.last_transaction_error = (
            exc_type
        )

        return False


class FakeConnection:
    def __init__(
        self,
        *,
        fetchrow_results=None,
        fetch_results=None,
    ):
        self.fetchrow_results = list(
            fetchrow_results or []
        )

        self.fetch_results = list(
            fetch_results or []
        )

        self.fetchrow_calls = []
        self.fetch_calls = []

        self.closed = False

        self.transaction_entries = 0
        self.transaction_exits = 0
        self.last_transaction_error = None

    async def fetchrow(
        self,
        query,
        *args,
    ):
        self.fetchrow_calls.append(
            (
                query,
                args,
            )
        )

        if not self.fetchrow_results:
            return None

        return self.fetchrow_results.pop(
            0
        )

    async def fetch(
        self,
        query,
        *args,
    ):
        self.fetch_calls.append(
            (
                query,
                args,
            )
        )

        if not self.fetch_results:
            return []

        return self.fetch_results.pop(
            0
        )

    def transaction(
        self,
    ):
        return FakeTransaction(
            self
        )

    async def close(
        self,
    ):
        self.closed = True


class MemoryRepositoryTests(
    unittest.IsolatedAsyncioTestCase
):
    def repository_for(
        self,
        connection,
    ):
        async def connect(
            database_url,
        ):
            self.assertEqual(
                database_url,
                (
                    "postgresql://"
                    "synthetic.invalid/osiris"
                ),
            )

            return connection

        return PostgresMemoryRepository(
            (
                "postgresql://"
                "synthetic.invalid/osiris"
            ),
            connect=connect,
        )

    async def test_create_round_trip(
        self,
    ):
        record = MemoryRecord.new(
            kind=MemoryKind.SEMANTIC,
            content=(
                "Synthetic repository fact."
            ),
            metadata={
                "synthetic": True,
            },
        )

        row = memory_record_to_db(
            record
        )

        connection = FakeConnection(
            fetchrow_results=[
                row,
            ]
        )

        repository = self.repository_for(
            connection
        )

        created = await repository.create(
            record
        )

        self.assertEqual(
            created,
            record,
        )

        self.assertTrue(
            connection.closed
        )

        query, args = (
            connection.fetchrow_calls[0]
        )

        self.assertIn(
            "INSERT INTO "
            "osiris_memory_records",
            query,
        )

        self.assertEqual(
            json.loads(
                args[18]
            ),
            {
                "synthetic": True,
            },
        )

    async def test_get_missing_returns_none(
        self,
    ):
        record = MemoryRecord.new(
            kind=MemoryKind.SEMANTIC,
            content="Synthetic fact.",
        )

        connection = FakeConnection(
            fetchrow_results=[
                None,
            ]
        )

        repository = self.repository_for(
            connection
        )

        result = await repository.get(
            record.id
        )

        self.assertIsNone(
            result
        )

        self.assertTrue(
            connection.closed
        )

    async def test_get_rejects_invalid_uuid(
        self,
    ):
        connection = FakeConnection()

        repository = self.repository_for(
            connection
        )

        with self.assertRaises(
            ValueError
        ):
            await repository.get(
                "not-a-uuid"
            )

        self.assertFalse(
            connection.closed
        )

    async def test_list_filters_records(
        self,
    ):
        record = MemoryRecord.new(
            kind=MemoryKind.SEMANTIC,
            content="Synthetic fact.",
        )

        row = memory_record_to_db(
            record
        )

        connection = FakeConnection(
            fetch_results=[
                [
                    row,
                ],
            ]
        )

        repository = self.repository_for(
            connection
        )

        result = await repository.list(
            kind=MemoryKind.SEMANTIC,
            status=MemoryStatus.ACTIVE,
            limit=25,
            offset=0,
        )

        self.assertEqual(
            result,
            [
                record,
            ],
        )

        _, args = (
            connection.fetch_calls[0]
        )

        self.assertEqual(
            args,
            (
                "semantic",
                "active",
                25,
                0,
            ),
        )

        self.assertTrue(
            connection.closed
        )

    async def test_list_rejects_bad_bounds(
        self,
    ):
        connection = FakeConnection()

        repository = self.repository_for(
            connection
        )

        with self.assertRaises(
            ValueError
        ):
            await repository.list(
                limit=0
            )

        with self.assertRaises(
            ValueError
        ):
            await repository.list(
                offset=-1
            )

    async def test_find_by_fingerprint(
        self,
    ):
        record = MemoryRecord.new(
            kind=MemoryKind.SEMANTIC,
            content="Synthetic fact.",
        )

        row = memory_record_to_db(
            record
        )

        connection = FakeConnection(
            fetch_results=[
                [
                    row,
                ],
            ]
        )

        repository = self.repository_for(
            connection
        )

        result = (
            await repository
            .find_by_fingerprint(
                record.fingerprint,
                status=(
                    MemoryStatus.ACTIVE
                ),
            )
        )

        self.assertEqual(
            result,
            [
                record,
            ],
        )

        _, args = (
            connection.fetch_calls[0]
        )

        self.assertEqual(
            args[0],
            record.fingerprint,
        )

        self.assertEqual(
            args[1],
            "active",
        )

        self.assertTrue(
            connection.closed
        )

    async def test_find_rejects_bad_fingerprint(
        self,
    ):
        connection = FakeConnection()

        repository = self.repository_for(
            connection
        )

        with self.assertRaises(
            ValueError
        ):
            await (
                repository
                .find_by_fingerprint(
                    "not-a-fingerprint"
                )
            )

    async def test_invalidate_active_memory(
        self,
    ):
        record = MemoryRecord.new(
            kind=MemoryKind.SEMANTIC,
            content="Synthetic fact.",
        )

        invalidated = (
            record.with_status(
                MemoryStatus.INVALIDATED
            )
        )

        connection = FakeConnection(
            fetchrow_results=[
                memory_record_to_db(
                    invalidated
                ),
            ]
        )

        repository = self.repository_for(
            connection
        )

        result = await (
            repository.invalidate(
                record.id
            )
        )

        self.assertEqual(
            result.status,
            MemoryStatus.INVALIDATED,
        )

        self.assertEqual(
            result.id,
            record.id,
        )

        query, args = (
            connection.fetchrow_calls[0]
        )

        self.assertIn(
            "UPDATE osiris_memory_records",
            query,
        )

        self.assertEqual(
            args,
            (
                record.id,
            ),
        )

        self.assertTrue(
            connection.closed
        )

    async def test_invalidate_missing_raises(
        self,
    ):
        record = MemoryRecord.new(
            kind=MemoryKind.SEMANTIC,
            content="Synthetic fact.",
        )

        connection = FakeConnection(
            fetchrow_results=[
                None,
                None,
            ]
        )

        repository = self.repository_for(
            connection
        )

        with self.assertRaises(
            MemoryNotFoundError
        ):
            await repository.invalidate(
                record.id
            )

        self.assertTrue(
            connection.closed
        )

    async def test_invalidate_state_conflict(
        self,
    ):
        record = MemoryRecord.new(
            kind=MemoryKind.SEMANTIC,
            content="Synthetic fact.",
        )

        connection = FakeConnection(
            fetchrow_results=[
                None,
                {
                    "status": "invalidated",
                },
            ]
        )

        repository = self.repository_for(
            connection
        )

        with self.assertRaises(
            MemoryStateConflictError
        ):
            await repository.invalidate(
                record.id
            )

        self.assertTrue(
            connection.closed
        )

    async def test_supersede_is_atomic(
        self,
    ):
        original = MemoryRecord.new(
            kind=MemoryKind.SEMANTIC,
            content="Old synthetic fact.",
        )

        replacement = MemoryRecord.new(
            kind=MemoryKind.SEMANTIC,
            content="New synthetic fact.",
        )

        superseded = (
            original.with_status(
                MemoryStatus.SUPERSEDED,
                superseded_by_id=(
                    replacement.id
                ),
            )
        )

        connection = FakeConnection(
            fetchrow_results=[
                memory_record_to_db(
                    original
                ),
                memory_record_to_db(
                    replacement
                ),
                memory_record_to_db(
                    superseded
                ),
            ]
        )

        repository = self.repository_for(
            connection
        )

        old_result, new_result = (
            await repository.supersede(
                original.id,
                replacement,
            )
        )

        self.assertEqual(
            old_result.status,
            MemoryStatus.SUPERSEDED,
        )

        self.assertEqual(
            old_result.superseded_by_id,
            replacement.id,
        )

        self.assertEqual(
            new_result,
            replacement,
        )

        self.assertEqual(
            connection.transaction_entries,
            1,
        )

        self.assertEqual(
            connection.transaction_exits,
            1,
        )

        self.assertIsNone(
            connection.last_transaction_error
        )

        self.assertTrue(
            connection.closed
        )

    async def test_supersede_missing_raises(
        self,
    ):
        original = MemoryRecord.new(
            kind=MemoryKind.SEMANTIC,
            content="Old synthetic fact.",
        )

        replacement = MemoryRecord.new(
            kind=MemoryKind.SEMANTIC,
            content="New synthetic fact.",
        )

        connection = FakeConnection(
            fetchrow_results=[
                None,
            ]
        )

        repository = self.repository_for(
            connection
        )

        with self.assertRaises(
            MemoryNotFoundError
        ):
            await repository.supersede(
                original.id,
                replacement,
            )

        self.assertEqual(
            connection.transaction_entries,
            1,
        )

        self.assertEqual(
            connection.transaction_exits,
            1,
        )

        self.assertIs(
            connection.last_transaction_error,
            MemoryNotFoundError,
        )

        self.assertTrue(
            connection.closed
        )

    async def test_supersede_rejects_same_id(
        self,
    ):
        original = MemoryRecord.new(
            kind=MemoryKind.SEMANTIC,
            content="Old synthetic fact.",
        )

        replacement = MemoryRecord(
            id=original.id,
            kind=MemoryKind.SEMANTIC,
            content="New synthetic fact.",
        )

        connection = FakeConnection()

        repository = self.repository_for(
            connection
        )

        with self.assertRaises(
            ValueError
        ):
            await repository.supersede(
                original.id,
                replacement,
            )

        self.assertEqual(
            connection.transaction_entries,
            0,
        )

    async def test_supersede_rejects_non_active_replacement(
        self,
    ):
        original = MemoryRecord.new(
            kind=MemoryKind.SEMANTIC,
            content="Old synthetic fact.",
        )

        replacement = (
            MemoryRecord.new(
                kind=MemoryKind.SEMANTIC,
                content="New synthetic fact.",
            )
            .with_status(
                MemoryStatus.INVALIDATED
            )
        )

        connection = FakeConnection()

        repository = self.repository_for(
            connection
        )

        with self.assertRaises(
            ValueError
        ):
            await repository.supersede(
                original.id,
                replacement,
            )

        self.assertEqual(
            connection.transaction_entries,
            0,
        )


if __name__ == "__main__":
    unittest.main()
