# frontend

GUI de administración + las API que usa esa GUI para hablar con el resto de
la malla (docs/ROADMAP.md Fase 9). Ya no es la puerta externa: eso lo hace
`services/traefik/`, que termina TLS y enruta hacia aquí -- frontend no
publica puerto propio, se alcanza sólo por `freya-mesh`, en HTTP plano (ver
`Dockerfile` y `services/traefik/README.md` para el porqué de que ese salto
concreto no lleve TLS de Freya).

## Modelo de sesión: sin token en el navegador

frontend no tiene identidad de servicio propia (sin `api_secret`, sin
`ServiceTokenProvider`): es un proxy que siempre actúa como el usuario que
inició sesión, nunca con privilegios elevados. El navegador nunca ve ningún
JWT:

1. `POST /api/session/sign-in` llama al `sign-in` real de `auth` y guarda el
   access/refresh token en dos cookies `httponly` (`app/deps.py:set_session_cookies`).
2. Cada ruta de proxy (`app/api/{git,storage,cicd,projects,catalog}.py`) usa
   `WebSessionDep` (`app/deps.py`), que lee la cookie de acceso, la valida
   contra el JWKS de `auth`, y si caducó la renueva de forma transparente con
   la cookie de refresh -- sin que el navegador se entere.
3. `app/infra/gateway.py:backend_client` construye un `ServiceClient` hacia
   el backend pedido, reenviando ese mismo token como `Authorization`. Los
   permisos (`read:git`, `write:cicd`, ...) los sigue exigiendo cada backend,
   no esta capa -- frontend nunca decide quién puede ver qué.

## Primer admin: bootstrap manual

El alta pública (`/api/v1/auth/sign-up` en `auth`) siempre crea `role: user`,
y crear un admin por API exige ya tener un admin (`AdminDep` en
`auth/app/deps.py`). El primer admin se siembra a mano, una sola vez, con
`UPDATE users SET role='admin' WHERE ...` directo en `gestor-database` --
mismo patrón que el resto de credenciales irreducibles de arranque de esta
plataforma (`api_secret`, `postgres_password`, la clave de firma inicial de
`auth`).

## `must_change_password`

Campo añadido a `auth` (`auth/migrations/0002_must_change_password.sql`)
para forzar un cambio de contraseña en el primer login de una cuenta
sembrada así. `sign-in` lo devuelve; el SPA (`app/static/app.js`) bloquea el
acceso al panel hasta que se llama a `POST /api/session/change-password`.

## Panel (`app/static/`)

HTML/CSS/JS sin build ni dependencias externas, servido en `/app` con
`StaticFiles`. Enrutado por hash (`#/git`, `#/storage/<bucket>`, ...) en
`app.js`. Vistas: panel/catálogo (fusiona el catálogo estático de
`app/domain/catalog.py` con el estado en vivo de `gestor-monitoring`), git,
storage, CI/CD (con botón para disparar un pipeline) y proyectos (kanban de
`project-manager`, Developer Portal de la Fase 9).

## Certificado

frontend ya no sirve HTTPS propio (ver arriba), pero sigue montando
`infra/certs/frontend/ca.crt` para confiar en la CA interna al llamar a
auth/storage/git/cicd/project-manager/gestor-monitoring. El certificado que
ve el navegador es el de `traefik` (`services/traefik/README.md`).

## Tests

```powershell
.\freya.ps1 test frontend
.\freya.ps1 lint frontend
```
