import unittest

from command_detector import detect_command


class CommandDetectorSafetyRoutingTests(
    unittest.TestCase
):
    def test_run_agent_overrides_analysis_language(
        self,
    ) -> None:
        command = detect_command(
            "run agent analyze project structure"
        )

        self.assertEqual(
            command,
            "agent_loop",
        )

    def test_run_agent_loop_routes_to_execution(
        self,
    ) -> None:
        command = detect_command(
            "run agent loop analyze project"
        )

        self.assertEqual(
            command,
            "agent_loop",
        )

    def test_plain_analysis_remains_planning_only(
        self,
    ) -> None:
        command = detect_command(
            "analyze project structure"
        )

        self.assertEqual(
            command,
            "cognition",
        )


if __name__ == "__main__":
    unittest.main()
