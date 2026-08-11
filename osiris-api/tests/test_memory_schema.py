from pathlib import Path
import unittest


ROOT = (
    Path(__file__)
    .resolve()
    .parents[1]
)

MIGRATION = (
    ROOT
    / "db"
    / "migrations"
    / "001_core_memory.sql"
)


class MemorySchemaTests(
    unittest.TestCase
):
    @classmethod
    def setUpClass(
        cls,
    ) -> None:
        cls.sql = (
            MIGRATION
            .read_text(
                encoding="utf-8"
            )
        )

        cls.upper = (
            cls.sql.upper()
        )

    def test_migration_is_additive(
        self,
    ) -> None:
        forbidden = (
            "DROP TABLE",
            "DROP INDEX",
            "TRUNCATE",
            "DELETE FROM",
            "ALTER TABLE",
        )

        for token in forbidden:
            with self.subTest(
                token=token
            ):
                self.assertNotIn(
                    token,
                    self.upper,
                )

    def test_canonical_table_is_created(
        self,
    ) -> None:
        self.assertIn(
            "CREATE TABLE IF NOT EXISTS "
            "osiris_memory_records",
            self.sql,
        )

    def test_migration_tracking_exists(
        self,
    ) -> None:
        self.assertIn(
            "osiris_schema_migrations",
            self.sql,
        )

        self.assertIn(
            "001_core_memory",
            self.sql,
        )

    def test_legacy_lilith_collections_are_untouched(
        self,
    ) -> None:
        self.assertNotIn(
            "lilith_memories",
            self.sql.lower(),
        )

        self.assertNotIn(
            "lilith_documents",
            self.sql.lower(),
        )


    def test_supersession_fk_restricts_physical_delete(
        self,
    ) -> None:
        self.assertIn(
            "ON DELETE RESTRICT",
            self.upper,
        )

        self.assertNotIn(
            "ON DELETE SET NULL",
            self.upper,
        )


if __name__ == "__main__":
    unittest.main()


class ActiveFingerprintConcurrencySchemaTests(
    unittest.TestCase
):
    def setUp(self):
        migration_path = (
            Path(__file__).resolve().parents[1]
            / "db"
            / "migrations"
            / "002_active_memory_fingerprint_unique.sql"
        )

        self.sql = migration_path.read_text()

    def test_active_fingerprint_unique_index_exists(self):
        self.assertIn(
            "CREATE UNIQUE INDEX IF NOT EXISTS",
            self.sql,
        )

        self.assertIn(
            "uq_osiris_memory_active_fingerprint",
            self.sql,
        )

        self.assertIn(
            "fingerprint",
            self.sql,
        )

        self.assertIn(
            "WHERE status = 'active'",
            self.sql,
        )

    def test_active_fingerprint_migration_is_non_destructive(self):
        upper = self.sql.upper()

        for forbidden in (
            "DROP ",
            "TRUNCATE ",
            "DELETE FROM",
        ):
            self.assertNotIn(
                forbidden,
                upper,
            )

    def test_active_fingerprint_migration_is_tracked(self):
        self.assertIn(
            "002_active_memory_fingerprint_unique",
            self.sql,
        )
