from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from threading import RLock
from typing import Any
from uuid import uuid4


class EventType(str, Enum):
    CORE_STARTING = "core.starting"
    CORE_STARTED = "core.started"
    CORE_STOPPING = "core.stopping"
    CORE_STOPPED = "core.stopped"

    CAPABILITY_REGISTERED = "capability.registered"
    CAPABILITY_STATE_CHANGED = "capability.state_changed"
    CAPABILITY_EXECUTED = "capability.executed"
    CAPABILITY_FAILED = "capability.failed"

    TASK_CREATED = "task.created"
    TASK_STATE_CHANGED = "task.state_changed"

    SYSTEM_NOTICE = "system.notice"
    SYSTEM_ERROR = "system.error"


@dataclass(frozen=True, slots=True)
class CoreEvent:
    event_id: str
    event_type: EventType
    timestamp: str
    source: str
    payload: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["event_type"] = self.event_type.value
        return result


class EventBus:
    """
    Small in-process event bus.

    Phase 2 begins in memory intentionally. Persistence and
    distributed delivery will be added behind this interface
    later without changing users of the event bus.
    """

    def __init__(self, max_events: int = 500) -> None:
        if max_events < 1:
            raise ValueError("max_events must be at least 1")

        self._events: deque[CoreEvent] = deque(maxlen=max_events)
        self._lock = RLock()

    def publish(
        self,
        event_type: EventType,
        *,
        source: str = "osiris-core",
        payload: dict[str, Any] | None = None,
    ) -> CoreEvent:
        event = CoreEvent(
            event_id=str(uuid4()),
            event_type=event_type,
            timestamp=datetime.now(timezone.utc).isoformat(),
            source=source,
            payload=dict(payload or {}),
        )

        with self._lock:
            self._events.append(event)

        return event

    def recent(self, limit: int = 50) -> list[CoreEvent]:
        if limit < 1:
            return []

        with self._lock:
            events = list(self._events)

        return events[-limit:]

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._events)
