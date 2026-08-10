from __future__ import annotations

import json
from typing import Any, Mapping

from .memory_models import (
    MemoryKind,
    MemoryRecord,
    MemoryRetention,
    MemorySensitivity,
    MemorySourceType,
    MemoryStatus,
)


MEMORY_TABLE = "osiris_memory_records"


def _metadata_from_value(
    value: Any,
) -> dict[str, Any]:
    if value is None:
        return {}

    if isinstance(
        value,
        str,
    ):
        decoded = json.loads(
            value
        )

        if not isinstance(
            decoded,
            dict,
        ):
            raise ValueError(
                "memory metadata JSON "
                "must contain an object"
            )

        return decoded

    if isinstance(
        value,
        Mapping,
    ):
        return dict(value)

    raise TypeError(
        "memory metadata must be "
        "a mapping or JSON object"
    )


def memory_record_to_db(
    record: MemoryRecord,
) -> dict[str, Any]:
    return {
        "id": record.id,
        "kind": record.kind.value,
        "content": record.content,
        "title": record.title,
        "status": record.status.value,
        "source_type": (
            record.source_type.value
        ),
        "source_ref": record.source_ref,
        "confidence": (
            record.confidence
        ),
        "importance": (
            record.importance
        ),
        "sensitivity": (
            record.sensitivity.value
        ),
        "retention": (
            record.retention.value
        ),
        "subject_entity_id": (
            record.subject_entity_id
        ),
        "superseded_by_id": (
            record.superseded_by_id
        ),
        "created_at": (
            record.created_at
        ),
        "updated_at": (
            record.updated_at
        ),
        "observed_at": (
            record.observed_at
        ),
        "valid_from": (
            record.valid_from
        ),
        "valid_until": (
            record.valid_until
        ),
        "metadata": dict(
            record.metadata
        ),
        "fingerprint": (
            record.fingerprint
        ),
    }


def memory_record_from_db(
    row: Mapping[str, Any],
) -> MemoryRecord:
    data = dict(row)

    record = MemoryRecord(
        id=str(data["id"]),
        kind=MemoryKind(
            data["kind"]
        ),
        content=data["content"],
        title=data.get("title"),
        status=MemoryStatus(
            data["status"]
        ),
        source_type=MemorySourceType(
            data["source_type"]
        ),
        source_ref=data.get(
            "source_ref"
        ),
        confidence=float(
            data["confidence"]
        ),
        importance=int(
            data["importance"]
        ),
        sensitivity=MemorySensitivity(
            data["sensitivity"]
        ),
        retention=MemoryRetention(
            data["retention"]
        ),
        subject_entity_id=data.get(
            "subject_entity_id"
        ),
        superseded_by_id=(
            str(
                data["superseded_by_id"]
            )
            if data.get(
                "superseded_by_id"
            ) is not None
            else None
        ),
        created_at=data[
            "created_at"
        ],
        updated_at=data[
            "updated_at"
        ],
        observed_at=data.get(
            "observed_at"
        ),
        valid_from=data.get(
            "valid_from"
        ),
        valid_until=data.get(
            "valid_until"
        ),
        metadata=_metadata_from_value(
            data.get("metadata")
        ),
    )

    stored_fingerprint = data.get(
        "fingerprint"
    )

    if (
        stored_fingerprint is not None
        and stored_fingerprint
        != record.fingerprint
    ):
        raise ValueError(
            "stored memory fingerprint "
            "does not match record"
        )

    return record
