-- git/cicd/project-manager pasan de SERVICE_GRANTS (global) a
-- TENANT_GRANTABLE_PERMISSIONS (por proyecto) -- pedido explícito del
-- usuario: "asimismo con el git, Drive, CI/CD, Proyectos". Sin esto,
-- full_permissions() (que ya filtra extra_permissions contra el conjunto
-- concedible actual, ver 0008) dejaría a cualquier cuenta con estos
-- permisos sin acceso de golpe al desplegar. Migra el acceso que tenía
-- cada cuenta al tenant "freya" (el único que existía antes de este
-- cambio) y limpia el dato viejo.

INSERT INTO user_tenant_grants (user_id, tenant_id, permissions)
SELECT
    id,
    'freya',
    ARRAY(
        SELECT unnest(extra_permissions)
        INTERSECT
        SELECT unnest(ARRAY[
            'read:git', 'write:git',
            'read:cicd', 'write:cicd',
            'read:project-manager', 'write:project-manager'
        ])
    )
FROM users
WHERE extra_permissions && ARRAY[
    'read:git', 'write:git',
    'read:cicd', 'write:cicd',
    'read:project-manager', 'write:project-manager'
]
ON CONFLICT (user_id, tenant_id) DO UPDATE
SET permissions = ARRAY(
    SELECT DISTINCT unnest(user_tenant_grants.permissions || EXCLUDED.permissions)
);

UPDATE users
SET extra_permissions = ARRAY(
    SELECT unnest(extra_permissions)
    EXCEPT
    SELECT unnest(ARRAY[
        'read:git', 'write:git',
        'read:cicd', 'write:cicd',
        'read:project-manager', 'write:project-manager'
    ])
)
WHERE extra_permissions && ARRAY[
    'read:git', 'write:git',
    'read:cicd', 'write:cicd',
    'read:project-manager', 'write:project-manager'
];
