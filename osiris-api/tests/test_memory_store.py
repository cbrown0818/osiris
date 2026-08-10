import json
import unittest
from uuid import uuid4

from osiris_core.memory_models import (
    MemoryKind,
    MemoryRecord,
    MemorySourceType,
    MemoryStatus,
)
from osiris_core.memory_store import (
    memory_record_from_db,
    memory_record_to_db,
)


class MemoryStoreMappingTests(
    unittest.TestCase
):
    def test_record_round_trip(
        self,
    ) -> None:
        original = MemoryRecord.new(
            kind=MemoryKind.SEMANTIC,
            content="A generic fact.",
            source_type=(
                MemorySourceType.USER
            ),
            metadata={
                "example": True,
            },
        )

        row = memory_record_to_db(
            original
        )

        restored = memory_record_from_db(
            row
        )

        self.assertEqual(
            restored,
            original,
        )

        self.assertEqual(
            row["fingerprint"],
            original.fingerprint,
        )

    def test_tampered_fingerprint_is_rejected(
        self,
    ) -> None:
        record = MemoryRecord.new(
            kind=MemoryKind.SEMANTIC,
            content="A generic fact.",
        )

        row = memory_record_to_db(
            record
        )

        row["fingerprint"] = (
            "0" * 64
        )

        with self.assertRaises(
            ValueError
        ):
            memory_record_from_db(
                row
            )

    def test_json_metadata_is_accepted(
        self,
    ) -> None:
        record = MemoryRecord.new(
            kind=MemoryKind.OBSERVATION,
            content=(
                "Synthetic observation."
            ),
            metadata={
                "sensor": "synthetic",
            },
        )

        row = memory_record_to_db(
            record
        )

        row["metadata"] = json.dumps(
            row["metadata"]
        )

        restored = memory_record_from_db(
            row
        )

        self.assertEqual(
            restored.metadata,
            {
                "sensor": "synthetic",
            },
        )


    def test_postgres_uuid_supersession_is_normalized(
        self,
    ) -> None:
        replacement_id = uuid4()

        record = (
            MemoryRecord.new(
                kind=MemoryKind.SEMANTIC,
                content="Old generic fact.",
            )
            .with_status(
                MemoryStatus.SUPERSEDED,
                superseded_by_id=str(
                    replacement_id
                ),
            )
        )

        row = memory_record_to_db(
            record
        )

        row["superseded_by_id"] = (
            replacement_id
        )

        restored = memory_record_from_db(
            row
        )

        self.assertEqual(
            restored.superseded_by_id,
            str(replacement_id),
        )


if __name__ == "__main__":
    unittest.main()
