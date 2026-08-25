# Freya API Gateway — Contrato de API

**Versión:** 1.0
**Base URL:** `https://freya.local/api/v1`
**Entry point:** todo el tráfico externo entra por `traefik` → `frontend`. Ningún servicio interno se expone directamente.

> **Nota sobre este documento:** es el contrato *objetivo*, no siempre el
> reflejo exacto de lo que corre hoy (rutas como `/auth/admin/audit-logs`
> o el header `X-Tenant-ID` son el diseño original, no lo desplegado —
> para la superficie realmente en producción, la fuente de verdad es el
> código de cada servicio, `app/api/*.py`, no este documento). La §3.9 y
> la §16.1 son la excepción: se
> reescribieron para documentar el modelo de tenants y accesos por
> proyecto tal como quedó implementado (2026-08-24), con sus rutas y
> nombres de cabecera reales (`X-Tenant-Context`, no `X-Tenant-ID`),
> incluyendo el acceso a gestor-db "como un RDS" del propio proyecto
> (grant `database`, ver §3.9).

---

## 1. Convenciones Globales

Estas reglas aplican a **todos** los endpoints. No se repiten en cada contrato individual.

### 1.1 Headers de Request

| Header | Obligatorio | Descripción |
|--------|-------------|-------------|
| `Content-Type` | Sí (POST/PUT) | Siempre `application/json`, salvo uploads (`multipart/form-data` u `octet-stream`) |
| `X-Tenant-ID` | Sí | Identificador del tenant (`freya`, `fortuna`, `potato`) |
| `Authorization` | Condicional | `Bearer {jwt}` — para usuarios y admins |
| `X-API-Key` | Condicional | Para service accounts (en lugar de `Authorization`) |
| `X-API-Secret` | Condicional | Acompaña siempre a `X-API-Key` |
| `X-Request-ID` | No | UUID generado por el cliente; se propaga en logs y respuesta |
| `Idempotency-Key` | No | UUID; en POST evita duplicados si se reintenta |

**Regla de autenticación:** un request usa `Authorization: Bearer` **o** el par `X-API-Key` + `X-API-Secret`, nunca ambos. Si vienen ambos → `400 BAD_REQUEST`.

### 1.2 Headers de Response

| Header | Descripción |
|--------|-------------|
| `X-Request-ID` | Eco del request, o generado por el gateway |
| `X-RateLimit-Limit` | Límite de requests en la ventana |
| `X-RateLimit-Remaining` | Requests restantes |
| `X-RateLimit-Reset` | Timestamp Unix del reset |
| `X-Upstream-Service` | Servicio interno que atendió (ej: `storage`) — solo en modo debug |

### 1.3 Envoltura de Respuesta

**Éxito:**
```json
{
  "success": true,
  "data": { },
  "meta": {
    "request_id": "req_01H8X...",
    "timestamp": 1692345600,
    "tenant_id": "fortuna"
  }
}
```

**Error:**
```json
{
  "success": false,
  "error": {
    "code": "INVALID_CREDENTIALS",
    "message": "Email or password is incorrect",
    "details": [
      { "field": "password", "issue": "does_not_match" }
    ]
  },
  "meta": {
    "request_id": "req_01H8X...",
    "timestamp": 1692345600
  }
}
```

**Lista paginada** (`data` es array, `meta` incluye `pagination`):
```json
{
  "success": true,
  "data": [ ],
  "meta": {
    "pagination": {
      "total": 342,
      "limit": 50,
      "offset": 0,
      "next_cursor": "eyJpZCI6..."
    },
    "request_id": "req_01H8X...",
    "timestamp": 1692345600
  }
}
```

### 1.4 Paginación (query params)

| Param | Tipo | Default | Máx | Descripción |
|-------|------|---------|-----|-------------|
| `limit` | int | 50 | 200 | Elementos por página |
| `offset` | int | 0 | — | Desplazamiento (paginación por offset) |
| `cursor` | string | — | — | Cursor opaco (paginación por cursor; preferida) |
| `sort` | string | varía | — | Campo de orden, prefijo `-` para descendente (ej: `-created_at`) |

### 1.5 Filtros comunes

| Param | Tipo | Descripción |
|-------|------|-------------|
| `created_after` | ISO 8601 | Filtra por fecha de creación |
| `created_before` | ISO 8601 | Filtra por fecha de creación |
| `status` | string | Filtro por estado (valores según recurso) |
| `q` | string | Búsqueda de texto libre |

### 1.6 Códigos HTTP

| Código | Significado | Cuándo |
|--------|-------------|--------|
| `200` | OK | GET/PUT/DELETE exitoso |
| `201` | Created | POST que crea recurso |
| `202` | Accepted | Operación asíncrona encolada (builds, webhooks) |
| `204` | No Content | DELETE sin cuerpo de respuesta |
| `400` | Bad Request | Payload inválido, params mal formados |
| `401` | Unauthorized | Sin credenciales, JWT inválido o expirado |
| `403` | Forbidden | Autenticado pero sin permiso; tenant incorrecto |
| `404` | Not Found | Recurso no existe o no pertenece al tenant |
| `409` | Conflict | Duplicado (email ya existe, bucket ya existe) |
| `413` | Payload Too Large | Upload excede límite del tenant |
| `422` | Unprocessable Entity | Validación semántica falló |
| `429` | Too Many Requests | Rate limit excedido |
| `500` | Internal Server Error | Fallo del gateway |
| `502` | Bad Gateway | Servicio interno respondió mal |
| `503` | Service Unavailable | Servicio interno caído |
| `504` | Gateway Timeout | Servicio interno no respondió a tiempo |

### 1.7 Catálogo de Códigos de Error

**Autenticación / Autorización**
| Código | HTTP | Descripción |
|--------|------|-------------|
| `MISSING_CREDENTIALS` | 401 | No se envió `Authorization` ni `X-API-Key` |
| `INVALID_CREDENTIALS` | 401 | Usuario/password o key/secret incorrectos |
| `TOKEN_EXPIRED` | 401 | JWT expirado; usar refresh token |
| `TOKEN_INVALID` | 401 | Firma inválida o malformado |
| `TOKEN_REVOKED` | 401 | Token revocado tras logout |
| `INSUFFICIENT_PERMISSIONS` | 403 | Rol sin el permiso requerido |
| `TENANT_MISMATCH` | 403 | `X-Tenant-ID` no coincide con el del token |
| `TENANT_INACTIVE` | 403 | Acceso a Freya desactivado para ese tenant |
| `ACCOUNT_LOCKED` | 403 | Bloqueado por intentos fallidos |

**Validación**
| Código | HTTP | Descripción |
|--------|------|-------------|
| `VALIDATION_ERROR` | 422 | Uno o más campos inválidos (ver `details`) |
| `MISSING_REQUIRED_FIELD` | 400 | Campo obligatorio ausente |
| `INVALID_FORMAT` | 400 | Formato incorrecto (email, fecha, UUID) |
| `RESOURCE_NOT_FOUND` | 404 | Recurso inexistente |
| `DUPLICATE_RESOURCE` | 409 | Ya existe con ese identificador |

**Límites**
| Código | HTTP | Descripción |
|--------|------|-------------|
| `RATE_LIMIT_EXCEEDED` | 429 | Demasiados requests |
| `QUOTA_EXCEEDED` | 403 | Cuota del tenant agotada (storage, builds) |
| `PAYLOAD_TOO_LARGE` | 413 | Archivo/body excede el máximo |

**Infraestructura**
| Código | HTTP | Descripción |
|--------|------|-------------|
| `UPSTREAM_UNAVAILABLE` | 503 | Servicio interno caído |
| `UPSTREAM_TIMEOUT` | 504 | Servicio interno no respondió |
| `INTERNAL_ERROR` | 500 | Error no clasificado |

### 1.8 Rate Limiting (por defecto)

| Tipo de cliente | Límite | Ventana |
|-----------------|--------|---------|
| Usuario autenticado (GUI) | 300 req | 1 min |
| Service account | 1000 req | 1 min |
| Endpoints de auth (login/signup) | 10 req | 15 min |
| Upload a storage | 100 req | 1 min |
| Sin autenticar | 20 req | 1 min |

Al exceder: `429` con header `Retry-After` en segundos.

### 1.9 Versionado

- Versión en la ruta: `/api/v1/...`
- Cambios retrocompatibles (nuevos campos opcionales) no incrementan versión
- Breaking changes → `/api/v2/`, con `v1` en deprecación por 6 meses
- Header de respuesta `X-API-Deprecation` cuando un endpoint está marcado para retiro

---

## 2. Auth — Autenticación de Usuarios

### 2.1 `POST /auth/sign-up`

Registra un usuario dentro de un tenant.

**Auth:** ninguna (público, si el tenant lo permite)

**Request**
```json
{
  "email": "user@fortuna.com",
  "password": "MinSecure123!",
  "first_name": "Carlos",
  "last_name": "Ruiz",
  "metadata": { "department": "finance" }
}
```

| Campo | Tipo | Oblig. | Reglas |
|-------|------|--------|--------|
| `email` | string | Sí | Formato email; único dentro del tenant |
| `password` | string | Sí | Mín 8 chars, 1 mayúscula, 1 número, 1 símbolo |
| `first_name` | string | Sí | 1–100 chars |
| `last_name` | string | No | 0–100 chars |
| `metadata` | object | No | Máx 4KB, claves libres |

**Response `201`**
```json
{
  "success": true,
  "data": {
    "user_id": "usr_fortuna_01H8X",
    "email": "user@fortuna.com",
    "first_name": "Carlos",
    "role": "user",
    "verified": false,
    "created_at": 1692345600
  }
}
```

**Errores:** `DUPLICATE_RESOURCE` (409), `VALIDATION_ERROR` (422), `TENANT_INACTIVE` (403), `RATE_LIMIT_EXCEEDED` (429)

---

### 2.2 `POST /auth/sign-in`

**Auth:** ninguna

**Request**
```json
{
  "email": "user@fortuna.com",
  "password": "MinSecure123!"
}
```

**Response `200`**
```json
{
  "success": true,
  "data": {
    "access_token": "eyJhbGciOiJSUzI1NiIs...",
    "refresh_token": "eyJhbGciOiJSUzI1NiIs...",
    "token_type": "Bearer",
    "expires_in": 900,
    "user": {
      "user_id": "usr_fortuna_01H8X",
      "email": "user@fortuna.com",
      "first_name": "Carlos",
      "role": "user",
      "permissions": ["read:self", "update:self"],
      "tenant_id": "fortuna"
    }
  }
}
```

**Response `200` con MFA pendiente**
```json
{
  "success": true,
  "data": {
    "mfa_required": true,
    "session_id": "mfa_01H8X",
    "methods": ["totp"],
    "expires_in": 300
  }
}
```

**Errores:** `INVALID_CREDENTIALS` (401), `ACCOUNT_LOCKED` (403), `TENANT_INACTIVE` (403), `RATE_LIMIT_EXCEEDED` (429)

---

### 2.3 `POST /auth/refresh-token`

**Auth:** ninguna (el refresh token es la credencial)

**Request**
```json
{ "refresh_token": "eyJhbGciOiJSUzI1NiIs..." }
```

**Response `200`**
```json
{
  "success": true,
  "data": {
    "access_token": "eyJhbGciOiJSUzI1NiIs...",
    "token_type": "Bearer",
    "expires_in": 900
  }
}
```

**Errores:** `TOKEN_INVALID` (401), `TOKEN_EXPIRED` (401), `TOKEN_REVOKED` (401)

---

### 2.4 `POST /auth/sign-out`

**Auth:** `Bearer {access_token}`

**Request**
```json
{ "refresh_token": "eyJhbGciOiJSUzI1NiIs...", "all_devices": false }
```

**Response `204`** — sin cuerpo.

---

### 2.5 `POST /auth/verify-token`

Valida un JWT. Lo usan backends de proyectos externos.

**Auth:** `X-API-Key` + `X-API-Secret`

**Request**
```json
{ "token": "eyJhbGciOiJSUzI1NiIs..." }
```

**Response `200`**
```json
{
  "success": true,
  "data": {
    "valid": true,
    "type": "user",
    "tenant_id": "fortuna",
    "user_id": "usr_fortuna_01H8X",
    "email": "user@fortuna.com",
    "role": "user",
    "permissions": ["read:self"],
    "issued_at": 1692345600,
    "expires_at": 1692346500
  }
}
```

**Response `200` con token inválido** (no es error HTTP):
```json
{
  "success": true,
  "data": { "valid": false, "reason": "TOKEN_EXPIRED" }
}
```

---

### 2.6 `POST /auth/forgot-password`

**Auth:** ninguna

**Request**
```json
{ "email": "user@fortuna.com" }
```

**Response `202`** — siempre responde igual exista o no el usuario (evita enumeración):
```json
{
  "success": true,
  "data": { "message": "If the account exists, a reset code was issued", "expires_in": 900 }
}
```

---

### 2.7 `POST /auth/reset-password`

**Request**
```json
{
  "email": "user@fortuna.com",
  "reset_code": "A7X92K",
  "new_password": "NewSecure456!"
}
```

**Response `200`**
```json
{ "success": true, "data": { "message": "Password updated", "sessions_revoked": 3 } }
```

**Errores:** `TOKEN_INVALID` (401), `TOKEN_EXPIRED` (401), `VALIDATION_ERROR` (422)

---

### 2.8 `GET /auth/user-info`

**Auth:** `Bearer`

**Response `200`**
```json
{
  "success": true,
  "data": {
    "user_id": "usr_fortuna_01H8X",
    "email": "user@fortuna.com",
    "first_name": "Carlos",
    "last_name": "Ruiz",
    "role": "user",
    "permissions": ["read:self", "update:self"],
    "tenant_id": "fortuna",
    "verified": true,
    "created_at": 1692345600,
    "last_login": 1692430000
  }
}
```

---

### 2.9 `PUT /auth/profile`

**Auth:** `Bearer`

**Request** (todos opcionales; solo se actualiza lo enviado)
```json
{ "first_name": "Carlos", "last_name": "Ruiz Pérez", "metadata": { "department": "ops" } }
```

**Response `200`** — objeto usuario actualizado (mismo shape que 2.8).

---

### 2.10 `POST /auth/password/change`

**Auth:** `Bearer`

**Request**
```json
{ "current_password": "MinSecure123!", "new_password": "NewSecure456!" }
```

**Response `200`**
```json
{ "success": true, "data": { "message": "Password updated", "sessions_revoked": 2 } }
```

**Errores:** `INVALID_CREDENTIALS` (401) si `current_password` no coincide.

---

## 3. Auth Admin — Gestión de Usuarios del Tenant

Todos requieren `Bearer` con `role: admin` del tenant indicado en `X-Tenant-ID`.

### 3.1 `POST /auth/admin/users`

**Request**
```json
{
  "email": "nuevo@fortuna.com",
  "first_name": "Ana",
  "last_name": "López",
  "role": "user",
  "temporary_password": "TempPass123!",
  "force_password_change": true
}
```

| Campo | Tipo | Oblig. | Reglas |
|-------|------|--------|--------|
| `role` | enum | Sí | `user` \| `admin` |
| `temporary_password` | string | No | Si se omite, se genera y devuelve una vez |
| `force_password_change` | bool | No | Default `true` |

**Response `201`**
```json
{
  "success": true,
  "data": {
    "user_id": "usr_fortuna_01H9A",
    "email": "nuevo@fortuna.com",
    "role": "user",
    "temporary_password": "Xk9#mQ2p",
    "must_change_password": true,
    "created_at": 1692345600
  }
}
```

> `temporary_password` se devuelve **solo en esta respuesta**. No es recuperable después.

---

### 3.2 `GET /auth/admin/users`

**Query:** `limit`, `offset`, `role`, `status` (`active`|`inactive`), `q` (busca en email/nombre)

**Response `200`**
```json
{
  "success": true,
  "data": [
    {
      "user_id": "usr_fortuna_01H8X",
      "email": "user@fortuna.com",
      "first_name": "Carlos",
      "role": "user",
      "active": true,
      "verified": true,
      "last_login": 1692430000,
      "created_at": 1692345600
    }
  ],
  "meta": { "pagination": { "total": 42, "limit": 50, "offset": 0 } }
}
```

---

### 3.3 `GET /auth/admin/users/{user_id}`
Response `200` — objeto usuario completo (shape de 3.2 + `metadata`, `permissions`).

### 3.4 `PUT /auth/admin/users/{user_id}`
**Request:** `{ "first_name", "last_name", "active", "metadata" }` — todos opcionales.
**Response `200`** — usuario actualizado.

### 3.5 `DELETE /auth/admin/users/{user_id}`
**Query:** `hard=false` (default: soft delete, marca `active: false`)
**Response `204`**

### 3.6 `PUT /auth/admin/users/{user_id}/roles`
**Request:** `{ "role": "admin" }`
**Response `200`** — usuario con rol actualizado.
**Errores:** `INSUFFICIENT_PERMISSIONS` (403) si intenta degradar al último admin del tenant.

### 3.7 `POST /auth/admin/users/{user_id}/reset-password`
**Request:** `{ "temporary_password": "..." }` (opcional)
**Response `200`**
```json
{
  "success": true,
  "data": { "temporary_password": "Yh3$nL8w", "must_change_password": true, "sessions_revoked": 1 }
}
```

### 3.8 `GET /auth/admin/audit-logs`

**Query:** `limit`, `offset`, `action`, `user_id`, `status`, `created_after`, `created_before`

**Response `200`**
```json
{
  "success": true,
  "data": [
    {
      "log_id": "log_01H8X",
      "action": "sign_in",
      "actor_type": "user",
      "actor_id": "usr_fortuna_01H8X",
      "resource": "auth",
      "status": "success",
      "ip_address": "203.0.113.42",
      "user_agent": "Mozilla/5.0...",
      "timestamp": 1692345600
    }
  ],
  "meta": { "pagination": { "total": 1204, "limit": 50, "offset": 0 } }
}
```

---

### 3.9 Gestión de Tenants y Accesos por Proyecto (real, no aspiracional)

Esta subsección documenta lo que corre hoy, no el diseño original de §3.1–3.8
(ver nota al inicio del documento). Rutas reales, todas detrás de
`https://freya.local/api/admin/...` (frontend), `Bearer` con `role: admin`.

**Modelo:** un tenant es sólo aislamiento de datos (un schema en Postgres +
un bucket `project` en storage). El acceso de un usuario a un tenant es
independiente del tenant donde vive su propia cuenta (siempre `freya`) — se
concede por separado, servicio por servicio, vía `user_tenant_grants`
(`auth/app/domain/tenants.py: TENANT_GRANTABLE_PERMISSIONS`):
`storage`, `monitoring`, `git`, `cicd`, `project-manager`, `database`.

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/admin/tenants` | Lista todos los tenants registrados |
| POST | `/api/admin/tenants` | Crea el tenant y aprovisiona su schema + bucket en storage, git, cicd y project-manager (fan-out, ver `frontend/app/api/admin.py`) |
| DELETE | `/api/admin/tenants/{tenant_id}` | Borra el tenant entero: `DROP SCHEMA ... CASCADE` (storage, git, cicd, project-manager comparten schema-por-tenant) + directorio físico de blobs + filas de `user_tenant_grants`. **Irreversible.** Rechaza `tenant_id = "freya"` con `400` — el tenant de control-plane nunca se borra |
| GET | `/api/admin/tenant-grants` | Servicios concedibles por tenant y sus permisos (`{"storage": ["read:storage","write:storage"], ...}`) |
| GET | `/api/admin/users/{user_id}/tenants` | Grants actuales del usuario, por tenant |
| PUT | `/api/admin/users/{user_id}/tenants/{tenant_id}` | Reemplaza los permisos del usuario para ese tenant (`body: {"permissions": ["read:storage","write:storage"]}`) — lista vacía retira el acceso |

**Creación de tenant — Response `201`**
```json
{
  "success": true,
  "data": { "id": "athenea", "name": "Athenea", "created_at": 1745539200 }
}
```

**Cómo se consume desde cada servicio:** el navegador nunca elige el
tenant activo por sí solo. El usuario primero ve el *picker* de tenants a
los que tiene grant para ese servicio (Panel, Git, Drive, CI/CD,
Proyectos); al elegir uno, el frontend agrega `?project={tenant_id}` a
cada llamada siguiente, y la traduce en la cabecera `X-Tenant-Context`
hacia el backend correspondiente (nunca `X-Tenant-ID`, pese a lo que diga
§1.1 — ver §16.1). Una cuenta `admin` conserva el comportamiento sin
picker (ve todo lo que existe) salvo en storage y monitoring, donde queda
restringida a su propio tenant (`freya`) salvo que también reciba un grant
explícito — pedido deliberado del usuario ("admin sólo tiene vista global
de Freya"); en git/cicd/project-manager/database, el permiso plano del rol
admin sigue alcanzando para cualquier tenant, igual que en el diseño
original.

**Errores:** `403` si el `tenant_id` es `"freya"` en un `DELETE`; `404` si
el tenant no existe; `409` si ya existe uno con ese `id` en el `POST`.

---

## 4. Database — Acceso a Datos

Requiere `X-API-Key` + `X-API-Secret` (service account) o `Bearer` con permiso `read:database` / `write:database`.

### 4.1 `POST /database/query`

Ejecuta lectura. El gateway impide operaciones de escritura en este endpoint.

**Request**
```json
{
  "schema": "fortuna",
  "table": "transactions",
  "select": ["id", "amount", "status", "created_at"],
  "where": {
    "status": "pending",
    "amount": { "gte": 1000 }
  },
  "order_by": [{ "field": "created_at", "direction": "desc" }],
  "limit": 50,
  "offset": 0
}
```

**Operadores permitidos en `where`:**
| Operador | Significado |
|----------|-------------|
| valor directo | igualdad |
| `eq` / `neq` | igual / distinto |
| `gt` / `gte` | mayor / mayor o igual |
| `lt` / `lte` | menor / menor o igual |
| `in` / `nin` | dentro / fuera de lista |
| `like` | coincidencia parcial |
| `is_null` | booleano |
| `between` | array de 2 valores |

**Response `200`**
```json
{
  "success": true,
  "data": {
    "rows": [
      { "id": 1, "amount": 1500, "status": "pending", "created_at": "2026-08-20T10:00:00Z" }
    ],
    "row_count": 1,
    "execution_time_ms": 12
  },
  "meta": { "pagination": { "total": 87, "limit": 50, "offset": 0 } }
}
```

**Errores:** `VALIDATION_ERROR` (422) si el schema no pertenece al tenant, `TENANT_MISMATCH` (403), `UPSTREAM_TIMEOUT` (504) si la query excede el timeout.

---

### 4.2 `POST /database/mutate`

**Request — insert**
```json
{
  "schema": "fortuna",
  "table": "transactions",
  "action": "insert",
  "data": { "amount": 1500, "status": "pending", "user_ref": "usr_01H8X" },
  "returning": ["id", "created_at"]
}
```

**Request — update**
```json
{
  "schema": "fortuna",
  "table": "transactions",
  "action": "update",
  "where": { "id": 42 },
  "data": { "status": "completed" },
  "returning": ["id", "status"]
}
```

**Request — delete**
```json
{
  "schema": "fortuna",
  "table": "transactions",
  "action": "delete",
  "where": { "id": 42 }
}
```

| Campo | Tipo | Oblig. | Notas |
|-------|------|--------|-------|
| `action` | enum | Sí | `insert` \| `update` \| `delete` \| `upsert` |
| `where` | object | Sí en update/delete | Sin `where` en update/delete → `400` |
| `data` | object/array | Sí en insert/update | Array en insert = bulk |
| `returning` | array | No | Campos a devolver |
| `conflict_target` | array | Solo upsert | Columnas para el ON CONFLICT |

**Response `200`**
```json
{
  "success": true,
  "data": {
    "affected_rows": 1,
    "returning": [{ "id": 42, "status": "completed" }],
    "execution_time_ms": 8
  }
}
```

---

### 4.3 `POST /database/transaction`

**Request**
```json
{
  "schema": "fortuna",
  "operations": [
    { "action": "insert", "table": "transactions", "data": { "amount": 500 }, "alias": "tx" },
    { "action": "update", "table": "balances", "where": { "user_ref": "usr_01H8X" }, "data": { "amount": { "decrement": 500 } } }
  ],
  "isolation_level": "read_committed"
}
```

**Response `200`**
```json
{
  "success": true,
  "data": {
    "transaction_id": "txn_01H8X",
    "committed": true,
    "results": [
      { "alias": "tx", "affected_rows": 1, "returning": [{ "id": 99 }] },
      { "affected_rows": 1 }
    ],
    "execution_time_ms": 24
  }
}
```

**Response `422` — rollback**
```json
{
  "success": false,
  "error": {
    "code": "TRANSACTION_ROLLBACK",
    "message": "Transaction rolled back at operation 2",
    "details": [{ "operation_index": 1, "reason": "check constraint violated: balance_non_negative" }]
  }
}
```

---

### 4.4 `GET /database/schemas`
**Response `200`** — `data: [{ "schema": "fortuna", "table_count": 12, "size_bytes": 4194304, "created_at": ... }]`

### 4.5 `POST /database/schemas`
**Request:** `{ "schema": "fortuna_staging" }`
**Response `201`** — `data: { "schema": "fortuna_staging", "created_at": ... }`
**Errores:** `DUPLICATE_RESOURCE` (409), `QUOTA_EXCEEDED` (403) si el tenant alcanzó su límite de schemas.

### 4.6 `GET /database/tables`
**Query:** `schema` (obligatorio)
**Response `200`** — `data: [{ "table": "transactions", "row_count": 8420, "size_bytes": 1048576, "columns": [{ "name": "id", "type": "bigint", "nullable": false }] }]`

---

## 5. Storage — Objetos

Requiere `X-API-Key`+`X-API-Secret` o `Bearer` con permiso `read:storage` / `write:storage`.

### 5.1 `PUT /storage/{bucket}/{key}`

Sube un objeto. `{key}` puede contener `/` (rutas anidadas).

**Headers adicionales**
| Header | Oblig. | Descripción |
|--------|--------|-------------|
| `Content-Type` | Sí | MIME del objeto |
| `Content-Length` | Sí | Bytes |
| `X-Object-Metadata` | No | JSON base64 con metadata libre |
| `If-None-Match` | No | `*` para fallar si ya existe |

**Body:** binario crudo.

**Response `201`**
```json
{
  "success": true,
  "data": {
    "bucket": "fortuna",
    "key": "reports/2026-08/summary.pdf",
    "version_id": "v3",
    "size": 2048576,
    "mime_type": "application/pdf",
    "etag": "33a64df551425fcc55e4d42a148795d9",
    "status": "ACTIVE",
    "created_at": 1692345600
  }
}
```

**Errores:** `PAYLOAD_TOO_LARGE` (413), `QUOTA_EXCEEDED` (403), `DUPLICATE_RESOURCE` (409 con `If-None-Match: *`)

---

### 5.2 `GET /storage/{bucket}/{key}`

**Query:** `versionId` (opcional; default: última versión ACTIVE)
**Headers:** `Range` (soportado para descargas parciales)

**Response `200`** — cuerpo binario. Headers:
```
Content-Type: application/pdf
Content-Length: 2048576
ETag: "33a64df551425fcc55e4d42a148795d9"
X-Version-Id: v3
X-Version-Status: ACTIVE
X-Object-Metadata: eyJhdXRob3IiOiJDYXJsb3MifQ==
```

Si la versión está `ARCHIVED`, se descomprime al vuelo y se añade `X-Decompressed: true`.

**Errores:** `RESOURCE_NOT_FOUND` (404) — incluye versiones `DELETED`.

---

### 5.3 `HEAD /storage/{bucket}/{key}`
Mismos headers que 5.2, sin cuerpo. Útil para verificar existencia y tamaño.

### 5.4 `DELETE /storage/{bucket}/{key}`
**Query:** `versionId` (opcional; sin él borra todas las versiones)
**Response `204`**

### 5.5 `GET /storage/{bucket}`

Lista objetos.

**Query:** `prefix`, `delimiter`, `limit`, `cursor`

**Response `200`**
```json
{
  "success": true,
  "data": {
    "bucket": "fortuna",
    "prefix": "reports/",
    "objects": [
      {
        "key": "reports/2026-08/summary.pdf",
        "size": 2048576,
        "mime_type": "application/pdf",
        "etag": "33a64df551425fcc55e4d42a148795d9",
        "version_count": 3,
        "current_version": "v3",
        "last_modified": 1692345600
      }
    ],
    "common_prefixes": ["reports/2026-07/", "reports/2026-08/"]
  },
  "meta": { "pagination": { "limit": 50, "next_cursor": "eyJrIjoi..." } }
}
```

---

### 5.6 `GET /storage/{bucket}/{key}/versions`

**Response `200`**
```json
{
  "success": true,
  "data": {
    "bucket": "fortuna",
    "key": "reports/2026-08/summary.pdf",
    "versions": [
      { "version_id": "v3", "status": "ACTIVE", "size": 2048576, "compression": null, "is_latest": true, "created_at": 1692345600 },
      { "version_id": "v2", "status": "ACTIVE", "size": 2040000, "compression": null, "is_latest": false, "created_at": 1692259200 },
      { "version_id": "v1", "status": "ACTIVE", "size": 2010000, "compression": null, "is_latest": false, "created_at": 1692172800 }
    ],
    "retention_policy": { "active_versions": 3, "archived_versions": 2, "deleted_after": "v6" }
  }
}
```

---

### 5.7 `POST /storage/{bucket}/{key}/restore`

Promueve una versión anterior a nueva versión ACTIVE.

**Request:** `{ "version_id": "v2" }`
**Response `201`** — nueva versión creada (shape de 5.1).
**Errores:** `VALIDATION_ERROR` (422) si la versión está `DELETED`.

---

### 5.8 Multipart upload

| Método | Endpoint | Request | Response |
|--------|----------|---------|----------|
| POST | `/storage/{bucket}/{key}/multipart` | `{ "mime_type", "total_size" }` | `201` → `{ "upload_id", "part_size", "expires_at" }` |
| PUT | `/storage/{bucket}/{key}/multipart/{upload_id}?part=1` | binario | `200` → `{ "part_number", "etag" }` |
| POST | `/storage/{bucket}/{key}/multipart/{upload_id}/complete` | `{ "parts": [{ "part_number", "etag" }] }` | `201` → objeto completo |
| DELETE | `/storage/{bucket}/{key}/multipart/{upload_id}` | — | `204` (aborta) |

---

### 5.9 Buckets

| Método | Endpoint | Request | Response |
|--------|----------|---------|----------|
| GET | `/storage/buckets` | — | `200` → lista de buckets del tenant |
| PUT | `/storage/buckets/{bucket}` | `{ "versioning": true, "encryption": true, "max_versions": 5 }` | `201` |
| DELETE | `/storage/buckets/{bucket}` | `?force=false` | `204` |
| GET | `/storage/buckets/{bucket}/usage` | — | `200` → uso |

**`GET /storage/buckets/{bucket}/usage` — Response `200`**
```json
{
  "success": true,
  "data": {
    "bucket": "fortuna",
    "object_count": 1420,
    "total_size_bytes": 8589934592,
    "active_size_bytes": 6442450944,
    "archived_size_bytes": 2147483648,
    "quota_bytes": 107374182400,
    "usage_percent": 8.0
  }
}
```

---

### 5.10 `GET /storage/usage`
Uso agregado de todos los buckets del tenant. Mismo shape que 5.9 sin el campo `bucket`, más `buckets: [...]`.

---

## 6. Git — Control de Versiones

Permisos: `read:git` / `write:git` / `admin:git`.

### 6.1 `POST /git/repos`

**Request**
```json
{
  "repo_name": "fortuna-api",
  "description": "Backend de Fortuna",
  "default_branch": "main",
  "visibility": "private",
  "github_mirror_url": "https://github.com/fortuna/api",
  "github_sync_enabled": true,
  "secret_validation_enabled": true
}
```

| Campo | Tipo | Oblig. | Reglas |
|-------|------|--------|--------|
| `repo_name` | string | Sí | `^[a-z0-9][a-z0-9._-]{1,99}$`, único en el tenant |
| `visibility` | enum | No | `private` (default) \| `internal` \| `public` |
| `github_sync_enabled` | bool | No | Requiere `github_mirror_url` y secreto `github_token` en el vault |
| `secret_validation_enabled` | bool | No | Default `true`; rechaza commits con credenciales |

**Response `201`**
```json
{
  "success": true,
  "data": {
    "repo_id": "repo_fortuna_api_01H8X",
    "repo_name": "fortuna-api",
    "tenant_id": "fortuna",
    "clone_url": "https://freya.local/api/v1/git/fortuna/fortuna-api.git",
    "default_branch": "main",
    "visibility": "private",
    "created_at": 1692345600
  }
}
```

---

### 6.2 `POST /git/repos/{repo_id}/push`

**Request**
```json
{
  "branch": "main",
  "commits": [
    {
      "hash": "abc123def4567890abcdef1234567890abcdef12",
      "message": "Add transaction validator",
      "author": { "name": "Carlos Ruiz", "email": "carlos@fortuna.com" },
      "timestamp": 1692345600,
      "files": [
        { "path": "src/validator.js", "action": "modify", "additions": 45, "deletions": 12 }
      ]
    }
  ]
}
```

**Response `200`**
```json
{
  "success": true,
  "data": {
    "repo_id": "repo_fortuna_api_01H8X",
    "branch": "main",
    "commits_received": 1,
    "stored_locally": 1,
    "total_local_commits": 5,
    "pushed_to_github": 1,
    "secret_validation": "passed",
    "head": "abc123def4567890abcdef1234567890abcdef12"
  }
}
```

**Response `422` — commit rechazado por secretos**
```json
{
  "success": false,
  "error": {
    "code": "SECRET_DETECTED",
    "message": "Commit rejected: hardcoded credentials detected",
    "details": [
      { "file": "src/config.js", "line": 12, "pattern": "api_key_assignment", "suggestion": "Store in vault and reference via secrets API" },
      { "file": ".env", "line": null, "pattern": "forbidden_file", "suggestion": "Remove .env; use the secrets service" }
    ]
  }
}
```

---

### 6.3 `GET /git/repos/{repo_id}/commits`

**Query:** `branch`, `limit`, `cursor`, `author`, `since`, `until`

**Response `200`**
```json
{
  "success": true,
  "data": [
    {
      "hash": "abc123def4567890abcdef1234567890abcdef12",
      "short_hash": "abc123d",
      "message": "Add transaction validator",
      "author": { "name": "Carlos Ruiz", "email": "carlos@fortuna.com" },
      "timestamp": 1692345600,
      "branch": "main",
      "storage_location": "local",
      "stats": { "additions": 45, "deletions": 12, "files_changed": 1 },
      "linked_task_id": "tsk_01H8X"
    },
    {
      "hash": "999888777666555444333222111000aaabbbcccd",
      "short_hash": "9998887",
      "message": "Initial commit",
      "author": { "name": "Carlos Ruiz", "email": "carlos@fortuna.com" },
      "timestamp": 1691000000,
      "storage_location": "github",
      "note": "Older commit fetched from GitHub mirror"
    }
  ],
  "meta": { "pagination": { "limit": 50, "next_cursor": "eyJoIjoi..." } }
}
```

---

### 6.4 Branches y Tags

| Método | Endpoint | Request | Response |
|--------|----------|---------|----------|
| GET | `/git/repos/{repo_id}/branches` | — | `200` → `[{ "name", "head_commit", "is_default", "protected", "created_at" }]` |
| POST | `/git/repos/{repo_id}/branches` | `{ "name", "from_commit" }` | `201` |
| DELETE | `/git/repos/{repo_id}/branches/{branch}` | — | `204` |
| GET | `/git/repos/{repo_id}/tags` | `?limit` | `200` → `[{ "name", "target_commit", "message", "tagger", "created_at" }]` |
| POST | `/git/repos/{repo_id}/tags` | `{ "name", "target_commit", "message" }` | `201` |
| DELETE | `/git/repos/{repo_id}/tags/{tag}` | — | `204` |

**Regla de deployabilidad:** solo commits con tag son desplegables. `name` de tag debe seguir semver: `^v\d+\.\d+\.\d+(-[a-z0-9.]+)?$`.

---

### 6.5 `GET /git/repos/{repo_id}/previous-tag/{tag}`

Devuelve el tag inmediatamente anterior. Es la primitiva del rollback automático.

**Response `200`**
```json
{
  "success": true,
  "data": {
    "current_tag": "v2.1.0",
    "previous_tag": "v2.0.8",
    "previous_commit": "def456abc7890123456789abcdef0123456789ab",
    "artifact_available": true,
    "artifact_path": "fortuna/ci-cd/artifacts/fortuna-api-v2.0.8.tar.gz"
  }
}
```

**Errores:** `RESOURCE_NOT_FOUND` (404) si no hay tag anterior (primer release).

---

### 6.6 `GET /git/repos/{repo_id}/diff`

**Query:** `base` (commit/tag/branch), `head` (commit/tag/branch), `path` (opcional)

**Response `200`**
```json
{
  "success": true,
  "data": {
    "base": "v2.0.8",
    "head": "v2.1.0",
    "commits_ahead": 7,
    "stats": { "additions": 312, "deletions": 89, "files_changed": 14 },
    "files": [
      { "path": "src/validator.js", "status": "modified", "additions": 45, "deletions": 12, "patch": "@@ -10,7 +10,40 @@..." }
    ]
  }
}
```

---

### 6.7 `GET /git/repos/{repo_id}/blame/{file}`

**Query:** `ref` (branch/commit, default: default branch)

**Response `200`**
```json
{
  "success": true,
  "data": {
    "file": "src/validator.js",
    "ref": "main",
    "lines": [
      { "line_number": 1, "content": "const validate = (tx) => {", "commit": "abc123d", "author": "Carlos Ruiz", "timestamp": 1692345600 }
    ]
  }
}
```

---

### 6.8 `GET /git/repos/{repo_id}/deployment-history`

**Response `200`**
```json
{
  "success": true,
  "data": [
    {
      "deployment_id": "dep_01H8X",
      "version_tag": "v2.1.0",
      "commit": "abc123def4567890abcdef1234567890abcdef12",
      "status": "rolled_back",
      "health_check_result": "unhealthy",
      "rolled_back_to": "v2.0.8",
      "rollback_attempts": 1,
      "deployed_at": 1692345600,
      "rollback_completed_at": 1692345900
    },
    {
      "deployment_id": "dep_01H7W",
      "version_tag": "v2.0.8",
      "commit": "def456abc7890123456789abcdef0123456789ab",
      "status": "successful",
      "health_check_result": "healthy",
      "deployed_at": 1692259200
    }
  ]
}
```

---

### 6.9 `POST /git/repos/{repo_id}/validate-secrets`

Dry-run de la validación anti-secretos, sin hacer push.

**Request:** `{ "files": [{ "path": "src/config.js", "content": "..." }] }`
**Response `200`** — `{ "validation_result": "passed" | "rejected", "files_scanned": 2, "issues": [] }`

---

## 7. Project Manager — Proyectos y Tareas

### 7.1 `POST /projects`

**Request**
```json
{
  "project_name": "Fortuna",
  "description": "Financial management platform",
  "project_type": "programming",
  "visibility": "private",
  "team_members": ["usr_01H8X", "usr_01H9A"],
  "linked_git_repo": "repo_fortuna_api_01H8X",
  "ci_cd_enabled": true,
  "freya_access_enabled": true
}
```

| Campo | Tipo | Oblig. | Reglas |
|-------|------|--------|--------|
| `project_type` | enum | Sí | `programming` \| `electronics` \| `general` |
| `linked_git_repo` | string | No | Solo si type ≠ `general` |
| `ci_cd_enabled` | bool | No | Solo `true` si type = `programming` |
| `freya_access_enabled` | bool | No | Si `true`, crea tenant y devuelve credenciales |

**Response `201`**
```json
{
  "success": true,
  "data": {
    "project_id": "prj_fortuna_01H8X",
    "project_name": "Fortuna",
    "project_type": "programming",
    "git_repo": "repo_fortuna_api_01H8X",
    "ci_cd_enabled": true,
    "freya_access": {
      "enabled": true,
      "tenant_id": "fortuna",
      "api_key": "sk_fortuna_service_01H8XABCDEF",
      "api_secret": "sec_9f2a8c1b4d7e6f3a0b5c8d1e4f7a2b9c",
      "secret_vault_path": "/secret/fortuna/service_api_secret",
      "notice": "api_secret is returned only once. Store api_key in your .env; the secret is retrievable from the vault using the api_key."
    },
    "created_at": 1692345600
  }
}
```

**Errores:** `VALIDATION_ERROR` (422) si `ci_cd_enabled: true` con type ≠ `programming`; `DUPLICATE_RESOURCE` (409) si el `tenant_id` derivado ya existe.

---

### 7.2 `POST /projects/{project_id}/tasks`

**Request**
```json
{
  "title": "Implement transaction validator",
  "description": "Add server-side validation for incoming transactions",
  "status": "backlog",
  "priority": "high",
  "story_points": 8,
  "estimated_hours": 5,
  "assigned_to": "usr_01H8X",
  "sprint_id": "spr_01H8X",
  "labels": ["backend", "validation"],
  "start_date": "2026-08-22",
  "due_date": "2026-08-25",
  "sync_to_icloud": true
}
```

| Campo | Tipo | Oblig. | Valores |
|-------|------|--------|---------|
| `status` | enum | No | `backlog` (default) \| `todo` \| `in_progress` \| `testing` \| `done` |
| `priority` | enum | No | `low` \| `medium` (default) \| `high` \| `critical` |
| `story_points` | int | No | 1, 2, 3, 5, 8, 13, 21 (Fibonacci) |
| `sync_to_icloud` | bool | No | Requiere `due_date` e integración iCloud activa |

**Response `201`**
```json
{
  "success": true,
  "data": {
    "task_id": "tsk_01H8X",
    "project_id": "prj_fortuna_01H8X",
    "title": "Implement transaction validator",
    "status": "backlog",
    "priority": "high",
    "story_points": 8,
    "assigned_to": "usr_01H8X",
    "due_date": "2026-08-25",
    "icloud_sync": { "status": "synced", "event_id": "evt_apple_01H8X", "calendar": "Work" },
    "created_at": 1692345600
  }
}
```

---

### 7.3 `PUT /tasks/{task_id}`

Todos los campos son opcionales. Cambiar `status` a `done` dispara el cálculo de XP en gamification y el evento `task.completed` en webhooks.

**Request:** `{ "status": "done", "actual_hours": 4 }`

**Response `200`**
```json
{
  "success": true,
  "data": {
    "task_id": "tsk_01H8X",
    "status": "done",
    "actual_hours": 4,
    "completed_at": 1692432000,
    "completed_by": "usr_01H8X",
    "gamification": {
      "xp_awarded": 253,
      "coins_awarded": 72,
      "breakdown": {
        "base_xp": 100,
        "story_points_multiplier": 1.6,
        "on_time_bonus": 1.25,
        "quality_bonus": 1.15,
        "team_bonus": 1.10
      },
      "new_total_xp": 8793,
      "new_level": 18,
      "quests_progressed": ["h_productive_day"]
    },
    "events_emitted": ["task.completed"]
  }
}
```

---

### 7.4 `POST /tasks/{task_id}/link-commit`

**Request:** `{ "repo_id": "repo_fortuna_api_01H8X", "commit_hash": "abc123def..." }`
**Response `201`** — `{ "task_id", "repo_id", "commit_hash", "linked_at" }`

> Alternativa automática: si el mensaje del commit contiene `#tsk_01H8X` o `Task #123`, el vínculo se crea solo al recibir el push.

---

### 7.5 `GET /projects/{project_id}/kanban`

**Response `200`**
```json
{
  "success": true,
  "data": {
    "project_id": "prj_fortuna_01H8X",
    "sprint_id": "spr_01H8X",
    "columns": [
      {
        "status": "backlog",
        "task_count": 12,
        "tasks": [
          { "task_id": "tsk_01H8X", "title": "...", "priority": "high", "story_points": 8, "assigned_to": "usr_01H8X", "due_date": "2026-08-25" }
        ]
      },
      { "status": "todo", "task_count": 5, "tasks": [] },
      { "status": "in_progress", "task_count": 3, "tasks": [] },
      { "status": "testing", "task_count": 2, "tasks": [] },
      { "status": "done", "task_count": 45, "tasks": [] }
    ]
  }
}
```

---

### 7.6 Sprints

| Método | Endpoint | Request | Response |
|--------|----------|---------|----------|
| POST | `/projects/{id}/sprints` | `{ "name", "goal", "start_date", "end_date", "task_ids" }` | `201` |
| GET | `/projects/{id}/sprints` | `?status=active` | `200` → lista |
| GET | `/projects/{id}/sprints/{sprint_id}` | — | `200` → sprint + burndown |
| PUT | `/projects/{id}/sprints/{sprint_id}` | `{ "status": "completed" }` | `200` |

**`GET /projects/{id}/sprints/{sprint_id}` — Response `200`**
```json
{
  "success": true,
  "data": {
    "sprint_id": "spr_01H8X",
    "name": "Sprint 5: Validation Layer",
    "goal": "Ship server-side validation",
    "status": "active",
    "start_date": "2026-08-18",
    "end_date": "2026-09-01",
    "metrics": {
      "total_story_points": 34,
      "completed_story_points": 15,
      "completion_percent": 44.1,
      "tasks_total": 12,
      "tasks_done": 5,
      "velocity_estimate": 12.0,
      "days_remaining": 12
    },
    "burndown": [
      { "date": "2026-08-18", "remaining_points": 34 },
      { "date": "2026-08-19", "remaining_points": 29 },
      { "date": "2026-08-20", "remaining_points": 19 }
    ]
  }
}
```

---

### 7.7 `GET /projects/{project_id}/dashboard`

**Response `200`** — la forma varía según `project_type`:

**Type `programming`:**
```json
{
  "success": true,
  "data": {
    "project_id": "prj_fortuna_01H8X",
    "project_type": "programming",
    "current_sprint": { "sprint_id": "spr_01H8X", "name": "Sprint 5", "completion_percent": 44.1 },
    "git": { "repo_id": "repo_fortuna_api_01H8X", "latest_commit": "abc123d", "commits_this_week": 23 },
    "ci_cd": {
      "latest_build": { "build_id": "bld_01H8X", "status": "success", "duration_seconds": 525 },
      "latest_deployment": { "version": "v2.0.8", "status": "healthy", "deployed_at": 1692259200 },
      "success_rate_30d": 94.2
    },
    "recent_activity": [
      { "type": "task_completed", "actor": "usr_01H8X", "ref": "tsk_01H8X", "timestamp": 1692432000 }
    ]
  }
}
```

**Type `electronics`:** reemplaza `ci_cd` por `designs: [{ design_id, type, version, uploaded_by, storage_path, uploaded_at }]`.

**Type `general`:** omite `git`, `ci_cd` y `designs`; incluye `kanban_summary` y `team_stats`.

---

### 7.8 Diseños (solo `project_type: electronics`)

| Método | Endpoint | Request | Response |
|--------|----------|---------|----------|
| POST | `/projects/{id}/designs` | multipart: `file`, `design_type`, `version`, `description` | `201` |
| GET | `/projects/{id}/designs` | `?design_type=schematic` | `200` → lista |
| GET | `/projects/{id}/designs/{design_id}/versions` | — | `200` → versiones |

`design_type`: `schematic` \| `pcb_layout` \| `bom` \| `datasheet` \| `render` \| `gerber`

**Response `201`**
```json
{
  "success": true,
  "data": {
    "design_id": "dsg_01H8X",
    "design_type": "schematic",
    "version": "1.0",
    "storage_bucket": "fortuna",
    "storage_key": "designs/schematic/v1.0/main.kicad_sch",
    "git_tag": "design/schematic/v1.0",
    "size": 524288,
    "uploaded_at": 1692345600
  }
}
```

---

### 7.9 Integración iCloud

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| POST | `/projects/{id}/integrations/icloud/connect` | Devuelve `auth_url` de OAuth2 |
| GET | `/projects/{id}/integrations/icloud/callback` | Callback (`?code=`); intercambia por refresh token → vault |
| GET | `/projects/{id}/integrations/icloud/calendars` | Lista calendarios disponibles |
| POST | `/projects/{id}/integrations/icloud/calendar-mapping` | Mapea calendario ↔ proyecto |
| DELETE | `/projects/{id}/integrations/icloud/disconnect` | Revoca acceso y borra token |
| POST | `/projects/{id}/integrations/icloud/sync` | Fuerza sync manual |
| GET | `/projects/{id}/integrations/icloud/sync-logs` | Historial de sincronizaciones |

**`POST .../calendar-mapping` — Request**
```json
{
  "icloud_calendar_id": "work",
  "direction": "bidirectional",
  "auto_create_tasks": true
}
```
`direction`: `import` \| `export` \| `bidirectional`

**`GET .../sync-logs` — Response `200`**
```json
{
  "success": true,
  "data": [
    {
      "sync_id": "syn_01H8X",
      "action": "create_event",
      "source": "project_manager",
      "task_id": "tsk_01H8X",
      "icloud_event_id": "evt_apple_01H8X",
      "status": "success",
      "timestamp": 1692345600
    },
    {
      "sync_id": "syn_01H8Y",
      "action": "update_event",
      "source": "icloud",
      "status": "conflict_resolved",
      "resolution": "latest_timestamp_wins",
      "winner": "project_manager",
      "timestamp": 1692345900
    }
  ]
}
```

---

### 7.10 Gestión de acceso a Freya

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/projects/{id}/freya-access` | Estado del acceso |
| POST | `/projects/{id}/freya-access` | Activar (crea tenant + credenciales) |
| DELETE | `/projects/{id}/freya-access` | Desactivar (invalida credenciales) |
| POST | `/projects/{id}/freya-access/regenerate` | Rotar api_key + api_secret |

**`GET` — Response `200`**
```json
{
  "success": true,
  "data": {
    "enabled": true,
    "tenant_id": "fortuna",
    "api_key": "sk_fortuna_service_01H8XABCDEF",
    "secret_vault_path": "/secret/fortuna/service_api_secret",
    "permissions": ["read:database", "write:database", "read:storage", "write:storage", "write:git", "manage:ci-cd"],
    "activated_at": 1692345600,
    "last_api_call": 1692432000,
    "calls_last_24h": 4218
  }
}
```

**`POST .../regenerate` — Response `200`**
```json
{
  "success": true,
  "data": {
    "api_key": "sk_fortuna_service_01H9BNEWKEY",
    "api_secret": "sec_new1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c",
    "previous_key_valid_until": 1692518400,
    "notice": "Previous credentials remain valid for 24h to allow rotation without downtime."
  }
}
```

---

## 8. CI/CD — Pipelines

### 8.1 `POST /ci-cd/pipelines`

**Request**
```json
{
  "pipeline_name": "fortuna-api",
  "repo_id": "repo_fortuna_api_01H8X",
  "project_id": "prj_fortuna_01H8X",
  "config_path": ".freya/pipeline.yaml",
  "trigger": {
    "type": "webhook",
    "events": ["push", "tag"],
    "branches": ["main"],
    "tag_pattern": "v*"
  },
  "rollback": {
    "enabled": true,
    "health_check_url": "/health",
    "health_check_timeout_seconds": 10,
    "wait_before_check_seconds": 30,
    "max_retries": 3,
    "retry_interval_seconds": 300
  }
}
```

**Response `201`**
```json
{
  "success": true,
  "data": {
    "pipeline_id": "pip_fortuna_api_01H8X",
    "pipeline_name": "fortuna-api",
    "webhook_url": "https://freya.local/api/v1/ci-cd/webhook/pip_fortuna_api_01H8X",
    "webhook_secret": "whsec_1a2b3c4d5e6f7a8b",
    "created_at": 1692345600
  }
}
```

---

### 8.2 `POST /ci-cd/pipelines/{pipeline_id}/trigger`

**Request:** `{ "branch": "main", "commit": "abc123d", "variables": { "SKIP_TESTS": "false" } }`

**Response `202`**
```json
{
  "success": true,
  "data": {
    "build_id": "bld_01H8X",
    "pipeline_id": "pip_fortuna_api_01H8X",
    "status": "queued",
    "queue_position": 2,
    "triggered_by": "usr_01H8X",
    "trigger_type": "manual",
    "created_at": 1692345600
  }
}
```

---

### 8.3 `GET /ci-cd/builds/{build_id}`

**Response `200`**
```json
{
  "success": true,
  "data": {
    "build_id": "bld_01H8X",
    "pipeline_id": "pip_fortuna_api_01H8X",
    "status": "running",
    "commit": "abc123def4567890abcdef1234567890abcdef12",
    "branch": "main",
    "version_tag": null,
    "triggered_by": "webhook",
    "progress_percent": 55,
    "current_stage": "Build",
    "started_at": 1692345600,
    "completed_at": null,
    "duration_seconds": 62,
    "stages": [
      {
        "name": "Test",
        "status": "success",
        "duration_seconds": 45,
        "steps": [
          { "name": "Lint", "status": "success", "duration_seconds": 12, "exit_code": 0 },
          { "name": "Unit Tests", "status": "success", "duration_seconds": 28, "exit_code": 0 },
          { "name": "Coverage", "status": "success", "duration_seconds": 5, "exit_code": 0 }
        ]
      },
      {
        "name": "Build",
        "status": "running",
        "duration_seconds": 17,
        "steps": [
          { "name": "Build App", "status": "success", "duration_seconds": 8, "exit_code": 0 },
          { "name": "Build Docker", "status": "running", "duration_seconds": 9, "exit_code": null },
          { "name": "Push Artifact", "status": "pending", "duration_seconds": null, "exit_code": null }
        ]
      },
      { "name": "Deploy", "status": "pending", "steps": [] },
      { "name": "Health Check", "status": "pending", "steps": [] }
    ]
  }
}
```

**Estados de build:** `queued` \| `running` \| `success` \| `failed` \| `cancelled` \| `timeout` \| `rolled_back`

---

### 8.4 `GET /ci-cd/builds/{build_id}/logs`

**Query:** `stage`, `step`, `since` (timestamp), `follow` (bool — abre SSE)

**Response `200`** (modo normal)
```json
{
  "success": true,
  "data": {
    "build_id": "bld_01H8X",
    "storage_key": "fortuna/ci-cd/logs/bld_01H8X.log",
    "lines": [
      { "timestamp": 1692345600, "level": "info", "stage": "Test", "step": "Lint", "message": "Linting 142 files" },
      { "timestamp": 1692345612, "level": "info", "stage": "Test", "step": "Lint", "message": "Lint passed" },
      { "timestamp": 1692345640, "level": "error", "stage": "Deploy", "step": "Health Check", "message": "Timeout after 10s" }
    ],
    "truncated": false
  }
}
```

**Response `200`** con `follow=true`: `Content-Type: text/event-stream`, cada evento es una línea del log en JSON.

---

### 8.5 Build fallido con rollback

**`GET /ci-cd/builds/{build_id}` — Response `200`**
```json
{
  "success": true,
  "data": {
    "build_id": "bld_01H9Z",
    "status": "rolled_back",
    "version_tag": "v2.1.0",
    "failure": {
      "stage": "Health Check",
      "step": "GET /health",
      "reason": "HEALTH_CHECK_TIMEOUT",
      "message": "Service did not respond within 10s"
    },
    "rollback": {
      "status": "success",
      "rolled_back_from": "v2.1.0",
      "rolled_back_to": "v2.0.8",
      "attempts": 1,
      "triggered_at": 1692345900,
      "completed_at": 1692345940,
      "post_rollback_health": "healthy"
    },
    "events_emitted": ["build.failed", "rollback.triggered", "deployment.completed"]
  }
}
```

---

### 8.6 Otros endpoints CI/CD

| Método | Endpoint | Request | Response |
|--------|----------|---------|----------|
| GET | `/ci-cd/pipelines` | `?project_id&limit` | `200` → lista |
| PUT | `/ci-cd/pipelines/{id}` | config parcial | `200` |
| DELETE | `/ci-cd/pipelines/{id}` | — | `204` |
| GET | `/ci-cd/builds` | `?pipeline_id&status&limit&cursor` | `200` → lista |
| GET | `/ci-cd/builds/{id}/artifacts` | — | `200` → artifacts |
| POST | `/ci-cd/builds/{id}/cancel` | — | `200` → `{ "status": "cancelled" }` |
| POST | `/ci-cd/builds/{id}/rollback` | `{ "to_version": "v2.0.8" }` | `202` |
| POST | `/ci-cd/webhook/{pipeline_id}` | payload de git + `X-Webhook-Signature` | `202` |

**`GET /ci-cd/builds/{id}/artifacts` — Response `200`**
```json
{
  "success": true,
  "data": [
    {
      "artifact_id": "art_01H8X",
      "name": "fortuna-api:v2.1.0",
      "type": "docker_image",
      "storage_bucket": "fortuna",
      "storage_key": "ci-cd/artifacts/fortuna-api-v2.1.0.tar.gz",
      "size_bytes": 15728640,
      "checksum": "sha256:a1b2c3...",
      "expires_at": 1700121600,
      "created_at": 1692345600
    }
  ]
}
```

---

## 9. Secrets — Vault

Permisos: `read:secrets` / `write:secrets`. Un tenant solo accede a su propio namespace.

### 9.1 `GET /secrets/{namespace}/{key}`

**Response `200`**
```json
{
  "success": true,
  "data": {
    "namespace": "fortuna",
    "key": "github_token",
    "value": "ghp_xxxxxxxxxxxxxxxxxxxx",
    "type": "api_key",
    "version": 3,
    "created_at": 1692345600,
    "updated_at": 1692432000,
    "expires_at": 1724000000,
    "rotated_at": 1692432000
  }
}
```

**Query opcional:** `version` (int) para leer una versión anterior; `metadata_only=true` para omitir `value`.

**Errores:** `RESOURCE_NOT_FOUND` (404), `TENANT_MISMATCH` (403) si el namespace no es del tenant.

---

### 9.2 `POST /secrets/{namespace}`

**Request**
```json
{
  "key": "stripe_secret_key",
  "value": "sk_live_xxxxxxxxxxxxx",
  "type": "api_key",
  "expires_at": 1755000000,
  "description": "Stripe production key",
  "overwrite": false
}
```

`type`: `rsa_private` \| `rsa_public` \| `api_key` \| `db_credentials` \| `certificate` \| `token` \| `generic`

**Response `201`**
```json
{
  "success": true,
  "data": {
    "namespace": "fortuna",
    "key": "stripe_secret_key",
    "type": "api_key",
    "version": 1,
    "created_at": 1692345600,
    "expires_at": 1755000000
  }
}
```

> El `value` nunca se devuelve en respuestas de escritura.

**Errores:** `DUPLICATE_RESOURCE` (409) si existe y `overwrite: false`.

---

### 9.3 `GET /secrets/{namespace}`

Lista claves sin valores.

**Response `200`**
```json
{
  "success": true,
  "data": [
    { "key": "github_token", "type": "api_key", "version": 3, "created_at": 1692345600, "expires_at": 1724000000, "expiring_soon": false },
    { "key": "db_password", "type": "db_credentials", "version": 1, "created_at": 1692345600, "expires_at": null, "expiring_soon": false }
  ],
  "meta": { "pagination": { "total": 2, "limit": 50, "offset": 0 } }
}
```

---

### 9.4 Otros endpoints Secrets

| Método | Endpoint | Request | Response |
|--------|----------|---------|----------|
| PUT | `/secrets/{ns}/{key}` | `{ "value", "expires_at" }` | `200` → nueva versión |
| DELETE | `/secrets/{ns}/{key}` | `?version=` (opcional) | `204` |
| POST | `/secrets/{ns}/{key}/rotate` | `{ "new_value" }` | `200` → `{ "version", "previous_version_valid_until" }` |
| GET | `/secrets/{ns}/{key}/versions` | — | `200` → historial (sin valores) |
| GET | `/secrets/{ns}/audit-logs` | `?limit&action` | `200` → accesos |

**`POST .../rotate` — Response `200`**
```json
{
  "success": true,
  "data": {
    "namespace": "fortuna",
    "key": "github_token",
    "version": 4,
    "previous_version": 3,
    "previous_version_valid_until": 1692518400,
    "rotated_at": 1692432000
  }
}
```

---

## 10. Gamification

### 10.1 `GET /gamification/profile/{user_id}`

**Response `200`**
```json
{
  "success": true,
  "data": {
    "user_id": "usr_01H8X",
    "username": "carlos",
    "level": 18,
    "total_xp": 8793,
    "xp_to_next_level": 1207,
    "coins": 522,
    "total_coins_earned": 1874,
    "current_streak": 24,
    "max_streak": 45,
    "rank": 3,
    "achievements_count": 8,
    "avatar_url": "https://freya.local/api/v1/storage/usr_01H8X/avatar.jpg",
    "bio": "Backend developer",
    "joined_at": 1687000000
  }
}
```

---

### 10.2 `POST /gamification/xp-transaction`

Endpoint interno: solo `project-manager` (service account) puede llamarlo.

**Request**
```json
{
  "user_id": "usr_01H8X",
  "event_type": "task_completed",
  "source_id": "tsk_01H8X",
  "context": {
    "priority": "high",
    "story_points": 8,
    "on_time": true,
    "has_linked_commit": true,
    "is_team_task": true,
    "project_id": "prj_fortuna_01H8X"
  }
}
```

**Response `200`**
```json
{
  "success": true,
  "data": {
    "user_id": "usr_01H8X",
    "xp_awarded": 253,
    "coins_awarded": 72,
    "breakdown": {
      "base_xp": 100,
      "story_points_multiplier": 1.6,
      "on_time_bonus": 1.25,
      "quality_bonus": 1.15,
      "team_bonus": 1.10,
      "final_xp": 253
    },
    "new_total_xp": 8793,
    "level_before": 18,
    "level_after": 18,
    "leveled_up": false,
    "quests_progressed": [
      { "quest_id": "q_productive_day", "progress": 3, "target": 3, "completed": true, "reward_pending": true }
    ],
    "achievements_unlocked": [],
    "streak": 24
  }
}
```

**Errores:** `INSUFFICIENT_PERMISSIONS` (403) si el llamante no es `project-manager`.

---

### 10.3 `GET /gamification/quests/{type}`

`type`: `daily` \| `weekly` \| `monthly` \| `annual`

**Response `200`**
```json
{
  "success": true,
  "data": {
    "quest_type": "daily",
    "cycle_start": "2026-08-20T00:00:00Z",
    "cycle_end": "2026-08-21T00:00:00Z",
    "quests": [
      {
        "quest_id": "h_early_riser",
        "name": "Early Riser",
        "category": "sleep",
        "objective": "Wake up before 7:00 AM",
        "objective_value": 1,
        "objective_unit": "occurrence",
        "progress": 1,
        "status": "completed",
        "xp_reward": 20,
        "coins_reward": 8,
        "streak": 12,
        "streak_bonus_xp": 15,
        "total_reward_xp": 35,
        "claimed": false
      },
      {
        "quest_id": "h_fitness",
        "name": "Fitness Warrior",
        "category": "fitness",
        "objective": "Exercise 30+ minutes",
        "objective_value": 30,
        "objective_unit": "minutes",
        "progress": 15,
        "status": "in_progress",
        "xp_reward": 35,
        "coins_reward": 12,
        "streak": 5,
        "claimed": false
      }
    ],
    "summary": { "completed": 3, "in_progress": 2, "not_started": 4, "xp_earned_today": 75, "coins_earned_today": 25 }
  }
}
```

---

### 10.4 `POST /gamification/habits/log`

**Request**
```json
{
  "habit": "fitness",
  "value": 45,
  "unit": "minutes",
  "source": "manual",
  "occurred_at": 1692345600,
  "notes": "Morning run + yoga"
}
```

`habit`: `early_riser` \| `fitness` \| `hydration` \| `meditation` \| `reading` \| `learning` \| `sleep` \| `healthy_eating` \| `digital_detox`
`source`: `manual` \| `apple_health` \| `google_fit` \| `strava` \| `sleep_cycle`

**Response `200`**
```json
{
  "success": true,
  "data": {
    "log_id": "hbl_01H8X",
    "habit": "fitness",
    "value": 45,
    "unit": "minutes",
    "quests_affected": [
      { "quest_id": "h_fitness", "quest_type": "daily", "progress": 45, "target": 30, "completed": true },
      { "quest_id": "h_weekly_athlete", "quest_type": "weekly", "progress": 5, "target": 5, "completed": true }
    ],
    "xp_awarded": 185,
    "coins_awarded": 52,
    "streak": 6,
    "logged_at": 1692345600
  }
}
```

**Errores:** `DUPLICATE_RESOURCE` (409) si ya se registró ese hábito en el ciclo y no acumula.

---

### 10.5 `POST /gamification/quests/{quest_id}/claim`

**Response `200`**
```json
{
  "success": true,
  "data": {
    "quest_id": "h_early_riser",
    "xp_awarded": 35,
    "coins_awarded": 8,
    "new_total_xp": 8828,
    "new_coins": 530,
    "leveled_up": false,
    "claimed_at": 1692345600
  }
}
```

**Errores:** `VALIDATION_ERROR` (422) si la quest no está completada; `DUPLICATE_RESOURCE` (409) si ya se reclamó.

---

### 10.6 `GET /gamification/leaderboard`

**Query:** `scope` (`global` \| `tenant` \| `project`), `period` (`all_time` \| `monthly` \| `weekly`), `limit`

**Response `200`**
```json
{
  "success": true,
  "data": {
    "scope": "tenant",
    "period": "monthly",
    "entries": [
      { "rank": 1, "user_id": "usr_01H5A", "username": "ana", "level": 45, "xp": 98500, "coins": 2340, "streak": 156, "achievements": 28, "title": "Legendary" },
      { "rank": 2, "user_id": "usr_01H6B", "username": "luis", "level": 42, "xp": 87200, "coins": 1890, "streak": 89, "achievements": 24, "title": null },
      { "rank": 3, "user_id": "usr_01H8X", "username": "carlos", "level": 18, "xp": 8793, "coins": 522, "streak": 24, "achievements": 8, "title": null }
    ],
    "current_user": { "rank": 3, "xp": 8793 }
  }
}
```

---

### 10.7 Tienda

| Método | Endpoint | Request | Response |
|--------|----------|---------|----------|
| GET | `/gamification/shop/items` | `?category&tier&max_coins&available_only` | `200` → catálogo |
| GET | `/gamification/shop/items/{item_id}` | — | `200` → detalle + reseñas |
| POST | `/gamification/shop/purchase/{item_id}` | `{ "quantity": 1 }` | `201` → compra |
| GET | `/gamification/shop/purchases` | `?status&limit` | `200` → historial |
| POST | `/gamification/shop/redeem/{purchase_id}` | — | `200` → instrucciones |
| POST | `/gamification/shop/verify-code` | `{ "code" }` | `200` → validez (para partners) |
| GET | `/gamification/inventory` | `?status=active` | `200` → ítems activos |
| POST | `/gamification/shop/items/{id}/review` | `{ "rating", "review_text" }` | `201` |
| GET | `/gamification/shop/trending` | `?period=monthly` | `200` → top ítems |

**`GET /gamification/shop/items` — Response `200`**
```json
{
  "success": true,
  "data": [
    {
      "item_id": "itm_movie_night",
      "name": "Movie Night",
      "category": "entertainment",
      "tier": 2,
      "description": "Entrada de cine para cualquier película",
      "cost_coins": 120,
      "benefit": "1 entrada de cine",
      "delivery_method": "code",
      "validity_days": 30,
      "stock": { "type": "unlimited", "available": null },
      "rating": 4.7,
      "review_count": 124,
      "affordable": true
    },
    {
      "item_id": "itm_intl_trip",
      "name": "International Trip",
      "category": "experience",
      "tier": 4,
      "description": "Viaje de 5 días (vuelo + hotel 4*)",
      "cost_coins": 1200,
      "delivery_method": "coordination",
      "validity_days": 180,
      "stock": { "type": "limited", "available": 2, "resets": "monthly" },
      "rating": 5.0,
      "review_count": 3,
      "affordable": false,
      "requires_approval": true
    }
  ],
  "meta": { "user_coins": 522, "pagination": { "total": 27, "limit": 50, "offset": 0 } }
}
```

**`POST /gamification/shop/purchase/{item_id}` — Response `201`**
```json
{
  "success": true,
  "data": {
    "purchase_id": "pur_01H8X",
    "item_id": "itm_movie_night",
    "item_name": "Movie Night",
    "cost_coins": 120,
    "coins_before": 522,
    "coins_after": 402,
    "status": "completed",
    "redemption_code": "MOVIE-NIGHT-A7X92K",
    "delivery_method": "code",
    "expires_at": 1694937600,
    "purchased_at": 1692345600,
    "redemption_instructions": "Presenta este código en cualquier cine participante"
  }
}
```

**Errores:** `QUOTA_EXCEEDED` (403) con `code: INSUFFICIENT_COINS`; `RESOURCE_NOT_FOUND` (404) si sin stock.

**`POST /gamification/shop/verify-code` — Response `200`** (endpoint para partners, auth por API key de partner)
```json
{
  "success": true,
  "data": {
    "valid": true,
    "item_name": "Movie Night",
    "benefit": "1 entrada de cine",
    "expires_at": 1694937600,
    "already_redeemed": false,
    "marked_redeemed_at": 1692500000
  }
}
```

---

### 10.8 Otros endpoints Gamification

| Método | Endpoint | Response |
|--------|----------|----------|
| GET | `/gamification/profile/{user_id}/stats` | Desglose de XP por fuente, actividad por día |
| GET | `/gamification/transactions/{user_id}` | Historial de XP/coins con `breakdown` |
| GET | `/gamification/achievements` | Logros del usuario + catálogo con progreso |
| GET | `/gamification/habits/progress` | Progreso agregado de hábitos |
| GET | `/gamification/habits/streaks` | Rachas por hábito |
| GET | `/gamification/showcase` | Vitrina de proyectos destacados |

---

## 11. Monitoring

### 11.1 `GET /monitoring/services`

**Response `200`**
```json
{
  "success": true,
  "data": {
    "overall_status": "degraded",
    "services": [
      {
        "service": "traefik",
        "status": "healthy",
        "uptime_percent_24h": 99.97,
        "response_time_ms": 12,
        "error_rate_percent": 0.02,
        "last_check": 1692345600,
        "sla_status": "met"
      },
      {
        "service": "storage",
        "status": "degraded",
        "uptime_percent_24h": 99.5,
        "response_time_ms": 156,
        "error_rate_percent": 0.8,
        "active_alerts": 1,
        "last_check": 1692345600,
        "sla_status": "at_risk"
      }
    ],
    "summary": { "total": 14, "healthy": 12, "degraded": 1, "down": 0, "unknown": 1 }
  }
}
```

**Estados:** `healthy` \| `degraded` \| `down` \| `unknown`

---

### 11.2 `GET /monitoring/metrics/{service}`

**Query:** `metric` (nombre), `from`, `to` (timestamps), `resolution` (`1m` \| `5m` \| `1h` \| `1d`), `aggregation` (`avg` \| `sum` \| `max` \| `p95` \| `p99`)

**Response `200`**
```json
{
  "success": true,
  "data": {
    "service": "storage",
    "metric": "response_time_ms",
    "aggregation": "p95",
    "resolution": "5m",
    "unit": "ms",
    "points": [
      { "timestamp": 1692345600, "value": 142.5 },
      { "timestamp": 1692345900, "value": 156.2 }
    ]
  }
}
```

---

### 11.3 `GET /monitoring/alerts`

**Query:** `severity`, `status` (`firing` \| `resolved`), `service`, `limit`

**Response `200`**
```json
{
  "success": true,
  "data": [
    {
      "alert_id": "alt_01H8X",
      "service": "storage",
      "type": "disk_usage_high",
      "severity": "critical",
      "message": "Storage disk usage above 90%",
      "threshold": { "operator": "gt", "value": 90, "unit": "percent" },
      "current_value": 89.4,
      "status": "firing",
      "triggered_at": 1692345600,
      "resolved_at": null,
      "duration_seconds": 1800,
      "runbook_url": "https://freya.local/runbooks/storage-disk-full",
      "linked_task_id": "tsk_01H9Z"
    }
  ]
}
```

**Severidades:** `info` \| `warning` \| `critical`

---

### 11.4 `GET /monitoring/incidents`

**Response `200`**
```json
{
  "success": true,
  "data": [
    {
      "incident_id": "inc_01H8X",
      "title": "Storage disk full event",
      "description": "Storage reached 95% usage; lifecycle cleanup triggered",
      "service": "storage",
      "severity": "p2",
      "status": "resolved",
      "root_cause": "Archived objects not cleaned after 90 days",
      "started_at": 1692345600,
      "resolved_at": 1692346200,
      "resolution_time_seconds": 600,
      "assigned_to": "usr_01H8X",
      "linked_alerts": ["alt_01H8X"],
      "post_mortem": "Schedule auto-cleanup for archived objects older than 90 days"
    }
  ]
}
```

**Severidades de incident:** `p1` (crítico, todo caído) \| `p2` (degradación mayor) \| `p3` (menor) \| `p4` (cosmético)

---

### 11.5 Otros endpoints Monitoring

| Método | Endpoint | Request | Response |
|--------|----------|---------|----------|
| GET | `/monitoring/services/{service}` | — | `200` → detalle + métricas clave |
| POST | `/monitoring/services/{service}/health-check` | — | `200` → resultado inmediato |
| GET | `/monitoring/dashboard` | — | `200` → resumen global |
| GET | `/monitoring/sla` | `?period=monthly` | `200` → cumplimiento por servicio |
| GET | `/monitoring/deployment-log` | `?service&limit` | `200` → deploys con health antes/después |
| PUT | `/monitoring/alerts/{alert_id}/resolve` | `{ "resolution_note" }` | `200` |
| POST | `/monitoring/incidents` | `{ "title", "service", "severity", "description" }` | `201` |
| PUT | `/monitoring/incidents/{id}` | `{ "status", "root_cause", "post_mortem" }` | `200` |

---

## 12. Webhooks

### 12.1 `POST /webhooks/subscribe`

**Request**
```json
{
  "url": "https://fortuna.local/hooks/freya",
  "events": ["task.completed", "build.completed", "rollback.triggered"],
  "description": "Fortuna event receiver",
  "retry_count": 5,
  "timeout_seconds": 30,
  "headers": { "X-Custom-Auth": "internal-token" },
  "active": true
}
```

**Response `201`**
```json
{
  "success": true,
  "data": {
    "endpoint_id": "whe_01H8X",
    "url": "https://fortuna.local/hooks/freya",
    "events": ["task.completed", "build.completed", "rollback.triggered"],
    "signing_secret": "whsec_9f2a8c1b4d7e6f3a0b5c8d1e4f7a2b9c",
    "active": true,
    "created_at": 1692345600
  }
}
```

> `signing_secret` se devuelve solo aquí. Se usa para verificar `X-Freya-Signature`.

---

### 12.2 Catálogo de Eventos

**`GET /webhooks/events` — Response `200`**

| Evento | Servicio origen | Payload principal |
|--------|-----------------|-------------------|
| `task.created` | project-manager | `task_id`, `project_id`, `title`, `priority` |
| `task.assigned` | project-manager | `task_id`, `assigned_to`, `assigned_by` |
| `task.completed` | project-manager | `task_id`, `project_id`, `completed_by`, `xp_awarded` |
| `sprint.started` | project-manager | `sprint_id`, `project_id`, `goal`, `total_points` |
| `sprint.completed` | project-manager | `sprint_id`, `completion_percent`, `velocity` |
| `project.created` | project-manager | `project_id`, `project_type`, `owner` |
| `commit.pushed` | git | `repo_id`, `branch`, `commits[]`, `pusher` |
| `branch.created` | git | `repo_id`, `branch`, `from_commit` |
| `tag.created` | git | `repo_id`, `tag`, `target_commit` |
| `build.started` | ci/cd | `build_id`, `pipeline_id`, `commit` |
| `build.completed` | ci/cd | `build_id`, `status`, `duration_seconds` |
| `build.failed` | ci/cd | `build_id`, `failure.stage`, `failure.reason` |
| `deployment.started` | ci/cd | `deployment_id`, `version`, `service` |
| `deployment.completed` | ci/cd | `deployment_id`, `version`, `health_status` |
| `rollback.triggered` | ci/cd | `build_id`, `from_version`, `to_version`, `reason` |
| `user.created` | auth | `user_id`, `email`, `role`, `tenant_id` |
| `user.deleted` | auth | `user_id`, `deleted_by` |
| `user.role_changed` | auth | `user_id`, `old_role`, `new_role` |
| `tenant.created` | auth | `tenant_id`, `project_id` |
| `tenant.deactivated` | auth | `tenant_id`, `reason` |
| `object.uploaded` | storage | `bucket`, `key`, `version_id`, `size` |
| `object.deleted` | storage | `bucket`, `key`, `version_id` |
| `secret.rotated` | secrets | `namespace`, `key`, `version` |
| `secret.expiring` | secrets | `namespace`, `key`, `expires_at` |
| `alert.triggered` | monitoring | `alert_id`, `service`, `severity`, `message` |
| `alert.resolved` | monitoring | `alert_id`, `duration_seconds` |
| `service.down` | monitoring | `service`, `last_healthy_at` |
| `service.recovered` | monitoring | `service`, `downtime_seconds` |
| `user.leveled_up` | gamification | `user_id`, `old_level`, `new_level` |
| `achievement.unlocked` | gamification | `user_id`, `achievement_id`, `rarity` |
| `quest.completed` | gamification | `user_id`, `quest_id`, `quest_type` |

---

### 12.3 Formato de Entrega (Freya → suscriptor)

**Request que Freya envía al `url` registrado:**

```
POST https://fortuna.local/hooks/freya
Content-Type: application/json
X-Freya-Event: task.completed
X-Freya-Delivery-ID: dlv_01H8X
X-Freya-Signature: sha256=a1b2c3d4e5f6...
X-Freya-Timestamp: 1692345600
X-Custom-Auth: internal-token
```

```json
{
  "event": "task.completed",
  "delivery_id": "dlv_01H8X",
  "tenant_id": "fortuna",
  "occurred_at": 1692345600,
  "data": {
    "task_id": "tsk_01H8X",
    "project_id": "prj_fortuna_01H8X",
    "title": "Implement transaction validator",
    "completed_by": "usr_01H8X",
    "story_points": 8,
    "xp_awarded": 253
  }
}
```

**Cálculo de firma:** `HMAC-SHA256(signing_secret, "{timestamp}.{raw_body}")`, resultado en hex con prefijo `sha256=`.

**Respuesta esperada del suscriptor:** cualquier `2xx` dentro del `timeout_seconds`. Cuerpo ignorado.

**Política de reintentos:** backoff exponencial `2^n × 60s` — 1min, 2min, 4min, 8min, 16min. Tras agotar `retry_count`, el evento pasa a la DLQ.

---

### 12.4 `GET /webhooks/deliveries`

**Query:** `endpoint_id`, `event`, `status`, `from`, `to`, `limit`

**Response `200`**
```json
{
  "success": true,
  "data": [
    {
      "delivery_id": "dlv_01H8X",
      "endpoint_id": "whe_01H8X",
      "event": "task.completed",
      "status": "success",
      "http_status": 200,
      "attempt_count": 1,
      "duration_ms": 145,
      "delivered_at": 1692345601,
      "created_at": 1692345600
    },
    {
      "delivery_id": "dlv_01H8Y",
      "endpoint_id": "whe_01H8X",
      "event": "build.failed",
      "status": "retrying",
      "http_status": 503,
      "attempt_count": 3,
      "next_retry_at": 1692346200,
      "last_error": "Connection refused",
      "created_at": 1692345600
    }
  ]
}
```

**Estados:** `pending` \| `success` \| `retrying` \| `failed` \| `dlq`

---

### 12.5 Otros endpoints Webhooks

| Método | Endpoint | Request | Response |
|--------|----------|---------|----------|
| GET | `/webhooks/endpoints` | `?active` | `200` → lista (sin `signing_secret`) |
| GET | `/webhooks/endpoints/{id}` | — | `200` → detalle + stats de entrega |
| PUT | `/webhooks/endpoints/{id}` | `{ "url", "events", "active", "retry_count" }` | `200` |
| DELETE | `/webhooks/endpoints/{id}` | — | `204` |
| POST | `/webhooks/endpoints/{id}/test` | `{ "event": "task.completed" }` | `200` → resultado de entrega de prueba |
| POST | `/webhooks/endpoints/{id}/rotate-secret` | — | `200` → nuevo `signing_secret` |
| GET | `/webhooks/deliveries/{id}` | — | `200` → detalle + request/response completos |
| POST | `/webhooks/deliveries/{id}/retry` | — | `202` |
| GET | `/webhooks/dlq` | `?limit` | `200` → eventos muertos |
| POST | `/webhooks/dlq/{id}/reprocess` | — | `202` |

---

## 13. Automation — Scheduler

### 13.1 `POST /automation/schedules`

**Request**
```json
{
  "job_name": "fortuna_nightly_report",
  "description": "Genera reporte nocturno de transacciones",
  "schedule_type": "cron",
  "cron_expression": "0 2 * * *",
  "timezone": "America/Sao_Paulo",
  "handler": {
    "type": "webhook",
    "url": "https://fortuna.local/jobs/nightly-report",
    "method": "POST",
    "headers": { "X-Job-Auth": "..." },
    "payload": { "format": "pdf" }
  },
  "timeout_seconds": 1800,
  "max_retries": 3,
  "retry_interval_seconds": 300,
  "active": true
}
```

| Campo | Tipo | Oblig. | Reglas |
|-------|------|--------|--------|
| `schedule_type` | enum | Sí | `cron` \| `interval` \| `once` |
| `cron_expression` | string | Si type=`cron` | Formato cron estándar de 5 campos |
| `interval_seconds` | int | Si type=`interval` | Mín 60 |
| `run_at` | ISO 8601 | Si type=`once` | Futuro |
| `timezone` | string | No | IANA tz; default `UTC` |
| `handler.type` | enum | Sí | `webhook` \| `internal_service` |

**Response `201`**
```json
{
  "success": true,
  "data": {
    "schedule_id": "sch_01H8X",
    "job_name": "fortuna_nightly_report",
    "schedule_type": "cron",
    "cron_expression": "0 2 * * *",
    "timezone": "America/Sao_Paulo",
    "next_run_at": 1692421200,
    "active": true,
    "created_at": 1692345600
  }
}
```

**Errores:** `VALIDATION_ERROR` (422) si el cron es inválido o el intervalo es menor a 60s.

---

### 13.2 `GET /automation/schedules`

**Query:** `service`, `active`, `limit`

**Response `200`**
```json
{
  "success": true,
  "data": [
    {
      "schedule_id": "sch_01H8X",
      "job_name": "fortuna_nightly_report",
      "schedule_type": "cron",
      "cron_expression": "0 2 * * *",
      "next_run_at": 1692421200,
      "last_run_at": 1692334800,
      "last_status": "success",
      "last_duration_seconds": 142,
      "consecutive_failures": 0,
      "active": true
    }
  ]
}
```

---

### 13.3 `POST /automation/schedules/{id}/run-now`

**Response `202`**
```json
{
  "success": true,
  "data": {
    "execution_id": "exe_01H8X",
    "schedule_id": "sch_01H8X",
    "status": "running",
    "triggered_by": "usr_01H8X",
    "trigger_type": "manual",
    "started_at": 1692345600
  }
}
```

---

### 13.4 `GET /automation/executions`

**Query:** `schedule_id`, `status`, `from`, `to`, `limit`

**Response `200`**
```json
{
  "success": true,
  "data": [
    {
      "execution_id": "exe_01H8X",
      "schedule_id": "sch_01H8X",
      "job_name": "fortuna_nightly_report",
      "status": "success",
      "trigger_type": "scheduled",
      "started_at": 1692334800,
      "completed_at": 1692334942,
      "duration_seconds": 142,
      "attempt": 1,
      "http_status": 200
    },
    {
      "execution_id": "exe_01H8Y",
      "schedule_id": "sch_01H9A",
      "job_name": "storage_lifecycle",
      "status": "failed",
      "trigger_type": "scheduled",
      "started_at": 1692331200,
      "completed_at": 1692331260,
      "duration_seconds": 60,
      "attempt": 3,
      "error": { "code": "UPSTREAM_TIMEOUT", "message": "storage did not respond within 60s" },
      "next_retry_at": null
    }
  ]
}
```

**Estados:** `pending` \| `running` \| `success` \| `failed` \| `timeout` \| `cancelled` \| `skipped`

---

### 13.5 Jobs Predefinidos del Sistema

Creados en bootstrap; visibles pero no eliminables por tenants.

| `job_name` | Cron | Servicio | Acción |
|------------|------|----------|--------|
| `database_backup` | `0 2 * * *` | database | Backup completo + compresión |
| `storage_lifecycle` | `0 3 * * *` | storage | Archivar v4–v5, borrar v6+ |
| `git_github_sync` | `0 4 * * *` | git | Push de commits antiguos a GitHub |
| `ci_cd_artifact_cleanup` | `0 5 * * *` | ci/cd | Borrar artifacts > 90 días |
| `monitoring_metrics_cleanup` | `0 6 * * *` | monitoring | Purgar métricas > 30 días |
| `auth_session_cleanup` | `0 * * * *` | auth | Borrar refresh tokens expirados |
| `secrets_expiry_check` | `0 7 * * *` | secrets | Emitir `secret.expiring` (30 días antes) |
| `gamification_daily_reset` | `0 0 * * *` | gamification | Reset de quests diarias |
| `gamification_weekly_eval` | `0 1 * * 1` | gamification | Evaluar quests semanales |
| `gamification_monthly_eval` | `0 1 1 * *` | gamification | Evaluar quests mensuales |
| `gamification_annual_eval` | `0 1 1 1 *` | gamification | Evaluar quests anuales |
| `gamification_leaderboard` | `*/15 * * * *` | gamification | Recalcular ranking |
| `icloud_sync` | `*/5 * * * *` | project-manager | Sync bidireccional de calendarios |
| `monitoring_health_check` | `*/5 * * * *` | monitoring | Health check de los 14 servicios |
| `webhooks_retry_processor` | `* * * * *` | webhooks | Procesar cola de reintentos |

---

### 13.6 Otros endpoints Automation

| Método | Endpoint | Request | Response |
|--------|----------|---------|----------|
| GET | `/automation/schedules/{id}` | — | `200` → detalle + últimas 10 ejecuciones |
| PUT | `/automation/schedules/{id}` | config parcial | `200` |
| DELETE | `/automation/schedules/{id}` | — | `204` |
| POST | `/automation/schedules/{id}/enable` | — | `200` |
| POST | `/automation/schedules/{id}/disable` | — | `200` |
| GET | `/automation/executions/{id}` | — | `200` → detalle |
| GET | `/automation/executions/{id}/logs` | — | `200` → salida del job |

---

## 14. Endpoints de Sistema

| Método | Endpoint | Auth | Response |
|--------|----------|------|----------|
| GET | `/health` | Ninguna | `200` → `{ "status": "healthy", "version": "1.0.0", "uptime_seconds": 86400 }` |
| GET | `/health/deep` | Service account | `200` → estado de cada dependencia upstream |
| GET | `/services` | Bearer | `200` → servicios disponibles para el tenant + permisos |
| GET | `/metrics` | Interno | Formato exposición Prometheus |

**`GET /services` — Response `200`**
```json
{
  "success": true,
  "data": {
    "tenant_id": "fortuna",
    "services": [
      { "service": "database", "available": true, "permissions": ["read:database", "write:database"], "base_path": "/api/v1/database" },
      { "service": "storage", "available": true, "permissions": ["read:storage", "write:storage"], "base_path": "/api/v1/storage", "quota_bytes": 107374182400 },
      { "service": "gamification", "available": false, "reason": "not_enabled_for_tenant" }
    ]
  }
}
```

---

## 15. Contratos Internos (servicio ↔ servicio)

No expuestos por el gateway. Autenticación por JWT de servicio firmado con RSA; clave pública obtenida de `secrets`.

### 15.1 Header estándar interno

```
Authorization: Bearer {service_jwt}
X-Service-Name: project-manager
X-Tenant-Context: fortuna
X-Request-ID: req_01H8X
```

**JWT de servicio:**
```json
{
  "iss": "auth",
  "sub": "service_authentication",
  "aud": "freya_internal",
  "service": "project-manager",
  "permissions": ["read:database", "write:database", "emit:events"],
  "iat": 1692345600,
  "exp": 1692345900
}
```
Expiración: 5 minutos. Cada servicio cachea su JWT y lo renueva a los 4m30s.

### 15.2 Llamadas internas clave

| Origen | Destino | Endpoint | Propósito |
|--------|---------|----------|-----------|
| todos | `auth` | `POST /authenticate/service` | Obtener JWT de servicio |
| todos | `auth` | `POST /validate` | Validar JWT entrante (o validación local con clave pública) |
| todos | `gestor-db` | `POST /query`, `/mutate` | Acceso a datos |
| todos | `secrets` | `GET /secret/{ns}/{key}` | Obtener credenciales al arrancar |
| todos | `webhooks` | `POST /emit` | Emitir evento de dominio |
| `project-manager` | `gamification` | `POST /xp-transaction` | Otorgar XP por task completada |
| `git` | `ci-cd` | `POST /webhook/{pipeline_id}` | Disparar pipeline en push |
| `ci-cd` | `git` | `GET /repos/{id}/previous-tag/{tag}` | Resolver versión para rollback |
| `ci-cd` | `storage` | `PUT /{bucket}/{key}` | Subir artifacts y logs |
| `ci-cd` | `project-manager` | `PUT /tasks/{id}` | Actualizar estado tras build |
| `git` | `storage` | `PUT /{bucket}/git/objects/{hash}` | Persistir objetos git |
| `automation` | varios | según `handler` | Ejecutar jobs programados |
| `monitoring` | todos | `GET /health` | Health check periódico |
| todos | `monitoring` | `GET /metrics` (scrape) | Exposición de métricas |

### 15.3 `POST /webhooks/emit` (interno)

**Request**
```json
{
  "event": "task.completed",
  "tenant_id": "fortuna",
  "source_service": "project-manager",
  "occurred_at": 1692345600,
  "data": {
    "task_id": "tsk_01H8X",
    "project_id": "prj_fortuna_01H8X",
    "completed_by": "usr_01H8X"
  }
}
```

**Response `202`**
```json
{
  "success": true,
  "data": {
    "event_id": "evt_01H8X",
    "matched_endpoints": 2,
    "deliveries_queued": ["dlv_01H8X", "dlv_01H8Y"]
  }
}
```

---

## 16. Reglas Transversales

### 16.1 Aislamiento de tenant (real, no aspiracional)

A diferencia del diseño original de esta sección, el tenant activo de una
petición **no** se deriva sólo del token: viaja en la cabecera
`X-Tenant-Context` (nunca `X-Tenant-ID`, pese a §1.1), que el frontend
fija a partir del `?project=` elegido en el picker (§3.9). El token nunca
lleva un tenant fijo — un usuario puede tener grants en varios a la vez.

Cada backend (storage/git/cicd/project-manager/gestor-db) valida esa
cabecera contra el propio token en cada request, nunca confía en la
cabecera sola:

- **Llamada de servicio a servicio** (`X-Service-Name` presente y
  coincide con el `service` firmado en el JWT): confianza total para
  cualquier tenant que declare — así se comportó siempre la malla interna.
- **Llamada de un usuario final** (JWT sin `service`): exige que el
  permiso pedido esté en el flat `permissions` del token (rol admin,
  salvo storage/monitoring que restringen admin a `freya`) **o** en
  `tenant_grants[tenant]` del propio JWT (`require_service_access` /
  `require_db_access`, `freya-common/auth_client.py` y
  `gestor-db/app/deps.py`). Si no hay ninguno de los dos → `403 Forbidden`,
  no `404` — se prefirió no ocultar la existencia del tenant sobre el
  riesgo de acostumbrar al cliente a distinguir "no existe" de "no tienes
  acceso" por el código de estado.

Body nunca lleva `tenant_id`: nunca formó parte del contrato real, ni en
el diseño original ni en el actual.

### 16.2 Idempotencia
POST que crean recursos aceptan `Idempotency-Key`. La respuesta se cachea 24h; un reintento con la misma key devuelve la respuesta original sin re-ejecutar.

### 16.3 Timeouts del gateway
| Tipo de operación | Timeout |
|-------------------|---------|
| Lectura simple | 10s |
| Escritura / mutación | 30s |
| Upload / download | 300s |
| Transacción de BD | 60s |
| Trigger de build | 10s (async, devuelve `202`) |

Al exceder → `504 UPSTREAM_TIMEOUT`.

### 16.4 Campos nunca devueltos
`password_hash`, `api_secret` (salvo en creación/rotación), `signing_secret` (salvo en creación/rotación), `private_key`, valores de secretos en respuestas de escritura, `refresh_token` de terceros (iCloud, OAuth).

### 16.5 Trazabilidad
Cada request genera o propaga `X-Request-ID`. Se registra en audit logs de cada servicio involucrado y permite reconstruir el recorrido completo de una petición a través del sistema.
