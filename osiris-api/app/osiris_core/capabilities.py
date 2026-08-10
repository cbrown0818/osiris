from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from threading import RLock
from typing import Any

from .events import EventBus, EventType


class CapabilityState(str, Enum):
    REGISTERED = "registered"
    AVAILABLE = "available"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    DISABLED = "disabled"


class CapabilityRisk(str, Enum):
    READ_ONLY = "read_only"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(slots=True)
class Capability:
    capability_id: str
    name: str
    description: str
    state: CapabilityState = CapabilityState.REGISTERED
    risk: CapabilityRisk = CapabilityRisk.READ_ONLY
    requires_approval: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["state"] = self.state.value
        result["risk"] = self.risk.value
        return result


class CapabilityRegistry:
    """
    Canonical registry for anything OSIRIS can do.

    Software tools, engineering actions, home automation,
    sensors, cameras, robots, and future physical bodies all
    enter OSIRIS through this same abstraction.
    """

    def __init__(self, events: EventBus) -> None:
        self._events = events
        self._items: dict[str, Capability] = {}
        self._lock = RLock()

    def register(
        self,
        capability: Capability,
        *,
        replace: bool = False,
    ) -> Capability:
        key = capability.capability_id.strip()

        if not key:
            raise ValueError("capability_id cannot be empty")

        with self._lock:
            if key in self._items and not replace:
                raise ValueError(
                    f"Capability already registered: {key}"
                )

            self._items[key] = capability

        self._events.publish(
            EventType.CAPABILITY_REGISTERED,
            payload={
                "capability_id": key,
                "state": capability.state.value,
                "risk": capability.risk.value,
            },
        )

        return capability

    def set_state(
        self,
        capability_id: str,
        state: CapabilityState,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> Capability:
        with self._lock:
            capability = self._items.get(capability_id)

            if capability is None:
                raise KeyError(
                    f"Capability not registered: {capability_id}"
                )

            previous_state = capability.state
            capability.state = state

            if metadata:
                capability.metadata.update(metadata)

        if previous_state != state:
            self._events.publish(
                EventType.CAPABILITY_STATE_CHANGED,
                source=capability_id,
                payload={
                    "capability_id": capability_id,
                    "previous_state": previous_state.value,
                    "state": state.value,
                },
            )

        return capability

    def get(self, capability_id: str) -> Capability | None:
        with self._lock:
            return self._items.get(capability_id)

    def all(self) -> list[Capability]:
        with self._lock:
            return list(self._items.values())

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._items)
