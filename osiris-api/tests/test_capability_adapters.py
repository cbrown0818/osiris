import unittest

from osiris_core.capabilities import (
    CapabilityRisk,
    CapabilityState,
)
from osiris_core.runtime import OsirisCore


class CapabilityAdapterTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.core = OsirisCore()
        self.core.start()

    def tearDown(self) -> None:
        self.core.stop()

    def test_safe_adapters_available(self) -> None:
        expected = {
            "intelligence.model_routing",
            "intelligence.intent",
            "intelligence.reasoning",
            "system.monitoring",
        }

        self.assertEqual(
            self.core.adapters.count,
            4,
        )

        for capability_id in expected:
            capability = self.core.capabilities.get(
                capability_id
            )

            self.assertIsNotNone(capability)
            self.assertEqual(
                capability.state,
                CapabilityState.AVAILABLE,
            )
            self.assertEqual(
                capability.metadata.get("adapter_state"),
                "validated",
            )

    def test_reasoning_is_read_only(self) -> None:
        capability = self.core.capabilities.get(
            "intelligence.reasoning"
        )

        self.assertIsNotNone(capability)
        self.assertEqual(
            capability.state,
            CapabilityState.AVAILABLE,
        )
        self.assertEqual(
            capability.risk,
            CapabilityRisk.READ_ONLY,
        )
        self.assertFalse(
            capability.requires_approval
        )

    def test_agent_execution_is_safety_gated(self) -> None:
        capability = self.core.capabilities.get(
            "intelligence.agent_execution"
        )

        self.assertIsNotNone(capability)
        self.assertEqual(
            capability.state,
            CapabilityState.REGISTERED,
        )
        self.assertEqual(
            capability.risk,
            CapabilityRisk.HIGH,
        )
        self.assertTrue(
            capability.requires_approval
        )
        self.assertIsNone(
            self.core.adapters.get(
                "intelligence.agent_execution"
            )
        )

    def test_adapter_installation_survives_restart(self) -> None:
        self.core.stop()
        self.core.start()

        self.assertEqual(
            self.core.adapters.count,
            4,
        )

    async def test_model_routing_adapter(self) -> None:
        result = await self.core.adapters.execute(
            "intelligence.model_routing",
            {
                "message": "Debug this Python function",
            },
        )

        self.assertTrue(result.success)
        self.assertEqual(
            result.result["category"],
            "coding",
        )

    async def test_reasoning_builds_plan_without_execution(self) -> None:
        result = await self.core.adapters.execute(
            "intelligence.reasoning",
            {
                "goal": "check gpu temperature",
            },
        )

        self.assertTrue(result.success)

        self.assertEqual(
            result.result["mode"],
            "planning_only",
        )

        self.assertEqual(
            result.result["plan"],
            ["gpu_status"],
        )

        self.assertFalse(
            result.result["executed"]
        )

        self.assertTrue(
            result.result[
                "requires_execution_authorization"
            ]
        )

    async def test_agent_execution_cannot_run_directly(self) -> None:
        result = await self.core.adapters.execute(
            "intelligence.agent_execution",
            {
                "goal": "Modify the system",
            },
        )

        self.assertFalse(result.success)

        self.assertEqual(
            result.error["type"],
            "ApprovalRequired",
        )


if __name__ == "__main__":
    unittest.main()
