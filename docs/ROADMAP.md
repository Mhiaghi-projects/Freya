# Freya — Roadmap por fases

El orden lo dictan las dependencias, no el interés. Cada fase deja algo que
arranca y responde. Cuando una fase necesita algo de un servicio posterior, se
pausa, se construye **sólo la parte necesaria** de ese servicio, y se vuelve.
Esos saltos están marcados como **↩ retorno**.

---

## Fase 0 — Fundaciones ✅ (esta entrega)

Sin contenedores todavía. Se fija el terreno.

- Arquitectura, redes, puertos, elección de tecnología.
- Convenciones de API, errores, logs, contenedores, datos.
- Backlog de proyectos y tasks con nivel de dificultad.
- Monorepo, librería común y plantilla de servicio Python.
- `freya.ps1`: control de la plataforma desde PowerShell, sin dependencias en
  el host, más el contenedor `toolbox` para las tareas que necesitan Unix.

**Salida:** `freya.ps1`, `docs/`, `projects/`, `libs/`, `templates/`, `infra/`.

---

## Fase 1 — `database` + `gestor-db` (núcleo de datos) ✅

Nada existe sin dónde guardarlo.

1. Contenedor `database`: PostgreSQL 16-alpine, red `freya-db` privada, volumen
   persistente, límites de recursos.
2. `gestor-db` en **modo bootstrap**: acepta el token estático, expone
   `/api/v1/query`, `/api/v1/execute`, `/api/v1/tx`, y gestión de schemas.
3. Motor de migraciones: aplica `migrations/NNNN_*.sql` por servicio y tenant.
4. Aislamiento por tenant: cada llamada resuelve el schema desde `X-Freya-Tenant`.

**Criterio de salida:** `gestor-db` crea el schema `freya_auth` y ejecuta una
query desde otro contenedor por HTTPS. `/ready` en verde.

---

## Fase 2 — `auth` (identidad) ✅

↩ **retorno a `gestor-db`** al final de esta fase.

1. Schema `freya_auth`: usuarios, roles, permisos, service accounts, tenants.
2. `client_credentials` para servicios: JWT EdDSA de 5 min.
3. `password` + refresh rotativo para usuarios; Argon2id.
4. JWKS público en `/api/v1/.well-known/jwks.json`.
5. Motor de scopes y roles, aislado por tenant.
6. ↩ Volver a `gestor-db`: activar `AUTH_ENABLED=true`, validar JWT contra el
   JWKS, invalidar el token de bootstrap.

**Criterio de salida:** `gestor-db` rechaza el token de bootstrap y acepta un
JWT de `auth`. Ambos servicios se autentican mutuamente. ✅ Verificado de
extremo a extremo: firma EdDSA con rotación de claves, JWKS público,
`client_credentials` para servicios, login con Argon2id, refresh rotativo con
revocación de familia al reusar un token, roles→scopes resueltos en el JWT.

Pendiente para una vuelta posterior (no bloquea la Fase 3): introspección y
revocación de *access token* con propagación &lt;60s pese al cacheo del JWKS
(auth-07 — necesita extender el `JwksCache` de `freya_common` con una
comprobación de revocación de refresco corto), auditoría de eventos de
identidad (auth-08), y aprovisionar cuentas de servicio para el resto de
servicios según se vayan creando (auth-09).

---

## Fase 3 — `secrets` (Barbican) ✅ (núcleo)

1. Envelope encryption AES-256-GCM: master key en fichero montado, una DEK
   por tenant cifrada con ella en la base — rotar la master key sólo
   re-envuelve la DEK, no re-cifra cada secreto. ✅
2. CRUD de secretos con versionado y rotación (`/secrets/{namespace}/{key}`,
   §9). ✅ Verificado: el valor nunca aparece en claro en la base (comprobado
   consultando `secret_versions` directo), `overwrite: false` rechaza
   duplicados, leer una versión antigua tras rotar sigue funcionando. ✅
3. Auditoría de todo acceso a un secreto (`/secrets/{namespace}/audit-logs`). ✅
4. Gestión de certificados (emisión/renovación desde una CA interna,
   sustituyendo la CA de desarrollo de la Fase 0) ✅ — la clave privada de
   la CA vive cifrada en el propio vault (`_internal_ca_key`, misma
   envelope encryption que cualquier secreto), `POST /certs/{service}/issue`
   emite certificados nuevos. `infra/certs/ca/ca.key` ya no existe en
   disco. Verificado en vivo: los 8 servicios ya construidos se
   redesplegaron con certificados emitidos por la CA interna, `doctor` en
   verde. Revocación — pendiente, sin caso de uso real todavía.
5. ↩ `gestor-db` y `auth` dejan de leer credenciales de `.env` y las piden a
   `secrets` al arrancar — **pendiente**, no bloquea lo siguiente.

**Criterio de salida (núcleo):** un secreto se crea, se lee (con y sin
versión), se rota y se audita, todo cifrado en reposo. ✅ La CA interna
(punto 4) ya no es pendiente. **Sigue pendiente:** el retorno de
credenciales reales (punto 5).

---

## Fase 4 — `storage` (Swift) ✅ (núcleo)

1. Modelo `/{tenant}/{bucket}/{key}`, metadatos en `gestor-db`, bytes en
   volumen (`/data`, con sharding por id de versión). ✅
2. API: PUT / GET / DELETE / HEAD / listado con cursor. ✅ Además `Range`
   para descargas parciales (`206`) y listado de versiones por `key`.
3. Multipart upload para ficheros grandes — **pendiente**.
4. Cuotas por tenant, checksum SHA-256 (como `ETag`), control de acceso vía
   `auth` (JWT + permisos `read:storage`/`write:storage`). ✅
5. Espacio reservado `/freya/{servicio}/` para uso interno de la
   plataforma — **pendiente** (hoy cualquier tenant autenticado puede crear
   cualquier bucket; no hay convención de namespacing reservado todavía).

**Criterio de salida:** un objeto se sube, se recupera íntegro y se puede
volver a subir con una versión nueva sin perder la anterior. ✅ Verificado
en vivo contra el servicio desplegado: crear bucket, subir dos versiones
de un objeto, descargar por rango, leer la versión antigua, listar
versiones y objetos, ver el uso del bucket, borrar objeto y borrar bucket
— 22 comprobaciones, usando el mismo circuito JWT de servicio que
usaría `auth` o cualquier otro consumidor autenticado.

Un límite real de `gestor-db` (`limit` topado a 200 en el DSL de `/query`,
§4) rompía `bucket_usage` al pedir páginas de hasta 10000 filas de golpe —
corregido paginando en `app/domain/buckets.py`/`objects.py`.

Pendiente para el criterio completo de la fase: subida multiparte,
restaurar una versión antigua como vigente, `/storage/usage` agregado por
tenant, y la cascada de retención de `max_versions` (§5.6/§13.5 —
queda para el futuro servicio de automatización `storage_lifecycle`).

---

## Fase 5 — `git` (Gerrit) ✅ (núcleo)

1. Repositorios sobre `storage`, protocolo Git smart HTTP vía
   `git http-backend`. ✅ El contenedor no guarda estado propio: cada repo
   es un packfile + un snapshot de refs (2-3 objetos) en el bucket `git` de
   storage, materializados en un directorio efímero por operación.
2. Branches, tags, commits, diffs, árbol de ficheros por API. ✅ (el árbol
   de ficheros no está en docs/freya-api-contract.md §6 todavía, se añadió
   igualmente porque esta tarea lo exige explícitamente).
3. **Política de retención**: los 5 commits más recientes viven en local; el
   resto se empuja a GitHub y se conserva sólo la referencia —
   **pendiente**: se deja para diseñar junto con la sincronización (punto
   4), ya que el modelo de "qué vive sólo en GitHub" es el mismo problema.
4. Sincronización bidireccional con GitHub, con resolución de conflictos —
   **pendiente**.
5. Permisos por repositorio vía `auth`. ✅ (a nivel de tenant: JWT +
   `read:git`/`write:git`/`admin:git`, mismo patrón que el resto de
   servicios). Marcado de repos con datos sensibles para excluirlos del
   push a GitHub — la columna `sensitive` ya existe en el catálogo, pero no
   hay nada todavía que la aplique (depende del punto 3).

**Criterio de salida (núcleo):** `git clone`, `commit` y `push` funcionan
contra Freya con un cliente git real. ✅ Verificado en vivo dos veces
seguidas: crear repo, clonar vacío, dos commits y dos `push`, clonar de
nuevo con los bytes íntegros (2 commits), branches, commits, crear+listar
una tag anotada, diff, árbol de ficheros, borrar repo — 22 comprobaciones.
**Pendiente para el criterio completo de la fase:** que el commit número 6
acabe en GitHub (retención + sincronización, puntos 3 y 4).

Dos bugs reales encontrados verificando en vivo (detalle en
`git/README.md`): (a) un `git clone` de un repo vacío necesita que
el servidor reenvíe la cabecera `Git-Protocol` del cliente como variable de
entorno CGI `HTTP_GIT_PROTOCOL` para que `git http-backend` negocie
protocolo v2 y anuncie la rama por defecto — sin esto, el clon cae
silenciosamente al `master` local del cliente y el primer `push` falla con
`src refspec main does not match any`; (b) subir `refs.json` a `storage`
con `Content-Type: application/json` lo hacía atravesar el
`EnvelopeMiddleware` genérico de storage (que envuelve cualquier respuesta
JSON, sin distinguir su propia API de un blob descargado) y quedar
doblemente envuelto — sin error visible, sólo refs que nunca se escribían.
Arreglado subiendo esos blobs como `application/octet-stream`.

---

## Fase 6 — `project-manager` (Jira) ✅

1. Schema `freya_pm`: proyectos, tasks, milestones, etiquetas, asignaciones. ✅
2. Tablero Kanban con estados configurables. ✅ Columnas por proyecto
   (`pm_board_columns`, sembradas con las 5 del contrato al crear el
   proyecto), no un enum global — el `status` de una task se valida contra
   las columnas de SU proyecto.
3. Dificultad y esfuerzo estimado/real por task — es lo que consume
   `gamification`. ✅ `difficulty` (1-5) no está en
   docs/freya-api-contract.md §7 (que sólo tiene `story_points`), pero esta
   tarea lo exige explícitamente para poder importar `projects/*.yaml` tal
   cual — se soportan ambos campos. `estimated_hours` se deriva de la
   dificultad si no se da explícita.
4. Vínculo task ↔ commit de `git`. ✅ (sólo el vínculo manual, §7.4; la
   alternativa automática por mensaje de commit queda pendiente).
5. Carga inicial del backlog de `projects/` como datos reales. ✅
   `.\freya.ps1 import-backlog` (nuevo comando, `infra/scripts/import_backlog.py`)
   importó los 12 proyectos y sus 92 tasks por la API REST real del
   servicio, idempotente, con dependencias entre tasks del mismo proyecto
   resueltas de verdad (las dependencias ENTRE proyectos del YAML no
   tienen hueco en el schema — se anotan como texto en la descripción, ver
   `project-manager/README.md`).

**Criterio de salida:** el backlog de Freya vive dentro de Freya y se
gestiona desde su propia API. ✅ Verificado en vivo, dos veces seguidas:
crear proyecto, rechazar reglas inválidas (§7.1), crear milestone y dos
tasks dependientes, mover la bloqueada (`409`), completar la que bloquea,
mover la que ya no está bloqueada (`200`), tablero Kanban, progreso de
milestone por dificultad (no por recuento — pm-05 literal), sprint,
vincular y listar un commit, borrar — 21 comprobaciones. Además, la
importación real del backlog de 92 tasks y la comprobación en vivo de que
una task importada bloqueada (`git-03` por `git-02`) rechaza el avance
hasta completar su dependencia.

Pendiente, sin bloquear lo siguiente: `freya_access_enabled` (crear tenant
+ cuenta de servicio + secreto al crear un proyecto — orquestación real
entre `auth`/`secrets`/`gestor-db` que merece su propio diseño),
integración iCloud y diseños de electrónica (§7.8/§7.9), XP al completar
una task (depende de `gamification`, Fase 10), webhooks, snapshot diario
de burndown (pide un job programado que todavía no existe).

---

## Fase 7 — `gestor-monitoring` (Prometheus/Grafana) ✅ (núcleo)

1. Contenedores `metrics` (VictoriaMetrics) y `logs` (VictoriaLogs) en la red
   `freya-mon`. ✅
2. `gestor-monitoring`: descubre targets por la etiqueta `freya.service`, hace
   scrape, expone consultas por HTTPS. ✅ Descubrimiento decidido en vivo
   con el usuario (`AskUserQuestion`): socket de Docker en sólo lectura
   frente a una lista estática regenerada por `freya.ps1` — se eligió el
   socket porque una lista estática no es descubrimiento real (depende de
   que todo cambio pase por `freya.ps1`). Única excepción del proyecto a
   "nada toca Docker salvo `freya.ps1`", documentada en
   `gestor-monitoring/README.md`.
3. Agregación de logs desde stdout de los contenedores — **pendiente**
   (mon-04): el contenedor `logs` existe y tiene retención acotada, pero
   nada le envía datos todavía; es un subsistema en sí mismo.
4. Health checks de todos los servicios → **Cloud Health**. ✅
   `uptime_percent_24h` necesita historial, no sólo el estado actual —
   cada `/ready` se guarda en `mon_health_checks` (gestor-db).
5. Reglas de alerta y notificaciones — **pendiente** (mon-06): depende de
   mon-04 y de tener un canal de notificación real.
6. Grafana bajo perfil opcional, encendido a demanda. ✅ Verificado en vivo
   que un `docker compose up` sin `--profile dashboards` no arranca nada
   ("no service selected") — la protección es real, no sólo documentada.

**Criterio de salida (núcleo):** un panel de estado muestra los servicios
con su salud y métricas reales. ✅ Verificado en vivo, dos veces seguidas:
listar servicios descubiertos (los 7 propios ya construidos), detalle de
uno, `404` de uno inexistente, forzar un health-check inmediato, dashboard,
consulta de métrica amigable con puntos reales, consulta PromQL cruda,
PromQL inválida → `400` — 12 comprobaciones. **Pendiente para el criterio
completo:** latencia y consumo por servicio en el mismo panel dependen de
mon-04/mon-06 para tener sentido completo (hoy sólo hay salud + métricas
crudas consultables, no un panel unificado con alertas).

Ninguno de los seis servicios ya construidos exponía `/metrics` de verdad
todavía: la etiqueta `freya.metrics.port`/`path` existía desde la Fase 0,
pero `create_app()` (`freya-common`) nunca montaba esa ruta. Se
añadió ahí (con `prometheus_client`, la librería oficial de Python —
reimplementar el formato de exposición Prometheus a mano no aportaba
nada), enganchado donde `ContextMiddleware` ya mide cada petición para el
log de acceso, así que los seis servicios exponen métricas reales en
cuanto se reconstruyen con la versión nueva de `freya_common` — se
redesplegaron los seis para comprobarlo, y sus siete series (con
`gestor-monitoring`) aparecieron en VictoriaMetrics.

Tres bugs reales de despliegue (ninguno de lógica de negocio): (a) el
socket de Docker en Docker Desktop es `660 root:root` — el proceso sigue
como UID 10001, nunca root, pero necesita `group_add: ["0"]` como grupo
suplementario para que el permiso de grupo del socket le alcance; (b)
`GF_INSTALL_PLUGINS` de Grafana intentaba instalar el plugin de
VictoriaLogs en arranque, pero `freya-mon` es `--internal` a propósito
(§4) y Grafana no tiene salida a internet ahí — el intento tumbaba el
proceso entero al fallar la resolución DNS de `grafana.com`; se quitó,
junto con la fuente de datos de VictoriaLogs que dependía de ese plugin
(sólo VictoriaMetrics queda pre-provisionada, con el tipo `prometheus`
incorporado); (c) la imagen de VictoriaLogs no tiene `/bin/sh` ni `wget`
—ni siquiera `ls`— así que su `HEALTHCHECK` con `CMD-SHELL` fallaba
siempre y el contenedor se veía "unhealthy" sin estarlo; se quitó el
healthcheck, `gestor-monitoring` ya lo vigila desde fuera.

---

## Fase 8 — `cicd` (Zuul) ✅ (núcleo, alcance recortado)

Dos de sus tareas (ci-03, ci-06) son dificultad 5: por diseño, las
capacidades más peligrosas construidas hasta ahora (ejecución de código
con privilegios de host; control sobre el resto de los servicios de
Freya). Se preguntó el alcance con el usuario antes de escribir código
(`AskUserQuestion`) en vez de asumirlo — respuesta: núcleo sin runner
general, y un Deployment Manager que sólo modela el flujo ("antes de
ejecutar algo debe correr con un pipeline; si falla, no se ejecuta"),
más una petición explícita añadida: migrar las pruebas unitarias ya
construidas para que corran de verdad por este servicio.

1. Pipelines declarativos en YAML dentro del repositorio — **recortado**:
   sólo existe `pipeline_type: "standard-tests"`, fijo en el propio
   servicio (nunca definido por quien llama a la API). Un YAML arbitrario
   en el repo significaría ejecutar lo que ese YAML defina — la misma
   superficie que se decidió no abrir.
2. Runner: lanza contenedores efímeros por job, con límites estrictos. ✅
   (recortado a un único camino fijo, ver abajo) — nunca acepta un
   Dockerfile, imagen o comando que no sea ese camino.
3. Disparadores: push a `git`, cron, manual. ✅ manual y push (cron sigue
   pendiente) — `git` dispara el pipeline `<repo>-standard-tests` en
   segundo plano tras un push que persiste con éxito
   (`git/app/domain/webhooks.py`), mejor esfuerzo, nunca bloquea
   ni tumba la respuesta al cliente git real.
4. **Deployment Manager**: despliegue y rollback de servicios de Freya —
   **recortado a simulación gateada** (ver abajo). Real, deliberadamente
   fuera de alcance.
5. **Dependency Updater**: revisa dependencias, abre tasks en
   `project-manager` — **pendiente**.
6. Consume credenciales de `secrets`, artefactos a `storage`, logs a
   `monitoring` — **pendiente**: el único job que existe hoy (lint/test)
   no consume secretos ni produce artefactos más allá de su log.

`app/domain/runner.py` reproduce exactamente `Invoke-FreyaTest` de
`infra/powershell/FreyaServices.psm1` (`docker build --target dev` + `ruff
check` + `pytest`), nunca un pipeline arbitrario. `<servicio>` se valida
contra un patrón estricto Y contra la existencia real de su Dockerfile
dentro del workspace, con `subprocess` siempre en forma de lista de
argumentos (nunca `shell=True`) — `tests/test_runner.py` prueba
explícitamente que intentos de recorrido de ruta e inyección de comandos
se rechazan. Necesita el socket de Docker en **escritura** (crear/correr
imágenes, no sólo listarlas como `gestor-monitoring`) — segunda excepción
del proyecto a "nada toca Docker salvo `freya.ps1`", ahora regla explícita
en `docs/ARCHITECTURE.md`. "Docker fuera de Docker": sólo el cliente
`docker` (de la imagen oficial `docker:27-cli`), nunca un daemon propio;
el repo se monta de sólo lectura como contexto de build.

**Criterio de salida (núcleo):** un pipeline construye y testea un
servicio de Freya sin intervención manual, y un despliegue no se acepta
sin una ejecución exitosa que lo respalde. ✅ Verificado en vivo: crear
pipeline, rechazar `pipeline_type` no soportado (`422`), disparar
build+lint+test real contra `storage` (los tres jobs en verde, log del
job de test con "passed" de verdad), crear un despliegue simulado sobre
esa ejecución, `404` al disparar un servicio inexistente, `404` al
desplegar sobre una ejecución inexistente — 14 comprobaciones. Después,
los ocho servicios ya construidos se migraron a sendos pipelines
`standard-tests` y se dispararon todos de verdad contra este servicio.
✅ "Sin intervención manual" de punta a punta ya no es pendiente: un push
real con un cliente `git` (repo `storage` autoalojado) disparó el pipeline
solo, sin ningún `POST /trigger` manual — ver `git/README.md`.
Además, cada servicio puede elegir sus pasos (`lint`/`test`/
`security_scan`) por YAML (`.freya/pipeline.yaml`), y `security_scan`
(`pip-audit`) encontró y forzó la corrección de un CVE real. **Sigue
pendiente para el criterio completo de la fase:** "despliega" de verdad
(Deployment Manager real, ci-06) — deliberadamente fuera de esta pasada,
confirmado de nuevo en vivo con el usuario.

---

## Fase 9 — `frontend` (Horizon)

1. Gateway HTTPS: única entrada desde el exterior, enruta al servicio destino.
2. UI: dashboard, navegación entre servicios, autenticación contra `auth`.
3. **Service Catalog**: inventario vivo de servicios y sus APIs.
4. **Developer Portal**: documentación y consola de pruebas, con datos de
   `project-manager`.
5. Vistas de `git`, `storage`, `cicd` y `monitoring`.

**Criterio de salida:** Freya se administra entera desde el navegador.

---

## Fase 10 — `gamification`

1. Schema `freya_gamification`. XP, niveles, monedas, rachas, achievements.
2. Consumo de `project-manager`: la XP sale de la dificultad de las tasks.
3. Tareas diarias, semanales, mensuales y anuales; metas.
4. **Habit Tracker**, **Expense Rewards**, **Leaderboard**, **Project Showcase**.
5. **Personal Dashboard**, renderizado por `frontend`.

**Criterio de salida:** cerrar una task en `project-manager` otorga XP y mueve
el nivel sin intervención.

---

## Fase 11 — Endurecimiento

- Rotación automática de certificados y secretos (la emisión manual ya
  existe, `.\freya.ps1 renew-cert <servicio>` — ver Fase 3, punto 4).
- Backups de `database` hacia el propio `storage`, con verificación —
  ✅ adelantado antes de esta fase (`.\freya.ps1 backup`/`restore-check`).
  Backups de `storage` sobre sí mismo sigue pendiente.
- Rate limiting por tenant en `frontend`.
- Auditoría transversal.
- Onboarding de tenants externos, documentado y automatizado.

---

## Resumen de dependencias

```
database → gestor-db → auth ─┬→ secrets ─┐
                             ├→ storage ─┴→ git → cicd
                             └→ project-manager → gamification
                                                        ↑
                    gestor-monitoring ──────────────────┤
                                   frontend ────────────┘
```

## Retornos previstos

| Fase | Se pausa para volver a | Motivo |
|---|---|---|
| 2 | `gestor-db` | activar validación JWT, matar el bootstrap |
| 3 | `gestor-db`, `auth` | migrar credenciales a `secrets` |
| 5 | `storage` | backend de objetos para packfiles Git |
| 8 | `git`, `secrets` | webhooks y credenciales de despliegue |
| 9 | todos | cada servicio expone su descriptor para el Service Catalog |
