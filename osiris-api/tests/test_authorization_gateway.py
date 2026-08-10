import unittest

from osiris_core.authorization import (
    AuthorizationGateway,
    MemoryApprovalStore,
)
from osiris_core.capabilities import (
    Capability,
    CapabilityRegistry,
    CapabilityRisk,
    CapabilityState,
)
from osiris_core.events import EventBus


class AuthorizationGatewayTests(
    unittest.TestCase
):
    def setUp(self) -> None:
        events = EventBus()

        self.registry = CapabilityRegistry(
            events
        )

        self.store = MemoryApprovalStore()

        self.gateway = AuthorizationGateway(
            self.registry,
            approval_store=self.store,
        )

        self.registry.register(
            Capability(
                capability_id="test.read",
                name="Read Test",
                description="Read-only test.",
                state=CapabilityState.AVAILABLE,
                risk=CapabilityRisk.READ_ONLY,
                requires_approval=False,
            )
        )

        self.registry.register(
            Capability(
                capability_id="test.high",
                name="High Test",
                description="Approval test.",
                state=CapabilityState.AVAILABLE,
                risk=CapabilityRisk.HIGH,
                requires_approval=True,
            )
        )

    def test_read_only_capability_is_allowed(self) -> None:
        decision = self.gateway.authorize(
            "test.read",
            {
                "value": 1,
            },
        )

        self.assertTrue(
            decision.allowed
        )

        self.assertFalse(
            decision.requires_approval
        )

        self.assertIsNone(
            decision.approval_id
        )

    def test_high_risk_creates_pending_approval(self) -> None:
        decision = self.gateway.authorize(
            "test.high",
            {
                "value": 1,
            },
        )

        self.assertFalse(
            decision.allowed
        )

        self.assertTrue(
            decision.requires_approval
        )

        self.assertIsNotNone(
            decision.approval_id
        )

        self.assertEqual(
            decision.approval_status,
            "pending",
        )

    def test_approval_is_bound_to_exact_payload(self) -> None:
        first = self.gateway.authorize(
            "test.high",
            {
                "value": 1,
            },
        )

        self.store.mark(
            first.approval_id,
            "approved",
        )

        changed = self.gateway.authorize(
            "test.high",
            {
                "value": 2,
            },
            approval_id=first.approval_id,
        )

        self.assertFalse(
            changed.allowed
        )

        self.assertIn(
            "fingerprint",
            changed.reason.lower(),
        )

    def test_approved_request_can_be_claimed_once(self) -> None:
        first = self.gateway.authorize(
            "test.high",
            {
                "value": 1,
            },
        )

        self.store.mark(
            first.approval_id,
            "approved",
        )

        claimed = self.gateway.authorize(
            "test.high",
            {
                "value": 1,
            },
            approval_id=first.approval_id,
        )

        self.assertTrue(
            claimed.allowed
        )

        self.assertEqual(
            claimed.approval_status,
            "executing",
        )

        replay = self.gateway.authorize(
            "test.high",
            {
                "value": 1,
            },
            approval_id=first.approval_id,
        )

        self.assertFalse(
            replay.allowed
        )

    def test_completed_approval_becomes_executed(self) -> None:
        first = self.gateway.authorize(
            "test.high",
            {
                "value": 1,
            },
        )

        self.store.mark(
            first.approval_id,
            "approved",
        )

        claimed = self.gateway.authorize(
            "test.high",
            {
                "value": 1,
            },
            approval_id=first.approval_id,
        )

        self.gateway.complete(
            claimed,
            success=True,
            result={
                "ok": True,
            },
        )

        record = self.store.get(
            first.approval_id
        )

        self.assertEqual(
            record["status"],
            "executed",
        )


if __name__ == "__main__":
    unittest.main()
