import json
import unittest
from datetime import (
    datetime,
    timedelta,
    timezone,
)
from uuid import uuid4

from osiris_core.memory_models import (
    MemoryKind,
    MemoryRecord,
    MemoryRetention,
    MemorySensitivity,
    MemorySourceType,
    MemoryStatus,
    memory_fingerprint,
)


class MemoryModelTests(
    unittest.TestCase
):
    def test_new_memory_has_safe_defaults(
        self,
    ) -> None:
        record = MemoryRecord.new(
            kind=MemoryKind.SEMANTIC,
            content="A generic fact.",
        )

        self.assertEqual(
            record.status,
            MemoryStatus.ACTIVE,
        )

        self.assertEqual(
            record.sensitivity,
            MemorySensitivity.PRIVATE,
        )

        self.assertEqual(
            record.retention,
            MemoryRetention.PERSISTENT,
        )

        self.assertEqual(
            record.source_type,
            MemorySourceType.SYSTEM,
        )

    def test_record_is_json_serializable(
        self,
    ) -> None:
        record = MemoryRecord.new(
            kind=MemoryKind.LEARNING,
            content=(
                "A synthetic learning record."
            ),
        )

        encoded = json.dumps(
            record.as_dict()
        )

        self.assertIn(
            record.id,
            encoded,
        )

    def test_content_is_normalized(
        self,
    ) -> None:
        record = MemoryRecord.new(
            kind=MemoryKind.SEMANTIC,
            content=(
                "A   fact\nwith   whitespace."
            ),
        )

        self.assertEqual(
            record.content,
            "A fact with whitespace.",
        )

    def test_fingerprint_is_stable(
        self,
    ) -> None:
        first = memory_fingerprint(
            MemoryKind.SEMANTIC,
            "A   generic fact.",
        )

        second = memory_fingerprint(
            MemoryKind.SEMANTIC,
            "A generic fact.",
        )

        self.assertEqual(
            first,
            second,
        )

    def test_kind_changes_fingerprint(
        self,
    ) -> None:
        semantic = memory_fingerprint(
            MemoryKind.SEMANTIC,
            "Generic content.",
        )

        episodic = memory_fingerprint(
            MemoryKind.EPISODIC,
            "Generic content.",
        )

        self.assertNotEqual(
            semantic,
            episodic,
        )

    def test_empty_content_is_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            ValueError
        ):
            MemoryRecord.new(
                kind=MemoryKind.SEMANTIC,
                content="   ",
            )

    def test_confidence_bounds(
        self,
    ) -> None:
        for value in (
            -0.1,
            1.1,
        ):
            with self.subTest(
                value=value
            ):
                with self.assertRaises(
                    ValueError
                ):
                    MemoryRecord.new(
                        kind=(
                            MemoryKind.SEMANTIC
                        ),
                        content=(
                            "Generic fact."
                        ),
                        confidence=value,
                    )

    def test_importance_bounds(
        self,
    ) -> None:
        for value in (
            0,
            11,
        ):
            with self.subTest(
                value=value
            ):
                with self.assertRaises(
                    ValueError
                ):
                    MemoryRecord.new(
                        kind=(
                            MemoryKind.SEMANTIC
                        ),
                        content=(
                            "Generic fact."
                        ),
                        importance=value,
                    )

    def test_naive_datetime_is_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            ValueError
        ):
            MemoryRecord.new(
                kind=MemoryKind.OBSERVATION,
                content=(
                    "Synthetic observation."
                ),
                observed_at=datetime.now(),
            )

    def test_invalid_validity_window_is_rejected(
        self,
    ) -> None:
        start = datetime.now(
            timezone.utc
        )

        end = start - timedelta(
            minutes=1
        )

        with self.assertRaises(
            ValueError
        ):
            MemoryRecord.new(
                kind=MemoryKind.SEMANTIC,
                content="Generic fact.",
                valid_from=start,
                valid_until=end,
            )

    def test_supersede_preserves_identity(
        self,
    ) -> None:
        record = MemoryRecord.new(
            kind=MemoryKind.SEMANTIC,
            content="Old generic fact.",
        )

        replacement_id = str(
            uuid4()
        )

        updated = record.with_status(
            MemoryStatus.SUPERSEDED,
            superseded_by_id=(
                replacement_id
            ),
        )

        self.assertEqual(
            updated.id,
            record.id,
        )

        self.assertEqual(
            updated.status,
            MemoryStatus.SUPERSEDED,
        )

        self.assertEqual(
            updated.superseded_by_id,
            replacement_id,
        )

        self.assertGreaterEqual(
            updated.updated_at,
            record.updated_at,
        )


    def test_updated_before_created_is_rejected(
        self,
    ) -> None:
        created = datetime.now(
            timezone.utc
        )

        updated = created - timedelta(
            seconds=1
        )

        with self.assertRaises(
            ValueError
        ):
            MemoryRecord(
                id=str(uuid4()),
                kind=MemoryKind.SEMANTIC,
                content="Generic fact.",
                created_at=created,
                updated_at=updated,
            )

    def test_active_memory_cannot_reference_replacement(
        self,
    ) -> None:
        with self.assertRaises(
            ValueError
        ):
            MemoryRecord(
                id=str(uuid4()),
                kind=MemoryKind.SEMANTIC,
                content="Generic fact.",
                superseded_by_id=str(
                    uuid4()
                ),
            )


    def test_memory_cannot_supersede_itself(
        self,
    ) -> None:
        memory_id = str(
            uuid4()
        )

        with self.assertRaises(
            ValueError
        ):
            MemoryRecord(
                id=memory_id,
                kind=MemoryKind.SEMANTIC,
                content="Generic fact.",
                status=(
                    MemoryStatus.SUPERSEDED
                ),
                superseded_by_id=memory_id,
            )


if __name__ == "__main__":
    unittest.main()
