BEGIN;

CREATE UNIQUE INDEX IF NOT EXISTS
    uq_osiris_memory_active_fingerprint
ON osiris_memory_records (
    fingerprint
)
WHERE status = 'active';

INSERT INTO osiris_schema_migrations (
    migration_id,
    description
)
VALUES (
    '002_active_memory_fingerprint_unique',
    'Enforce one active canonical memory per fingerprint'
)
ON CONFLICT (migration_id) DO NOTHING;

COMMIT;
