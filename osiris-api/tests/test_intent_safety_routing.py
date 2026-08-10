import unittest

from intent_classifier import classify_intent_with_ai


class IntentSafetyRoutingTests(
    unittest.IsolatedAsyncioTestCase
):
    async def test_think_through_routes_to_planning(self) -> None:
        command = await classify_intent_with_ai(
            "think through this architecture"
        )

        self.assertEqual(
            command,
            "cognition",
        )

    async def test_deep_analysis_routes_to_planning(self) -> None:
        command = await classify_intent_with_ai(
            "deep analyze my codebase"
        )

        self.assertEqual(
            command,
            "cognition",
        )

    async def test_run_agent_routes_to_gated_execution(self) -> None:
        command = await classify_intent_with_ai(
            "run agent on my codebase"
        )

        self.assertEqual(
            command,
            "agent_loop",
        )

    async def test_autonomous_language_routes_to_gated_execution(
        self,
    ) -> None:
        command = await classify_intent_with_ai(
            "autonomously inspect project"
        )

        self.assertEqual(
            command,
            "agent_loop",
        )


if __name__ == "__main__":
    unittest.main()
