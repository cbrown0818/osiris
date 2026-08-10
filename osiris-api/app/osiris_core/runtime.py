from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from threading import RLock
from time import monotonic
from typing import Any

from .adapters import (
    AdapterRegistry,
    install_phase2c_adapters,
)
from .bootstrap import (
    BootstrapReport,
    bootstrap_existing_capabilities,
)
from .capabilities import (
    Capability,
    CapabilityRegistry,
    CapabilityRisk,
    CapabilityState,
)
from .events import EventBus, EventType
from .identity import OsirisIdentity
from .tasks import TaskManager


class CoreState(str, Enum):
    CREATED = "created"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


class OsirisCore:
    """
    Root runtime object for the unified OSIRIS intelligence.

    Existing OSIRIS subsystems will progressively attach to this
    runtime rather than being rewritten wholesale.
    """

    def __init__(self) -> None:
        self.identity = OsirisIdentity()

        self.events = EventBus()
        self.capabilities = CapabilityRegistry(self.events)
        self.adapters = AdapterRegistry(
            self.capabilities,
            self.events,
        )
        self.tasks = TaskManager(self.events)

        self._state = CoreState.CREATED
        self._started_monotonic: float | None = None
        self._started_at: str | None = None
        self._bootstrap_report: BootstrapReport | None = None
        self._adapter_report: dict[str, Any] | None = None
        self._lock = RLock()

    @property
    def state(self) -> CoreState:
        with self._lock:
            return self._state

    def start(self) -> None:
        with self._lock:
            if self._state == CoreState.RUNNING:
                return

            self._state = CoreState.STARTING

        self.events.publish(EventType.CORE_STARTING)

        if self.capabilities.get("core.status") is None:
            self.capabilities.register(
                Capability(
                    capability_id="core.status",
                    name="Core Status",
                    description=(
                        "Read the state and identity of "
                        "the OSIRIS Core runtime."
                    ),
                    state=CapabilityState.AVAILABLE,
                    risk=CapabilityRisk.READ_ONLY,
                    requires_approval=False,
                )
            )

        self._bootstrap_report = (
            bootstrap_existing_capabilities(
                self.capabilities
            )
        )

        self._adapter_report = install_phase2c_adapters(
            self.adapters
        )

        now = datetime.now(timezone.utc).isoformat()

        with self._lock:
            self._started_monotonic = monotonic()
            self._started_at = now
            self._state = CoreState.RUNNING

        self.events.publish(EventType.CORE_STARTED)

    def stop(self) -> None:
        with self._lock:
            if self._state in {
                CoreState.CREATED,
                CoreState.STOPPED,
            }:
                self._state = CoreState.STOPPED
                return

            self._state = CoreState.STOPPING

        self.events.publish(EventType.CORE_STOPPING)

        with self._lock:
            self._state = CoreState.STOPPED

        self.events.publish(EventType.CORE_STOPPED)

    def status(self) -> dict[str, Any]:
        with self._lock:
            state = self._state
            started_at = self._started_at
            started_monotonic = self._started_monotonic

        uptime_seconds: float | None = None

        if (
            state == CoreState.RUNNING
            and started_monotonic is not None
        ):
            uptime_seconds = round(
                monotonic() - started_monotonic,
                3,
            )

        bootstrap = (
            self._bootstrap_report.as_dict()
            if self._bootstrap_report is not None
            else None
        )

        return {
            "identity": self.identity.as_dict(),
            "state": state.value,
            "started_at": started_at,
            "uptime_seconds": uptime_seconds,
            "capabilities": self.capabilities.count,
            "adapters": self.adapters.count,
            "tasks": self.tasks.count,
            "events": self.events.count,
            "capability_bootstrap": bootstrap,
            "adapter_install": self._adapter_report,
        }


core = OsirisCore()
