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

    def test_phase2c_safe_adapters_available(self) -> None:
        expected = {
            "intelligence.model_routing",
            "intelligence.intent",
            "system.monitoring",
        }

        self.assertEqual(self.core.adapters.count, 3)

        for capability_id in expected:
            capability = self.core.capabilities.get(capability_id)

            self.assertIsNotNone(capability)
            self.assertEqual(
                capability.state,
                CapabilityState.AVAILABLE,
            )
            self.assertEqual(
                capability.metadata.get("adapter_state"),
                "validated",
            )

    def test_reasoning_remains_safety_gated(self) -> None:
        capability = self.core.capabilities.get(
            "intelligence.reasoning"
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
        self.assertTrue(capability.requires_approval)
        self.assertIsNone(
            self.core.adapters.get("intelligence.reasoning")
        )

    def test_adapter_installation_survives_restart(self) -> None:
        self.core.stop()
        self.core.start()

        self.assertEqual(self.core.adapters.count, 3)

        for capability_id in (
            "intelligence.model_routing",
            "intelligence.intent",
            "system.monitoring",
        ):
            capability = self.core.capabilities.get(capability_id)

            self.assertIsNotNone(capability)
            self.assertEqual(
                capability.state,
                CapabilityState.AVAILABLE,
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
        self.assertEqual(
            result.result["model"],
            "qwen2.5-coder:7b",
        )

    async def test_reasoning_cannot_execute(self) -> None:
        result = await self.core.adapters.execute(
            "intelligence.reasoning",
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
