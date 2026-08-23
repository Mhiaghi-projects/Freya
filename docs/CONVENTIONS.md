# Freya — Convenciones

Estas reglas son obligatorias para todo servicio. Si un servicio no las cumple,
la task no está terminada.

> **`docs/freya-api-contract.md` es la fuente de verdad para el contrato de
> API** y sustituye lo que este documento decía sobre §2 (contrato HTTP:
> cabeceras, sobre de respuesta, catálogo de errores) y §4 (autenticación).
> En concreto, ya no aplican de este documento: `X-Freya-Tenant`/
> `X-Freya-Service`/`X-Request-Id` (ahora `X-Tenant-Context`/
> `X-Service-Name`/`X-Request-ID` para llamadas internas — ver
> freya-api-contract.md §15.1), el formato de error `{"error": {...}}` sin
> sobre (ahora `{"success", "data"|"error", "meta"}` — §1.3), los códigos de
> error en `snake_case` (ahora `UPPER_SNAKE` del catálogo — §1.7), EdDSA para
> el JWT de servicio (ahora RSA/RS256 — §15.1), y UUIDv7 como id (ahora
> `<prefijo>_<ulid>`, p.ej. `usr_01H8X...` — `freya_common.new_id`). El
> resto de este documento (estructura de servicio, migraciones, logs,
> contenedores, "definición de terminado") sigue vigente.

## 1. Estructura de un servicio

Cada servicio propio es su propio proyecto en la raíz del repo — su propio
git, su propio pipeline (docs/ARCHITECTURE.md §2.1) — no un subdirectorio
de `services/`. Ahí sólo quedan ya los backends de terceros sin código
propio que separar (`database`, `metrics`, `logs`, `dashboards`).

```
<nombre>/
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── README.md
├── app/
│   ├── main.py            # creación de la app, montaje de routers
│   ├── config.py          # settings desde entorno (pydantic-settings)
│   ├── deps.py            # dependencias FastAPI (auth, db, tenant)
│   ├── api/               # routers, un fichero por recurso
│   ├── domain/            # lógica de negocio, sin FastAPI ni SQL
│   ├── infra/             # clientes: gestor-db, secrets, storage, auth
│   └── models/            # esquemas pydantic de entrada y salida
└── tests/
```

Ningún fichero pasa de **500 líneas**. Si crece, se parte por responsabilidad.

## 2. Contrato HTTP

### Prefijo y versión
Todas las rutas cuelgan de `/api/v1/`. Fuera de ese prefijo sólo existen
`/health`, `/ready` y `/metrics`.

### Cabeceras obligatorias en llamadas entre servicios

| Cabecera | Obligatoria | Descripción |
|---|---|---|
| `Authorization` | sí | `Bearer <jwt>` emitido por `auth` |
| `X-Freya-Tenant` | sí | tenant destino; `freya` para uso interno |
| `X-Request-Id` | sí | UUIDv4; se propaga sin modificar por toda la cadena |
| `X-Freya-Service` | sí | nombre del servicio llamante |

Si el servicio recibe una petición sin `X-Request-Id`, genera uno y lo devuelve
en la respuesta. Siempre se devuelve `X-Request-Id` en la respuesta.

### Formato de error

Un único formato, en todos los servicios, para todos los errores:

```json
{
  "error": {
    "code": "resource_not_found",
    "message": "El bucket 'builds' no existe en el tenant 'freya'",
    "details": {"bucket": "builds", "tenant": "freya"},
    "request_id": "0f3c...",
    "service": "storage"
  }
}
```

`code` es un identificador estable en `snake_case`. `message` es para humanos y
puede cambiar. Los clientes se programan contra `code`, nunca contra `message`.

Códigos de estado: `400` validación, `401` sin credencial o inválida,
`403` credencial válida sin permiso, `404` no existe o no visible para el tenant,
`409` conflicto de estado, `422` semántica inválida, `429` rate limit,
`503` dependencia caída.

### Paginación

Cursor, no offset. `GET /api/v1/recursos?limit=50&cursor=<opaco>` devuelve:

```json
{"items": [...], "next_cursor": "...", "has_more": true}
```

`limit` por defecto 50, máximo 200.

## 3. Endpoints operativos

| Ruta | Auth | Qué devuelve |
|---|---|---|
| `/health` | no | `{"status":"ok","service":"...","version":"..."}` — el proceso vive |
| `/ready` | no | comprueba dependencias; `503` si alguna falla |
| `/metrics` | red interna | formato Prometheus |

`/health` **nunca** toca la base de datos ni la red. Es el healthcheck de Docker.
`/ready` sí comprueba dependencias, y es lo que consulta `gestor-monitoring`.

## 4. Autenticación

### Entre servicios
`client_credentials` contra `auth`, JWT EdDSA de 5 minutos, validado localmente
contra el JWKS cacheado. El cliente compartido de la plantilla gestiona la
renovación del token; ningún servicio implementa esto por su cuenta.

### Usuarios
Access token de 15 minutos + refresh token rotativo de 30 días. El refresh token
se guarda hasheado (Argon2id), nunca en claro.

### Scopes
Formato `<servicio>:<recurso>:<acción>`, por ejemplo `storage:object:write`,
`git:repo:admin`, `pm:task:read`. El comodín `*` sólo se concede a roles de
administración de plataforma.

## 5. Datos

- Ningún servicio se conecta a PostgreSQL directamente. Todo pasa por `gestor-db`.
  La única excepción es `gestor-db` mismo.
- Un schema por servicio y tenant: `<tenant>_<servicio>`.
- Toda tabla lleva `id` (UUIDv7), `created_at`, `updated_at` en UTC.
- Borrado lógico por defecto (`deleted_at`), borrado físico sólo bajo petición
  explícita del propietario del dato.
- Las migraciones son ficheros SQL numerados en `migrations/NNNN_nombre.sql`,
  aplicados por `gestor-db`. Sin ORM para el esquema.

## 6. Configuración y secretos

- Toda la configuración viene del entorno, leída con `pydantic-settings`.
- Prefijo `FREYA_`. Ejemplo: `FREYA_AUTH_URL`, `FREYA_LOG_LEVEL`.
- **Ningún secreto en el repositorio.** Ni en `docker-compose.yml`, ni en
  ficheros de ejemplo con valores reales.
- Durante el bootstrap, los secretos se leen de ficheros montados en
  `/run/secrets/`. Una vez `secrets` esté operativo, se piden a `secrets`
  al arrancar y se cachean en memoria.

## 7. Logs

JSON en una línea a stdout. Nunca a fichero, nunca a stderr salvo crash.

```json
{"ts":"2026-08-20T14:03:11.482Z","level":"info","service":"storage",
 "request_id":"0f3c...","tenant":"freya","msg":"object stored",
 "duration_ms":14,"path":"/api/v1/objects"}
```

Prohibido loguear tokens, contraseñas, contenido de secretos o cuerpos de
petición completos.

## 8. Contenedores

- Base: `python:3.12-slim`. Build multi-stage.
- El proceso corre como usuario `freya` (UID 10001), nunca root.
- `read_only: true` en el filesystem, con `tmpfs` para `/tmp`.
- Límites obligatorios en cada `docker-compose.yml`:
  ```yaml
  deploy:
    resources:
      limits: {cpus: "0.50", memory: 256M}
  ```
- `restart: unless-stopped`.
- Healthcheck apuntando a `/health`.
- Etiqueta `freya.service=<nombre>` para que `gestor-monitoring` descubra targets.

## 9. Versionado y Git

- Ramas: `main` estable, `feat/<servicio>-<descripción>`, `fix/<...>`.
- Commits en formato Conventional Commits con el servicio como scope:
  `feat(storage): añadir multipart upload`.
- Tags: `<servicio>/vX.Y.Z`. Cada servicio se versiona por separado.

## 10. Definición de "terminado"

Una task está terminada cuando:

1. El código cumple estas convenciones y ningún fichero pasa de 500 líneas.
2. Hay tests y pasan dentro del contenedor.
3. El servicio arranca con `docker compose up` y `/ready` devuelve `200`.
4. `README.md` del servicio documenta los endpoints nuevos.
5. Las variables de entorno nuevas están en `.env.example`.
