BEGIN;

CREATE TABLE IF NOT EXISTS osiris_schema_migrations (
    migration_id TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS osiris_memory_records (
    id UUID PRIMARY KEY,

    kind TEXT NOT NULL
        CHECK (
            kind IN (
                'semantic',
                'episodic',
                'learning',
                'preference',
                'instruction',
                'observation'
            )
        ),

    content TEXT NOT NULL
        CHECK (
            length(btrim(content)) > 0
        ),

    title TEXT,

    status TEXT NOT NULL DEFAULT 'active'
        CHECK (
            status IN (
                'active',
                'superseded',
                'invalidated',
                'deleted'
            )
        ),

    source_type TEXT NOT NULL DEFAULT 'system'
        CHECK (
            source_type IN (
                'user',
                'assistant',
                'system',
                'agent',
                'device',
                'document',
                'migration'
            )
        ),

    source_ref TEXT,

    confidence DOUBLE PRECISION NOT NULL DEFAULT 1.0
        CHECK (
            confidence >= 0.0
            AND confidence <= 1.0
        ),

    importance SMALLINT NOT NULL DEFAULT 5
        CHECK (
            importance >= 1
            AND importance <= 10
        ),

    sensitivity TEXT NOT NULL DEFAULT 'private'
        CHECK (
            sensitivity IN (
                'internal',
                'private',
                'restricted'
            )
        ),

    retention TEXT NOT NULL DEFAULT 'persistent'
        CHECK (
            retention IN (
                'session',
                'temporary',
                'persistent',
                'pinned'
            )
        ),

    subject_entity_id TEXT,

    superseded_by_id UUID
        REFERENCES osiris_memory_records(id)
        ON DELETE RESTRICT,

    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,

    observed_at TIMESTAMPTZ,
    valid_from TIMESTAMPTZ,
    valid_until TIMESTAMPTZ,

    metadata JSONB NOT NULL
        DEFAULT '{}'::jsonb
        CHECK (
            jsonb_typeof(metadata) = 'object'
        ),

    fingerprint TEXT NOT NULL
        CHECK (
            fingerprint ~ '^[0-9a-f]{64}$'
        ),

    CONSTRAINT chk_memory_updated_time
        CHECK (
            updated_at >= created_at
        ),

    CONSTRAINT chk_memory_valid_window
        CHECK (
            valid_until IS NULL
            OR valid_from IS NULL
            OR valid_until >= valid_from
        ),

    CONSTRAINT chk_memory_supersession
        CHECK (
            (
                status = 'superseded'
                AND superseded_by_id IS NOT NULL
            )
            OR
            (
                status <> 'superseded'
                AND superseded_by_id IS NULL
            )
        ),

    CONSTRAINT chk_memory_no_self_supersession
        CHECK (
            superseded_by_id IS NULL
            OR superseded_by_id <> id
        )
);

CREATE INDEX IF NOT EXISTS
    idx_osiris_memory_kind_status
ON osiris_memory_records (
    kind,
    status
);

CREATE INDEX IF NOT EXISTS
    idx_osiris_memory_created
ON osiris_memory_records (
    created_at DESC
);

CREATE INDEX IF NOT EXISTS
    idx_osiris_memory_fingerprint
ON osiris_memory_records (
    fingerprint
);

CREATE INDEX IF NOT EXISTS
    idx_osiris_memory_subject_status
ON osiris_memory_records (
    subject_entity_id,
    status
)
WHERE subject_entity_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS
    idx_osiris_memory_source
ON osiris_memory_records (
    source_type,
    source_ref
);

CREATE INDEX IF NOT EXISTS
    idx_osiris_memory_observed
ON osiris_memory_records (
    observed_at DESC
)
WHERE observed_at IS NOT NULL;

INSERT INTO osiris_schema_migrations (
    migration_id,
    description
)
VALUES (
    '001_core_memory',
    'Create canonical OSIRIS Memory Core storage'
)
ON CONFLICT (migration_id) DO NOTHING;

COMMIT;
