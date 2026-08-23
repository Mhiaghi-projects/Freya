-- Esquema de auth: cuentas de servicio, usuarios y refresh tokens.
--
-- id es siempre un id con prefijo tipo ULID, generado por la app
-- (freya_common.new_id) — docs/freya-api-contract.md usa IDs legibles
-- ("usr_...", "sva_..."), no UUID. permissions es text[] (no jsonb): así
-- asyncpg lo liga nativamente sin necesitar un codec aparte.

CREATE TABLE service_accounts (
    id text PRIMARY KEY,
    service text NOT NULL UNIQUE,
    api_secret_hash text NOT NULL,
    permissions text[] NOT NULL DEFAULT '{}',
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz
);

CREATE TABLE users (
    id text PRIMARY KEY,
    email text NOT NULL UNIQUE,
    password_hash text NOT NULL,
    first_name text NOT NULL,
    last_name text NOT NULL DEFAULT '',
    role text NOT NULL DEFAULT 'user',
    verified boolean NOT NULL DEFAULT false,
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    last_login timestamptz,
    deleted_at timestamptz
);

-- Rotación de refresh token: "id" es el selector (indexado, no secreto),
-- secret_hash es la parte que se verifica. Reusar un id ya marcado
-- revoked_at revoca toda la familia.
CREATE TABLE refresh_tokens (
    id text PRIMARY KEY,
    user_id text NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    family_id text NOT NULL,
    secret_hash text NOT NULL,
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX refresh_tokens_family_idx ON refresh_tokens (family_id);
