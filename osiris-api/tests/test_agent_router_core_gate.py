import unittest

from osiris_core.runtime import core
from routers.agent_router import handle_agent_command


class AgentRouterCoreGateTests(
    unittest.IsolatedAsyncioTestCase
):
    def setUp(self) -> None:
        core.stop()
        core.start()

    def tearDown(self) -> None:
        core.stop()

    async def test_cognition_only_builds_plan(self) -> None:
        result = await handle_agent_command(
            "cognition",
            "check gpu temperature",
        )

        self.assertEqual(
            result["type"],
            "cognitive_plan",
        )

        self.assertIsNone(
            result["data"]["execution"]
        )

        self.assertEqual(
            result["data"]["steps"],
            ["gpu_status"],
        )

    async def test_agent_loop_requires_approval(self) -> None:
        result = await handle_agent_command(
            "agent_loop",
            "analyze my codebase",
        )

        self.assertEqual(
            result["type"],
            "approval_required",
        )

        capability_result = (
            result["data"]["capability_result"]
        )

        self.assertFalse(
            capability_result["success"]
        )

        self.assertEqual(
            capability_result["error"]["type"],
            "ApprovalRequired",
        )

        self.assertIsNotNone(
            result["data"]["approval_id"]
        )

        self.assertEqual(
            result["data"]["authorization"][
                "approval_status"
            ],
            "pending",
        )


if __name__ == "__main__":
    unittest.main()
