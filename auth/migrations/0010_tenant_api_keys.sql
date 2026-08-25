-- Credenciales de tenant "como las nubes" (pedido explícito del usuario):
-- un par key_id/api_secret por proyecto para que scripts, CI externo u
-- otro backend llamen a Freya sin pasar por un login de navegador -- se
-- canjean por un JWT de corta duración vía POST /api/v1/auth/token (ver
-- app/domain/tenant_keys.py), mismo mecanismo que ya usa un servicio
-- interno con su api_secret vía /authenticate/service, pero scoped a un
-- tenant y a TENANT_GRANTABLE_PERMISSIONS -- nunca a un permiso plano de
-- servicio. Sólo se guarda el hash del secreto (mismo Argon2id que
-- passwords/api_secret de servicio); el secreto en claro sólo se muestra
-- una vez, al crearlo.
--
-- key_id es el identificador público (va en claro en cada llamada, como un
-- Access Key ID de AWS) -- no confundir con "id", que es el id interno de
-- fila con prefijo (freya_common.new_id).
CREATE TABLE tenant_api_keys (
    id text PRIMARY KEY,
    tenant_id text NOT NULL,
    key_id text NOT NULL UNIQUE,
    secret_hash text NOT NULL,
    name text NOT NULL DEFAULT '',
    permissions text[] NOT NULL DEFAULT '{}',
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by text
);

CREATE INDEX tenant_api_keys_tenant_idx ON tenant_api_keys (tenant_id);
