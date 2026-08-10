import unittest

from osiris_core.adapters import (
    AdapterRegistry,
    FunctionAdapter,
)
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


def _test_runner(
    payload: dict,
) -> dict:
    return {
        "received": dict(payload),
    }


class CompletionFailStore(
    MemoryApprovalStore
):
    def mark(
        self,
        approval_id: str,
        status: str,
        result: dict | None = None,
    ) -> dict:
        if status == "executed":
            raise RuntimeError(
                "Simulated ledger completion failure"
            )

        return super().mark(
            approval_id,
            status,
            result=result,
        )


class AdapterAuthorizationTests(
    unittest.IsolatedAsyncioTestCase
):
    def setUp(self) -> None:
        self.events = EventBus()

        self.capabilities = CapabilityRegistry(
            self.events
        )

        self.store = MemoryApprovalStore()

        self.authorization = AuthorizationGateway(
            self.capabilities,
            approval_store=self.store,
        )

        self.adapters = AdapterRegistry(
            self.capabilities,
            self.events,
            authorization=self.authorization,
        )

        self.capabilities.register(
            Capability(
                capability_id="test.high",
                name="High Risk Test",
                description=(
                    "Authorization integration test."
                ),
                state=CapabilityState.REGISTERED,
                risk=CapabilityRisk.HIGH,
                requires_approval=True,
            )
        )

        installed = self.adapters.register(
            FunctionAdapter(
                capability_id="test.high",
                name="High Risk Test Adapter",
                module_name="reasoning_planner",
                function_name="build_reasoning_plan",
                runner=_test_runner,
            )
        )

        self.assertTrue(
            installed
        )

    async def test_high_risk_adapter_creates_pending_approval(
        self,
    ) -> None:
        result = await self.adapters.execute(
            "test.high",
            {
                "value": 1,
            },
        )

        self.assertFalse(
            result.success
        )

        self.assertEqual(
            result.error["type"],
            "ApprovalRequired",
        )

        self.assertEqual(
            result.authorization[
                "approval_status"
            ],
            "pending",
        )

    async def test_approved_request_executes_once(
        self,
    ) -> None:
        first = await self.adapters.execute(
            "test.high",
            {
                "value": 1,
            },
        )

        approval_id = first.authorization[
            "approval_id"
        ]

        self.store.mark(
            approval_id,
            "approved",
        )

        executed = await self.adapters.execute(
            "test.high",
            {
                "value": 1,
            },
            approval_id=approval_id,
        )

        self.assertTrue(
            executed.success
        )

        self.assertEqual(
            executed.result,
            {
                "received": {
                    "value": 1,
                }
            },
        )

        self.assertEqual(
            executed.authorization[
                "approval_status"
            ],
            "executed",
        )

        replay = await self.adapters.execute(
            "test.high",
            {
                "value": 1,
            },
            approval_id=approval_id,
        )

        self.assertFalse(
            replay.success
        )

        self.assertEqual(
            replay.error["type"],
            "AuthorizationDenied",
        )

    async def test_changed_payload_cannot_use_approval(
        self,
    ) -> None:
        first = await self.adapters.execute(
            "test.high",
            {
                "value": 1,
            },
        )

        approval_id = first.authorization[
            "approval_id"
        ]

        self.store.mark(
            approval_id,
            "approved",
        )

        changed = await self.adapters.execute(
            "test.high",
            {
                "value": 2,
            },
            approval_id=approval_id,
        )

        self.assertFalse(
            changed.success
        )

        self.assertEqual(
            changed.error["type"],
            "AuthorizationDenied",
        )

        record = self.store.get(
            approval_id
        )

        self.assertEqual(
            record["status"],
            "approved",
        )


    async def test_completed_action_is_not_false_reported(
        self,
    ) -> None:
        events = EventBus()
        capabilities = CapabilityRegistry(
            events
        )
        store = CompletionFailStore()

        authorization = AuthorizationGateway(
            capabilities,
            approval_store=store,
        )

        adapters = AdapterRegistry(
            capabilities,
            events,
            authorization=authorization,
        )

        capabilities.register(
            Capability(
                capability_id="test.ledger_failure",
                name="Ledger Failure Test",
                description=(
                    "Tests completion failure handling."
                ),
                state=CapabilityState.REGISTERED,
                risk=CapabilityRisk.HIGH,
                requires_approval=True,
            )
        )

        installed = adapters.register(
            FunctionAdapter(
                capability_id="test.ledger_failure",
                name="Ledger Failure Adapter",
                module_name="reasoning_planner",
                function_name="build_reasoning_plan",
                runner=_test_runner,
            )
        )

        self.assertTrue(installed)

        first = await adapters.execute(
            "test.ledger_failure",
            {
                "value": 1,
            },
        )

        approval_id = first.authorization[
            "approval_id"
        ]

        store.mark(
            approval_id,
            "approved",
        )

        result = await adapters.execute(
            "test.ledger_failure",
            {
                "value": 1,
            },
            approval_id=approval_id,
        )

        self.assertFalse(
            result.success
        )

        self.assertEqual(
            result.error["type"],
            "AuthorizationCompletionError",
        )

        self.assertEqual(
            result.result,
            {
                "received": {
                    "value": 1,
                }
            },
        )

        approval = store.get(
            approval_id
        )

        self.assertEqual(
            approval["status"],
            "executing",
        )


if __name__ == "__main__":
    unittest.main()
