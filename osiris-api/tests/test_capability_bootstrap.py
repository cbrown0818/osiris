import unittest

from osiris_core import (
    EXISTING_CAPABILITY_SPECS,
    OsirisCore,
)


class CapabilityBootstrapTests(
    unittest.TestCase
):

    def test_all_existing_modules_discovered(self):
        core = OsirisCore()
        core.start()

        status = core.status()

        report = status[
            "capability_bootstrap"
        ]

        self.assertEqual(
            report["total_specs"],
            len(EXISTING_CAPABILITY_SPECS),
        )

        self.assertEqual(
            report["missing"],
            0,
        )

        self.assertEqual(
            report["present"],
            len(EXISTING_CAPABILITY_SPECS),
        )

    def test_expected_capability_count(self):
        core = OsirisCore()
        core.start()

        expected = (
            1
            + len(EXISTING_CAPABILITY_SPECS)
        )

        self.assertEqual(
            core.capabilities.count,
            expected,
        )

    def test_capability_ids_are_unique(self):
        ids = [
            item.capability_id
            for item in EXISTING_CAPABILITY_SPECS
        ]

        self.assertEqual(
            len(ids),
            len(set(ids)),
        )

    def test_bootstrap_is_idempotent(self):
        core = OsirisCore()

        core.start()

        first_count = (
            core.capabilities.count
        )

        core.stop()
        core.start()

        second_count = (
            core.capabilities.count
        )

        self.assertEqual(
            first_count,
            second_count,
        )

    def test_high_risk_capabilities_require_approval(self):
        core = OsirisCore()
        core.start()

        protected = {
            "intelligence.agent_execution",
            "tools.execution",
            "security.permissions",
            "security.approvals",
            "devices.control",
            "devices.mqtt_bridge",
            "host.agent",
            "development.core",
            "development.patching",
            "recovery.self_heal",
        }

        for capability_id in protected:
            capability = (
                core.capabilities.get(
                    capability_id
                )
            )

            self.assertIsNotNone(
                capability
            )

            self.assertTrue(
                capability.requires_approval,
                capability_id,
            )


if __name__ == "__main__":
    unittest.main()
