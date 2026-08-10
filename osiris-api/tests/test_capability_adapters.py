import unittest

from osiris_core.capabilities import (
    CapabilityRisk,
    CapabilityState,
)
from osiris_core.runtime import OsirisCore


class CapabilityAdapterTests(
    unittest.IsolatedAsyncioTestCase
):
    def setUp(self) -> None:
        self.core = OsirisCore()
        self.core.start()

    def tearDown(self) -> None:
        self.core.stop()

    def test_adapter_inventory(self) -> None:
        expected = {
            "intelligence.model_routing",
            "intelligence.intent",
            "intelligence.reasoning",
            "intelligence.agent_execution",
            "system.monitoring",
        }

        self.assertEqual(
            self.core.adapters.count,
            5,
        )

        for capability_id in expected:
            capability = (
                self.core.capabilities.get(
                    capability_id
                )
            )

            self.assertIsNotNone(
                capability
            )

            self.assertEqual(
                capability.state,
                CapabilityState.AVAILABLE,
            )

            self.assertIsNotNone(
                self.core.adapters.get(
                    capability_id
                )
            )

    def test_reasoning_is_read_only(self) -> None:
        capability = (
            self.core.capabilities.get(
                "intelligence.reasoning"
            )
        )

        self.assertEqual(
            capability.risk,
            CapabilityRisk.READ_ONLY,
        )

        self.assertFalse(
            capability.requires_approval
        )

    def test_agent_execution_is_available_but_gated(
        self,
    ) -> None:
        capability = (
            self.core.capabilities.get(
                "intelligence.agent_execution"
            )
        )

        self.assertIsNotNone(
            capability
        )

        self.assertEqual(
            capability.state,
            CapabilityState.AVAILABLE,
        )

        self.assertEqual(
            capability.risk,
            CapabilityRisk.HIGH,
        )

        self.assertTrue(
            capability.requires_approval
        )

        self.assertIsNotNone(
            self.core.adapters.get(
                "intelligence.agent_execution"
            )
        )

    def test_adapter_installation_survives_restart(
        self,
    ) -> None:
        self.core.stop()
        self.core.start()

        self.assertEqual(
            self.core.adapters.count,
            5,
        )

    async def test_model_routing_adapter(self) -> None:
        result = await self.core.adapters.execute(
            "intelligence.model_routing",
            {
                "message": (
                    "Debug this Python function"
                ),
            },
        )

        self.assertTrue(
            result.success
        )

        self.assertEqual(
            result.result["category"],
            "coding",
        )

    async def test_reasoning_builds_plan_without_execution(
        self,
    ) -> None:
        result = await self.core.adapters.execute(
            "intelligence.reasoning",
            {
                "goal": (
                    "check gpu temperature"
                ),
            },
        )

        self.assertTrue(
            result.success
        )

        self.assertEqual(
            result.result["mode"],
            "planning_only",
        )

        self.assertFalse(
            result.result["executed"]
        )

    async def test_agent_execution_creates_approval(
        self,
    ) -> None:
        result = await self.core.adapters.execute(
            "intelligence.agent_execution",
            {
                "goal": "Modify the system",
            },
        )

        self.assertFalse(
            result.success
        )

        self.assertEqual(
            result.error["type"],
            "ApprovalRequired",
        )

        self.assertIsNotNone(
            result.authorization
        )

        self.assertEqual(
            result.authorization[
                "approval_status"
            ],
            "pending",
        )

        self.assertIsNotNone(
            result.authorization[
                "approval_id"
            ]
        )


if __name__ == "__main__":
    unittest.main()
