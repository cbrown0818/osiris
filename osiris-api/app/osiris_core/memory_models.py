from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4


class MemoryKind(str, Enum):
    SEMANTIC = "semantic"
    EPISODIC = "episodic"
    LEARNING = "learning"
    PREFERENCE = "preference"
    INSTRUCTION = "instruction"
    OBSERVATION = "observation"


class MemoryStatus(str, Enum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    INVALIDATED = "invalidated"
    DELETED = "deleted"


class MemorySensitivity(str, Enum):
    INTERNAL = "internal"
    PRIVATE = "private"
    RESTRICTED = "restricted"


class MemoryRetention(str, Enum):
    SESSION = "session"
    TEMPORARY = "temporary"
    PERSISTENT = "persistent"
    PINNED = "pinned"


class MemorySourceType(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    AGENT = "agent"
    DEVICE = "device"
    DOCUMENT = "document"
    MIGRATION = "migration"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _require_aware_datetime(
    value: datetime | None,
    field_name: str,
) -> None:
    if value is None:
        return

    if (
        value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError(
            f"{field_name} must be timezone-aware"
        )


def normalize_memory_content(
    content: str,
) -> str:
    if not isinstance(content, str):
        raise TypeError(
            "memory content must be a string"
        )

    normalized = " ".join(
        content.split()
    )

    if not normalized:
        raise ValueError(
            "memory content cannot be empty"
        )

    return normalized


def memory_fingerprint(
    kind: MemoryKind | str,
    content: str,
    subject_entity_id: str | None = None,
) -> str:
    if not isinstance(kind, MemoryKind):
        kind = MemoryKind(kind)

    normalized_content = (
        normalize_memory_content(content)
    )

    normalized_subject = (
        subject_entity_id.strip()
        if isinstance(
            subject_entity_id,
            str,
        )
        and subject_entity_id.strip()
        else None
    )

    canonical = json.dumps(
        {
            "kind": kind.value,
            "content": normalized_content,
            "subject_entity_id": (
                normalized_subject
            ),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )

    return hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()


@dataclass(
    frozen=True,
    slots=True,
)
class MemoryRecord:
    id: str
    kind: MemoryKind
    content: str

    title: str | None = None

    status: MemoryStatus = (
        MemoryStatus.ACTIVE
    )

    source_type: MemorySourceType = (
        MemorySourceType.SYSTEM
    )

    source_ref: str | None = None

    confidence: float = 1.0
    importance: int = 5

    sensitivity: MemorySensitivity = (
        MemorySensitivity.PRIVATE
    )

    retention: MemoryRetention = (
        MemoryRetention.PERSISTENT
    )

    subject_entity_id: str | None = None
    superseded_by_id: str | None = None

    created_at: datetime = field(
        default_factory=utc_now
    )

    updated_at: datetime = field(
        default_factory=utc_now
    )

    observed_at: datetime | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        try:
            UUID(self.id)
        except Exception as exc:
            raise ValueError(
                "memory id must be a valid UUID"
            ) from exc

        if not isinstance(
            self.kind,
            MemoryKind,
        ):
            object.__setattr__(
                self,
                "kind",
                MemoryKind(self.kind),
            )

        if not isinstance(
            self.status,
            MemoryStatus,
        ):
            object.__setattr__(
                self,
                "status",
                MemoryStatus(self.status),
            )

        if not isinstance(
            self.source_type,
            MemorySourceType,
        ):
            object.__setattr__(
                self,
                "source_type",
                MemorySourceType(
                    self.source_type
                ),
            )

        if not isinstance(
            self.sensitivity,
            MemorySensitivity,
        ):
            object.__setattr__(
                self,
                "sensitivity",
                MemorySensitivity(
                    self.sensitivity
                ),
            )

        if not isinstance(
            self.retention,
            MemoryRetention,
        ):
            object.__setattr__(
                self,
                "retention",
                MemoryRetention(
                    self.retention
                ),
            )

        object.__setattr__(
            self,
            "content",
            normalize_memory_content(
                self.content
            ),
        )

        if self.title is not None:
            title = self.title.strip()

            object.__setattr__(
                self,
                "title",
                title or None,
            )

        if self.source_ref is not None:
            source_ref = (
                self.source_ref.strip()
            )

            object.__setattr__(
                self,
                "source_ref",
                source_ref or None,
            )

        if self.subject_entity_id is not None:
            subject = (
                self.subject_entity_id.strip()
            )

            object.__setattr__(
                self,
                "subject_entity_id",
                subject or None,
            )

        if self.superseded_by_id:
            try:
                UUID(
                    self.superseded_by_id
                )
            except Exception as exc:
                raise ValueError(
                    "superseded_by_id must "
                    "be a valid UUID"
                ) from exc

        if (
            self.status
            == MemoryStatus.SUPERSEDED
            and not self.superseded_by_id
        ):
            raise ValueError(
                "superseded memories require "
                "superseded_by_id"
            )

        if (
            self.status
            != MemoryStatus.SUPERSEDED
            and self.superseded_by_id
            is not None
        ):
            raise ValueError(
                "only superseded memories may "
                "have superseded_by_id"
            )

        if (
            self.superseded_by_id
            == self.id
        ):
            raise ValueError(
                "memory cannot supersede itself"
            )

        if (
            isinstance(
                self.confidence,
                bool,
            )
            or not isinstance(
                self.confidence,
                (int, float),
            )
            or not 0.0
            <= float(self.confidence)
            <= 1.0
        ):
            raise ValueError(
                "confidence must be "
                "between 0.0 and 1.0"
            )

        object.__setattr__(
            self,
            "confidence",
            float(self.confidence),
        )

        if (
            isinstance(
                self.importance,
                bool,
            )
            or not isinstance(
                self.importance,
                int,
            )
            or not 1
            <= self.importance
            <= 10
        ):
            raise ValueError(
                "importance must be "
                "between 1 and 10"
            )

        for field_name in (
            "created_at",
            "updated_at",
            "observed_at",
            "valid_from",
            "valid_until",
        ):
            _require_aware_datetime(
                getattr(
                    self,
                    field_name,
                ),
                field_name,
            )

        if (
            self.updated_at
            < self.created_at
        ):
            raise ValueError(
                "updated_at cannot be earlier "
                "than created_at"
            )

        if (
            self.valid_from is not None
            and self.valid_until is not None
            and self.valid_until
            < self.valid_from
        ):
            raise ValueError(
                "valid_until cannot be "
                "earlier than valid_from"
            )

        if not isinstance(
            self.metadata,
            dict,
        ):
            raise TypeError(
                "metadata must be a dictionary"
            )

        object.__setattr__(
            self,
            "metadata",
            dict(self.metadata),
        )

    @classmethod
    def new(
        cls,
        *,
        kind: MemoryKind,
        content: str,
        title: str | None = None,
        source_type: MemorySourceType = (
            MemorySourceType.SYSTEM
        ),
        source_ref: str | None = None,
        confidence: float = 1.0,
        importance: int = 5,
        sensitivity: MemorySensitivity = (
            MemorySensitivity.PRIVATE
        ),
        retention: MemoryRetention = (
            MemoryRetention.PERSISTENT
        ),
        subject_entity_id: (
            str | None
        ) = None,
        observed_at: (
            datetime | None
        ) = None,
        valid_from: (
            datetime | None
        ) = None,
        valid_until: (
            datetime | None
        ) = None,
        metadata: (
            dict[str, Any] | None
        ) = None,
    ) -> "MemoryRecord":
        now = utc_now()

        return cls(
            id=str(uuid4()),
            kind=kind,
            content=content,
            title=title,
            source_type=source_type,
            source_ref=source_ref,
            confidence=confidence,
            importance=importance,
            sensitivity=sensitivity,
            retention=retention,
            subject_entity_id=(
                subject_entity_id
            ),
            created_at=now,
            updated_at=now,
            observed_at=observed_at,
            valid_from=valid_from,
            valid_until=valid_until,
            metadata=dict(
                metadata or {}
            ),
        )

    @property
    def fingerprint(self) -> str:
        return memory_fingerprint(
            self.kind,
            self.content,
            self.subject_entity_id,
        )

    def with_status(
        self,
        status: MemoryStatus,
        *,
        superseded_by_id: (
            str | None
        ) = None,
    ) -> "MemoryRecord":
        if (
            status
            == MemoryStatus.SUPERSEDED
            and not superseded_by_id
        ):
            raise ValueError(
                "superseded memories require "
                "superseded_by_id"
            )

        return replace(
            self,
            status=status,
            superseded_by_id=(
                superseded_by_id
            ),
            updated_at=utc_now(),
        )

    def as_dict(
        self,
    ) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind.value,
            "content": self.content,
            "title": self.title,
            "status": self.status.value,
            "source_type": (
                self.source_type.value
            ),
            "source_ref": self.source_ref,
            "confidence": self.confidence,
            "importance": self.importance,
            "sensitivity": (
                self.sensitivity.value
            ),
            "retention": (
                self.retention.value
            ),
            "subject_entity_id": (
                self.subject_entity_id
            ),
            "superseded_by_id": (
                self.superseded_by_id
            ),
            "created_at": (
                self.created_at.isoformat()
            ),
            "updated_at": (
                self.updated_at.isoformat()
            ),
            "observed_at": (
                self.observed_at.isoformat()
                if self.observed_at
                else None
            ),
            "valid_from": (
                self.valid_from.isoformat()
                if self.valid_from
                else None
            ),
            "valid_until": (
                self.valid_until.isoformat()
                if self.valid_until
                else None
            ),
            "metadata": dict(
                self.metadata
            ),
            "fingerprint": (
                self.fingerprint
            ),
        }
