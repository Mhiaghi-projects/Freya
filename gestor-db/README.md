# gestor-db

Única puerta a PostgreSQL de toda Freya. Ningún otro servicio se conecta a
`database` directamente. Contrato interno, no expuesto por el gateway — ver
`docs/freya-api-contract.md` §4 y §15.

## Autenticación

Con `FREYA_AUTH_ENABLED=true`: JWT RSA (RS256) validado contra el JWKS de
`auth` (cacheado, sin llamada por petición). El `service` del token tiene
que coincidir con `X-Service-Name` — esa cabecera no es una credencial,
cualquiera podría escribirla; lo que prueba la identidad es el JWT.

Con `FREYA_AUTH_ENABLED=false` (bootstrap, antes de que `auth` exista):
sólo se acepta el token estático de `/run/secrets/bootstrap_token`
(`.\freya.ps1 secret gestor-db bootstrap_token`).

## Schema por tenant

Un schema es de un **tenant**, no de un tenant+servicio: `"fortuna"` es el
schema del tenant `fortuna`; varios servicios comparten ese schema, en
tablas distintas. `"fortuna_staging"` es un schema con nombre dentro del
mismo tenant (§4.5). El `"schema"` del cuerpo tiene que pertenecer al
tenant de `X-Tenant-Context` — si no, `403 TENANT_MISMATCH`.

## Endpoints

Sin prefijo `/api/v1` (contrato interno). `Authorization: Bearer <jwt>`.

| Ruta | Método | Permiso | Qué hace |
|---|---|---|---|
| `/query` | POST | `read:database` | `{schema, table, select, where, order_by, limit, offset}`. Lectura estructurada — ver operadores en §4.1. |
| `/mutate` | POST | `write:database` | `{schema, table, action, where, data, returning, conflict_target}`. `action`: `insert`\|`update`\|`delete`\|`upsert`. |
| `/transaction` | POST | `write:database` | `{schema, operations: [...], isolation_level}`. Varias operaciones atómicas; rollback si cualquiera falla. |
| `/schemas` | GET/POST | `read:database`/`write:database` | Lista o crea schemas del tenant. |
| `/tables` | GET | `read:database` | `?schema=`. Tablas y columnas de un schema. |
| `/migrations` | POST | `write:database` | `{schema, migrations: [{filename, sql}]}`. Las aplica en orden, checksum en `public.freya_schema_migrations`, idempotente. |

Nunca SQL crudo: el DSL se traduce a SQL parametrizado en
`app/domain/query_builder.py`, con identificadores validados contra un
patrón estricto y valores siempre ligados (`$1`, `$2`...) — nunca
interpolados en el texto. DDL fuera de `/migrations` no existe: no hay
manera de mandarlo por `/mutate`.

Todo error de PostgreSQL se traduce al catálogo común: caída de conexión →
`503`, choque de unicidad → `409 DUPLICATE_RESOURCE` (sin el valor que
chocó — no se filtra por el mensaje), otra restricción violada →
`422 VALIDATION_ERROR`, cualquier otra cosa → `400`.

## Estructura

```
app/
├── main.py                creación de la app, lifespan, verificador RSA
├── config.py               settings: conexión a database, bootstrap
├── deps.py                  JWT + cruce service/X-Service-Name
├── api/                      query, mutate, transaction, schemas, tables, migrations
├── domain/
│   ├── pool.py                pool asyncpg con reconexión
│   ├── tenant.py               resolución y validación de schema por tenant
│   ├── query_builder.py         DSL -> SQL parametrizado (§4)
│   └── migrations.py           motor de migraciones versionadas
├── infra/db.py               traducción de errores de asyncpg
└── models/requests.py          esquemas pydantic del DSL
```

## Tests

```powershell
.\freya.ps1 test gestor-db
.\freya.ps1 lint gestor-db
```
