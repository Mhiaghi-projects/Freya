-- Esquema de secrets: claves de datos por tenant, secretos versionados,
-- auditoría de accesos. Envelope encryption (docs/ROADMAP.md sec-02): la
-- master key nunca toca esta base, sólo las DEK ya cifradas con ella.

CREATE TABLE secret_data_keys (
    id text PRIMARY KEY,
    wrapped_dek text NOT NULL,
    dek_nonce text NOT NULL,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    retired_at timestamptz
);

CREATE TABLE secrets (
    id text PRIMARY KEY,
    namespace text NOT NULL,
    key text NOT NULL,
    type text NOT NULL DEFAULT 'generic',
    description text NOT NULL DEFAULT '',
    current_version int NOT NULL DEFAULT 1,
    expires_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz
);

-- Parcial: permite recrear un secreto borrado con la misma key.
CREATE UNIQUE INDEX secrets_namespace_key_idx
    ON secrets (namespace, key) WHERE deleted_at IS NULL;

CREATE TABLE secret_versions (
    id text PRIMARY KEY,
    secret_id text NOT NULL REFERENCES secrets (id) ON DELETE CASCADE,
    version int NOT NULL,
    data_key_id text NOT NULL REFERENCES secret_data_keys (id),
    value_ciphertext text NOT NULL,
    value_nonce text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX secret_versions_secret_version_idx
    ON secret_versions (secret_id, version);

CREATE TABLE secrets_audit_log (
    id text PRIMARY KEY,
    namespace text NOT NULL,
    key text NOT NULL,
    action text NOT NULL,
    actor_service text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX secrets_audit_log_namespace_idx ON secrets_audit_log (namespace, created_at DESC);
