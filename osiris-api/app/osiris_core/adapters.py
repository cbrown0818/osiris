from __future__ import annotations

import ast
from dataclasses import asdict, dataclass
from importlib.util import find_spec
from inspect import isawaitable
from pathlib import Path
from threading import RLock
from time import monotonic
from typing import Any, Callable

from .capabilities import (
    CapabilityRegistry,
    CapabilityState,
)
from .events import EventBus, EventType


AdapterRunner = Callable[[dict[str, Any]], Any]


@dataclass(frozen=True, slots=True)
class CapabilityResult:
    capability_id: str
    success: bool
    result: Any = None
    error: dict[str, str] | None = None
    duration_ms: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class FunctionAdapter:
    capability_id: str
    name: str
    module_name: str
    function_name: str
    runner: AdapterRunner

    def validate(self) -> tuple[bool, str]:
        """
        Validate the legacy target without importing or executing it.

        This intentionally parses the target module's Python source instead
        of importing it during Core startup. That keeps adapter discovery
        free of network calls, device access, or other import side effects.
        """
        try:
            spec = find_spec(self.module_name)
        except (ImportError, AttributeError, ValueError) as exc:
            return False, f"module lookup failed: {type(exc).__name__}"

        if spec is None or not spec.origin:
            return False, "module not found"

        path = Path(spec.origin)

        if not path.is_file():
            return False, "module source not found"

        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, SyntaxError) as exc:
            return False, f"source validation failed: {type(exc).__name__}"

        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == self.function_name:
                    return True, "validated"

        return False, f"function not found: {self.function_name}"

    async def invoke(self, payload: dict[str, Any]) -> Any:
        value = self.runner(payload)

        if isawaitable(value):
            return await value

        return value


class AdapterRegistry:
    """
    Maps OSIRIS Core capabilities onto controlled legacy subsystem adapters.

    Registering a Python module is not enough to make a capability executable.
    A capability becomes AVAILABLE only after its adapter validates.
    """

    def __init__(
        self,
        capabilities: CapabilityRegistry,
        events: EventBus,
    ) -> None:
        self._capabilities = capabilities
        self._events = events
        self._items: dict[str, FunctionAdapter] = {}
        self._lock = RLock()

    def register(
        self,
        adapter: FunctionAdapter,
        *,
        replace: bool = False,
    ) -> bool:
        capability = self._capabilities.get(adapter.capability_id)

        if capability is None:
            raise KeyError(
                f"Capability not registered: {adapter.capability_id}"
            )

        if capability.state in {
            CapabilityState.UNAVAILABLE,
            CapabilityState.DISABLED,
        }:
            return False

        # Phase 2C must never auto-activate approval-gated capabilities.
        if capability.requires_approval:
            self._capabilities.set_state(
                adapter.capability_id,
                CapabilityState.REGISTERED,
                metadata={
                    "adapter_state": "approval_required",
                    "adapter_target": (
                        f"{adapter.module_name}.{adapter.function_name}"
                    ),
                },
            )
            return False

        valid, validation = adapter.validate()

        if not valid:
            self._capabilities.set_state(
                adapter.capability_id,
                CapabilityState.DEGRADED,
                metadata={
                    "adapter": adapter.name,
                    "adapter_state": "validation_failed",
                    "adapter_validation": validation,
                    "adapter_target": (
                        f"{adapter.module_name}.{adapter.function_name}"
                    ),
                },
            )
            return False

        with self._lock:
            if adapter.capability_id in self._items and not replace:
                raise ValueError(
                    f"Adapter already registered: {adapter.capability_id}"
                )

            self._items[adapter.capability_id] = adapter

        self._capabilities.set_state(
            adapter.capability_id,
            CapabilityState.AVAILABLE,
            metadata={
                "adapter": adapter.name,
                "adapter_state": "validated",
                "adapter_validation": validation,
                "adapter_target": (
                    f"{adapter.module_name}.{adapter.function_name}"
                ),
            },
        )

        return True

    def get(self, capability_id: str) -> FunctionAdapter | None:
        with self._lock:
            return self._items.get(capability_id)

    def all(self) -> list[FunctionAdapter]:
        with self._lock:
            return list(self._items.values())

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._items)

    async def execute(
        self,
        capability_id: str,
        payload: dict[str, Any] | None = None,
    ) -> CapabilityResult:
        started = monotonic()

        capability = self._capabilities.get(capability_id)

        if capability is None:
            return self._failure(
                capability_id,
                started,
                "CapabilityNotFound",
                "Capability is not registered.",
            )

        if capability.requires_approval:
            return self._failure(
                capability_id,
                started,
                "ApprovalRequired",
                "Capability requires approval and cannot execute directly.",
            )

        if capability.state != CapabilityState.AVAILABLE:
            return self._failure(
                capability_id,
                started,
                "CapabilityUnavailable",
                f"Capability state is {capability.state.value}.",
            )

        adapter = self.get(capability_id)

        if adapter is None:
            return self._failure(
                capability_id,
                started,
                "AdapterNotFound",
                "No validated adapter is registered.",
            )

        try:
            result = await adapter.invoke(dict(payload or {}))
        except Exception as exc:
            duration = round((monotonic() - started) * 1000, 3)

            self._events.publish(
                EventType.CAPABILITY_FAILED,
                source=capability_id,
                payload={
                    "error_type": type(exc).__name__,
                    "duration_ms": duration,
                },
            )

            return CapabilityResult(
                capability_id=capability_id,
                success=False,
                error={
                    "type": type(exc).__name__,
                    "message": str(exc),
                },
                duration_ms=duration,
            )

        duration = round((monotonic() - started) * 1000, 3)

        self._events.publish(
            EventType.CAPABILITY_EXECUTED,
            source=capability_id,
            payload={
                "duration_ms": duration,
            },
        )

        return CapabilityResult(
            capability_id=capability_id,
            success=True,
            result=result,
            error=None,
            duration_ms=duration,
        )

    def _failure(
        self,
        capability_id: str,
        started: float,
        error_type: str,
        message: str,
    ) -> CapabilityResult:
        duration = round((monotonic() - started) * 1000, 3)

        self._events.publish(
            EventType.CAPABILITY_FAILED,
            source=capability_id,
            payload={
                "error_type": error_type,
                "duration_ms": duration,
            },
        )

        return CapabilityResult(
            capability_id=capability_id,
            success=False,
            error={
                "type": error_type,
                "message": message,
            },
            duration_ms=duration,
        )


def _require_string(
    payload: dict[str, Any],
    key: str,
    *,
    allow_empty: bool = False,
) -> str:
    value = payload.get(key)

    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")

    if not allow_empty and not value.strip():
        raise ValueError(f"{key} cannot be empty")

    return value


def _run_model_routing(payload: dict[str, Any]) -> dict[str, Any]:
    from model_router import select_model

    message = _require_string(
        payload,
        "message",
        allow_empty=True,
    )

    requested_model = payload.get("requested_model")
    if requested_model is not None and not isinstance(
        requested_model,
        str,
    ):
        raise ValueError("requested_model must be a string or null")

    has_image = payload.get("has_image", False)
    if not isinstance(has_image, bool):
        raise ValueError("has_image must be a boolean")

    previous_category = payload.get("previous_category")

    allowed_categories = {
        None,
        "general",
        "reasoning",
        "coding",
        "vision",
    }

    if previous_category not in allowed_categories:
        raise ValueError("previous_category is invalid")

    decision = select_model(
        message,
        requested_model=requested_model,
        has_image=has_image,
        previous_category=previous_category,
    )

    return asdict(decision)


async def _run_intent(payload: dict[str, Any]) -> dict[str, Any]:
    from intent_classifier import classify_intent_with_ai

    message = _require_string(
        payload,
        "message",
        allow_empty=True,
    )

    fallback_command = payload.get("fallback_command", "chat")

    if not isinstance(fallback_command, str):
        raise ValueError("fallback_command must be a string")

    command = await classify_intent_with_ai(
        message,
        fallback_command=fallback_command,
    )

    return {
        "command": command,
    }


async def _run_system_monitoring(
    payload: dict[str, Any],
) -> dict[str, Any]:
    from system_monitor import get_full_system_snapshot

    return await get_full_system_snapshot()


def install_phase2c_adapters(
    registry: AdapterRegistry,
) -> dict[str, Any]:
    adapters = (
        FunctionAdapter(
            capability_id="intelligence.model_routing",
            name="Model Routing Adapter",
            module_name="model_router",
            function_name="select_model",
            runner=_run_model_routing,
        ),
        FunctionAdapter(
            capability_id="intelligence.intent",
            name="Intent Classification Adapter",
            module_name="intent_classifier",
            function_name="classify_intent_with_ai",
            runner=_run_intent,
        ),
        FunctionAdapter(
            capability_id="system.monitoring",
            name="System Monitoring Adapter",
            module_name="system_monitor",
            function_name="get_full_system_snapshot",
            runner=_run_system_monitoring,
        ),
    )

    installed: list[str] = []
    failed: list[str] = []

    for adapter in adapters:
        # Built-in adapters are revalidated and replaced on Core restart.
        # General duplicate registration remains protected by the registry.
        if registry.register(adapter, replace=True):
            installed.append(adapter.capability_id)
        else:
            failed.append(adapter.capability_id)

    return {
        "requested": len(adapters),
        "installed": installed,
        "failed": failed,
    }
