-- Hallazgo de seguridad (revisión de la migración a accesos por tenant):
-- storage y monitoring vivían en extra_permissions (grant plano, global)
-- antes de pasar a ser por-proyecto (0007_user_tenant_grants.sql). Si a
-- alguna cuenta le hubiera quedado uno de estos cuatro permisos en la
-- columna, seguiría dándole acceso GLOBAL a todos los tenants -- exacto
-- lo que el modelo nuevo busca impedir (full_permissions() en
-- app/domain/users.py ya lo filtra en runtime; esto limpia el dato en
-- reposo también, por si algo más llegara a leer la columna sin pasar
-- por ahí).
UPDATE users
SET extra_permissions = array_remove(
    array_remove(
        array_remove(
            array_remove(extra_permissions, 'read:storage'),
            'write:storage'
        ),
        'read:monitoring'
    ),
    'write:monitoring'
)
WHERE extra_permissions && ARRAY['read:storage', 'write:storage', 'read:monitoring', 'write:monitoring'];
