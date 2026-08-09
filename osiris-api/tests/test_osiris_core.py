import unittest

from osiris_core import (
    Capability,
    CapabilityRisk,
    CapabilityState,
    OsirisCore,
    TaskState,
)


class OsirisCoreTests(unittest.TestCase):

    def test_identity_is_stable(self):
        core = OsirisCore()

        self.assertEqual(
            core.identity.identifier,
            "osiris",
        )

        self.assertEqual(
            core.identity.name,
            "OSIRIS",
        )

    def test_core_lifecycle(self):
        core = OsirisCore()

        self.assertEqual(
            core.status()["state"],
            "created",
        )

        core.start()

        status = core.status()

        self.assertEqual(
            status["state"],
            "running",
        )

        self.assertEqual(
            status["capabilities"],
            1,
        )

        self.assertGreaterEqual(
            status["events"],
            3,
        )

        core.stop()

        self.assertEqual(
            core.status()["state"],
            "stopped",
        )

    def test_capability_registry(self):
        core = OsirisCore()

        capability = Capability(
            capability_id="test.read",
            name="Test Read",
            description="Test capability",
            state=CapabilityState.AVAILABLE,
            risk=CapabilityRisk.READ_ONLY,
        )

        core.capabilities.register(capability)

        self.assertIsNotNone(
            core.capabilities.get("test.read")
        )

    def test_duplicate_capability_rejected(self):
        core = OsirisCore()

        capability = Capability(
            capability_id="test.duplicate",
            name="Duplicate",
            description="Duplicate test",
        )

        core.capabilities.register(capability)

        with self.assertRaises(ValueError):
            core.capabilities.register(capability)

    def test_task_lifecycle(self):
        core = OsirisCore()

        task = core.tasks.create(
            "test.task"
        )

        self.assertEqual(
            task.state,
            TaskState.CREATED,
        )

        core.tasks.transition(
            task.task_id,
            TaskState.PLANNING,
        )

        core.tasks.transition(
            task.task_id,
            TaskState.RUNNING,
        )

        core.tasks.transition(
            task.task_id,
            TaskState.VERIFYING,
        )

        core.tasks.transition(
            task.task_id,
            TaskState.SUCCEEDED,
        )

        self.assertEqual(
            core.tasks.get(task.task_id).state,
            TaskState.SUCCEEDED,
        )

        with self.assertRaises(ValueError):
            core.tasks.transition(
                task.task_id,
                TaskState.RUNNING,
            )


if __name__ == "__main__":
    unittest.main()
