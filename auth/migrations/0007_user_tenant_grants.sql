-- Accesos por proyecto (pedido explícito del usuario: tener un tenant
-- asignado no da automáticamente todos los permisos -- storage y
-- monitoring se conceden aparte, por tenant, igual que antes se concedían
-- de forma global vía extra_permissions). Reemplaza, para estos dos
-- servicios, lo que "storage"/"monitoring" hacían en SERVICE_GRANTS -- git,
-- cicd y project-manager siguen siendo grants planos, sin tenant.
CREATE TABLE user_tenant_grants (
    user_id text NOT NULL,
    tenant_id text NOT NULL,
    permissions text[] NOT NULL DEFAULT '{}',
    PRIMARY KEY (user_id, tenant_id)
);
