# auth

Identidad de Freya. Firma los JWT que usa toda la malla, gestiona usuarios y
cuentas de servicio. No toca PostgreSQL directamente — pasa por `gestor-db`,
igual que cualquier otro servicio. Contrato: `docs/freya-api-contract.md`
§2 (usuarios), §3 (admin), §15 (interno servicio-a-servicio).

## Modo bootstrap

Con `FREYA_AUTH_ENABLED=false`: auth habla con `gestor-db` usando el token
estático de éste (montado aparte, `/run/gestor-db-bootstrap-token`), y
`/admin/*` exige el token de bootstrap **propio** de auth
(`/run/secrets/bootstrap_token`) — no puede haber JWT hasta que exista al
menos una cuenta de servicio.

Con `FREYA_AUTH_ENABLED=true`: auth firma su propio JWT de servicio en
proceso para hablar con `gestor-db` (`SelfTokenProvider` — pedírselo a sí
misma por HTTP sería un autobloqueo, ver `app/infra/gestor_db_client.py`).
`/admin/*` exige un JWT de usuario con `role: admin`.

## Claves de firma (RSA)

```powershell
.\freya.ps1 signing-key auth
```

Genera un par RSA 2048 en `infra/secrets/auth/signing_keys/<marca-de-tiempo>.pem`.
auth carga todos los ficheros de ese directorio al arrancar: firma con el
más nuevo, publica todos en el JWKS — un token emitido con una clave
anterior sigue verificando mientras esa clave no se borre. Sin ninguna
clave montada (p. ej. en tests), genera una efímera en memoria.

## JWT de servicio vs. JWT de usuario

Dos formas, misma audiencia fija `"freya_internal"` (§15.1):

- **Servicio** (`POST /authenticate/service`): `sub` es la constante
  `"service_authentication"` — la identidad real va en la claim `service`.
  `permissions` es una lista plana (`["read:database", ...]`).
- **Usuario** (`/api/v1/auth/sign-in`): `sub` es el `user_id`. `role` es
  `user` o `admin`; `permissions` sale de una tabla fija por rol
  (`app/domain/users.py::ROLE_PERMISSIONS`), no de un motor de roles en
  base — el contrato no lo pide más granular que eso.

## Endpoints

| Ruta | Auth | Qué hace |
|---|---|---|
| `GET /.well-known/jwks.json` | ninguna | Claves públicas RSA activas, con `kid`. |
| `POST /authenticate/service` | `service` + `api_secret` en el cuerpo | JWT de servicio, 5 min. Interno, no expuesto por el gateway. |
| `POST /admin/service-accounts` | bootstrap / `role: admin` | Alta de cuenta de servicio: `service`, `api_secret`, `permissions`. |
| `POST /api/v1/auth/sign-up` | pública | Alta de usuario: `email`, `password` (Argon2id), `first_name`, `last_name`. |
| `POST /api/v1/auth/sign-in` | pública | `email` + `password` → JWT de 15 min + refresh de 30 días. |
| `POST /api/v1/auth/refresh-token` | el refresh es la credencial | Rota el refresh, revoca el usado. |
| `POST /api/v1/auth/sign-out` | pública | Revoca el refresh token presentado. |

## Refresh token rotativo

El token que ve el cliente es `"<id>.<secret>"`: `id` es el selector
(columna indexada, no secreto), `secret` es lo que se verifica con
Argon2id. Reusar un `id` ya rotado revoca **toda la familia** — es la señal
de que ese token fue robado y usado por dos partes.

## Seguridad

- Límite de tasa en sign-in: 5 intentos/min por (tenant, email) —
  `app/infra/rate_limit.py`, en memoria, vale para `--workers 1`.
- Tiempo constante en login: un email o `service` desconocido gasta el
  mismo trabajo de Argon2id que una contraseña incorrecta.
- `SelfTokenProvider` se autoconcede sólo `read:database`+`write:database`
  para hablar con gestor-db — nunca `*`.
- Log de auditoría mínimo (`freya.audit`): login correcto/fallido con
  email, tenant e IP. No sustituye una tabla de auditoría persistida.

## Pendiente

El contrato (§2, §3) define bastante más superficie de la construida:
`verify-token`, `forgot-password`/`reset-password`, `user-info`,
`profile`, `password/change`, CRUD completo de `/auth/admin/users` (list,
get, put, delete, cambiar rol, reset-password ajeno), `audit-logs`, MFA.
También queda pendiente introspección/revocación de *access token* con
propagación &lt;60 s.

## Estructura

```
app/
├── main.py                creación de la app, lifespan, claves, migraciones
├── config.py                settings: TTLs, rutas de claves y bootstrap
├── deps.py                    AdminDep: bootstrap o JWT con role: admin
├── api/                        jwks, service_auth, auth, admin
├── domain/
│   ├── keys.py                  KeyRing: carga y publica claves RSA
│   ├── tokens.py                 firma JWT de servicio y de usuario
│   ├── passwords.py               hashing Argon2id, tiempo constante
│   ├── accounts.py                 cuentas de servicio
│   ├── users.py                     usuarios, login, permisos por rol
│   └── refresh.py                   rotación de refresh token
├── infra/
│   ├── gestor_db_client.py           DSL de gestor-db + SelfTokenProvider
│   ├── migrations.py                  aplica migrations/*.sql con reintento
│   └── rate_limit.py                   limitador de tasa en memoria
└── models/requests.py
```

## Tests

```powershell
.\freya.ps1 test auth
.\freya.ps1 lint auth
```
