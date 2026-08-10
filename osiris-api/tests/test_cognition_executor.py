import unittest

from cognition_executor import execute_plan


class CognitionExecutorTests(
    unittest.IsolatedAsyncioTestCase
):
    async def test_unsupported_step_is_not_success(self) -> None:
        result = await execute_plan(
            ["gpu_status"],
            message="check gpu",
        )

        self.assertEqual(
            result["status"],
            "partial",
        )

        self.assertEqual(
            result["results"][0]["status"],
            "unsupported",
        )


if __name__ == "__main__":
    unittest.main()
