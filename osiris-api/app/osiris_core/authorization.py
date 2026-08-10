from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Protocol

from .capabilities import (
    CapabilityRegistry,
    CapabilityState,
)


CORE_EXECUTION_ACTION = "core.capability.execute"


def request_fingerprint(
    capability_id: str,
    payload: dict[str, Any],
) -> str:
    canonical = json.dumps(
        {
            "capability_id": capability_id,
            "payload": payload,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )

    return hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class AuthorizationDecision:
    capability_id: str
    allowed: bool
    requires_approval: bool
    reason: str
    request_hash: str
    approval_id: str | None = None
    approval_status: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class ApprovalStore(Protocol):
    def create(
        self,
        *,
        capability_id: str,
        payload: dict[str, Any],
        request_hash: str,
        risk: str,
    ) -> dict[str, Any]:
        ...

    def get(
        self,
        approval_id: str,
    ) -> dict[str, Any] | None:
        ...

    def claim(
        self,
        *,
        approval_id: str,
        capability_id: str,
        request_hash: str,
    ) -> dict[str, Any]:
        ...

    def mark(
        self,
        approval_id: str,
        status: str,
        result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ...


class MemoryApprovalStore:
    """
    In-memory approval store for isolated Core testing.

    Production uses PostgreSQL whenever DATABASE_URL is configured.
    """

    def __init__(self) -> None:
        self._items: dict[str, dict[str, Any]] = {}
        self._lock = RLock()

    def create(
        self,
        *,
        capability_id: str,
        payload: dict[str, Any],
        request_hash: str,
        risk: str,
    ) -> dict[str, Any]:
        approval_id = str(uuid.uuid4())

        approval = {
            "id": approval_id,
            "status": "pending",
            "tool_name": capability_id,
            "target": capability_id,
            "action": CORE_EXECUTION_ACTION,
            "params": {
                "payload": dict(payload),
            },
            "permission": {
                "capability_id": capability_id,
                "risk": risk,
                "request_hash": request_hash,
            },
            "result": None,
            "created_at": datetime.now(
                timezone.utc
            ).isoformat(),
            "decided_at": None,
        }

        with self._lock:
            self._items[approval_id] = approval

        return dict(approval)

    def get(
        self,
        approval_id: str,
    ) -> dict[str, Any] | None:
        with self._lock:
            approval = self._items.get(approval_id)

            if approval is None:
                return None

            return dict(approval)

    def claim(
        self,
        *,
        approval_id: str,
        capability_id: str,
        request_hash: str,
    ) -> dict[str, Any]:
        with self._lock:
            approval = self._items.get(approval_id)

            if approval is None:
                raise ValueError(
                    f"Unknown approval id: {approval_id}"
                )

            if approval["status"] != "approved":
                raise ValueError(
                    "Approval is not in approved state. "
                    f"Current status: {approval['status']}"
                )

            if approval["tool_name"] != capability_id:
                raise ValueError(
                    "Approval tool does not match request."
                )

            if approval["target"] != capability_id:
                raise ValueError(
                    "Approval target does not match request."
                )

            if approval["action"] != CORE_EXECUTION_ACTION:
                raise ValueError(
                    "Approval action does not match request."
                )

            permission = approval.get("permission") or {}

            if permission.get("request_hash") != request_hash:
                raise ValueError(
                    "Approval request fingerprint does not match."
                )

            approval["status"] = "executing"

            return dict(approval)

    def mark(
        self,
        approval_id: str,
        status: str,
        result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            approval = self._items.get(approval_id)

            if approval is None:
                raise ValueError(
                    f"Unknown approval id: {approval_id}"
                )

            approval["status"] = status
            approval["result"] = dict(result or {})

            if status in {
                "approved",
                "denied",
            }:
                approval["decided_at"] = datetime.now(
                    timezone.utc
                ).isoformat()

            return dict(approval)


class PostgresApprovalStore:
    """
    Adapter over the existing OSIRIS approvals.py subsystem.
    """

    def create(
        self,
        *,
        capability_id: str,
        payload: dict[str, Any],
        request_hash: str,
        risk: str,
    ) -> dict[str, Any]:
        from approvals import create_approval

        return create_approval(
            tool_name=capability_id,
            target=capability_id,
            action=CORE_EXECUTION_ACTION,
            params={
                "payload": dict(payload),
            },
            permission={
                "capability_id": capability_id,
                "risk": risk,
                "request_hash": request_hash,
                "authorization_layer": "osiris_core",
            },
        )

    def get(
        self,
        approval_id: str,
    ) -> dict[str, Any] | None:
        from approvals import get_approval

        return get_approval(approval_id)

    def claim(
        self,
        *,
        approval_id: str,
        capability_id: str,
        request_hash: str,
    ) -> dict[str, Any]:
        from approvals import (
            claim_approval_for_execution,
        )

        return claim_approval_for_execution(
            approval_id,
            tool_name=capability_id,
            target=capability_id,
            action=CORE_EXECUTION_ACTION,
            request_hash=request_hash,
        )

    def mark(
        self,
        approval_id: str,
        status: str,
        result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        from approvals import mark_approval_decision

        return mark_approval_decision(
            approval_id=approval_id,
            status=status,
            result=result,
        )


def default_approval_store() -> ApprovalStore:
    if os.getenv("DATABASE_URL"):
        return PostgresApprovalStore()

    return MemoryApprovalStore()


class AuthorizationGateway:
    """
    Core-native capability authorization boundary.

    Core capability authorization is intentionally separate from
    legacy tool permissions. Adapter-specific tool permissions can
    be evaluated underneath this boundary as those subsystems migrate.
    """

    def __init__(
        self,
        capabilities: CapabilityRegistry,
        approval_store: ApprovalStore | None = None,
    ) -> None:
        self._capabilities = capabilities
        self._approval_store = (
            approval_store
            if approval_store is not None
            else default_approval_store()
        )

    @property
    def approval_store(self) -> ApprovalStore:
        return self._approval_store

    def authorize(
        self,
        capability_id: str,
        payload: dict[str, Any] | None = None,
        *,
        approval_id: str | None = None,
    ) -> AuthorizationDecision:
        payload = dict(payload or {})

        capability = self._capabilities.get(
            capability_id
        )

        fingerprint = request_fingerprint(
            capability_id,
            payload,
        )

        if capability is None:
            return AuthorizationDecision(
                capability_id=capability_id,
                allowed=False,
                requires_approval=False,
                reason="Capability is not registered.",
                request_hash=fingerprint,
            )

        if capability.state != CapabilityState.AVAILABLE:
            return AuthorizationDecision(
                capability_id=capability_id,
                allowed=False,
                requires_approval=(
                    capability.requires_approval
                ),
                reason=(
                    "Capability is not available. "
                    f"Current state: {capability.state.value}"
                ),
                request_hash=fingerprint,
            )

        if not capability.requires_approval:
            return AuthorizationDecision(
                capability_id=capability_id,
                allowed=True,
                requires_approval=False,
                reason=(
                    "Capability does not require approval."
                ),
                request_hash=fingerprint,
            )

        if approval_id is None:
            approval = self._approval_store.create(
                capability_id=capability_id,
                payload=payload,
                request_hash=fingerprint,
                risk=capability.risk.value,
            )

            return AuthorizationDecision(
                capability_id=capability_id,
                allowed=False,
                requires_approval=True,
                reason=(
                    "Capability requires explicit approval."
                ),
                request_hash=fingerprint,
                approval_id=str(approval["id"]),
                approval_status=str(
                    approval["status"]
                ),
            )

        try:
            claimed = self._approval_store.claim(
                approval_id=approval_id,
                capability_id=capability_id,
                request_hash=fingerprint,
            )
        except Exception as exc:
            approval_status = None

            try:
                existing = self._approval_store.get(
                    approval_id
                )

                if existing:
                    approval_status = existing.get(
                        "status"
                    )
            except Exception:
                pass

            return AuthorizationDecision(
                capability_id=capability_id,
                allowed=False,
                requires_approval=True,
                reason=str(exc),
                request_hash=fingerprint,
                approval_id=approval_id,
                approval_status=approval_status,
            )

        return AuthorizationDecision(
            capability_id=capability_id,
            allowed=True,
            requires_approval=True,
            reason="Approved request claimed for execution.",
            request_hash=fingerprint,
            approval_id=approval_id,
            approval_status=str(
                claimed.get(
                    "status",
                    "executing",
                )
            ),
        )

    def complete(
        self,
        decision: AuthorizationDecision,
        *,
        success: bool,
        result: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        if not decision.approval_id:
            return None

        if decision.approval_status != "executing":
            return None

        return self._approval_store.mark(
            decision.approval_id,
            "executed" if success else "failed",
            result=result,
        )
