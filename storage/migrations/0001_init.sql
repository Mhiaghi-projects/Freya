-- Esquema de storage: buckets, objetos y versiones. Los bytes viven en el
-- volumen /data (docs/ROADMAP.md Fase 4); aquí sólo hay metadatos.

CREATE TABLE storage_buckets (
    id text PRIMARY KEY,
    bucket text NOT NULL,
    versioning boolean NOT NULL DEFAULT false,
    encryption boolean NOT NULL DEFAULT false,
    max_versions int NOT NULL DEFAULT 5,
    quota_bytes bigint NOT NULL DEFAULT 10737418240,
    created_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz
);

CREATE UNIQUE INDEX storage_buckets_bucket_idx
    ON storage_buckets (bucket) WHERE deleted_at IS NULL;

CREATE TABLE storage_objects (
    id text PRIMARY KEY,
    bucket text NOT NULL,
    key text NOT NULL,
    current_version_id text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz
);

CREATE UNIQUE INDEX storage_objects_bucket_key_idx
    ON storage_objects (bucket, key) WHERE deleted_at IS NULL;

CREATE TABLE storage_versions (
    id text PRIMARY KEY,
    object_id text NOT NULL REFERENCES storage_objects (id) ON DELETE CASCADE,
    status text NOT NULL DEFAULT 'ACTIVE',
    size bigint NOT NULL,
    mime_type text NOT NULL,
    etag text NOT NULL,
    metadata text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX storage_versions_object_idx ON storage_versions (object_id, created_at DESC);
