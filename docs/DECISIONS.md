# Decisiones autónomas

Registro de decisiones de diseño tomadas sin confirmación explícita del
usuario, cuando había más de una opción razonable. Pedido explícito del
usuario (2026-08-22): "en caso de que tengas una decisión, toma la que
creas más apropiada, pero déjala anotada en un archivo para leerlas luego."

Cada entrada: qué se decidió, por qué, y qué alternativa se descartó -- para
que revisar esto luego sea "¿de acuerdo o no?", no "¿qué hizo aquí y por
qué?".

---

## 2026-08-22 — Traefik: enrutado por fichero estático, no por proveedor docker

**Decisión:** `services/traefik/dynamic/routes.yml` declara el router hacia
`frontend` a mano, en vez de que Traefik descubra contenedores vía
`docker.sock` y sus labels `traefik.*`.

**Por qué:** probado en vivo -- el cliente Docker SDK de Traefik contra el
socket de Docker Desktop en Windows devuelve `400 Bad Request` sin cuerpo en
la negociación inicial, de forma reproducible (probado en dos versiones de
Traefik, v3.2 y v3.5). `curl` directo al mismo socket responde 200 normal a
`/version` y `/info`, así que el socket en sí funciona -- es el cliente Go
de Traefik el que no lo tolera en este entorno concreto.

**Alternativa descartada:** proveedor docker con labels (más "estándar" y
dinámico, pero bloqueado por el problema de arriba). Revisar si esto cambia
en una versión futura de Traefik o de Docker Desktop.

---

## 2026-08-22 — Storage: bucket "users" es el único visible desde el panel

**Decisión:** `frontend/app/api/storage.py` excluye `git`, `secrets`,
`backups`, `logs`, `artifacts` del panel de storage -- ni en la lista ni por
URL directa (404).

**Por qué:** pedido explícito del usuario ("no debería ver como
administrador... son archivos de los servicios"). La lista exacta de
buckets "internos" está hardcodeada en `_INTERNAL_BUCKETS`
(`frontend/app/api/storage.py`) -- si se crea un bucket interno nuevo para
otro servicio, hay que añadirlo ahí a mano; no hay una convención en
`storage` que distinga "bucket de servicio" de "bucket de usuario" todavía.

**Alternativa descartada:** que `storage` mismo marque buckets como
internos/públicos en su propio schema (más robusto, pero es un cambio de
storage, no sólo de frontend -- se dejó para si hace falta más adelante).

---

## 2026-08-22 — Roles de auth: por servicio, no un motor de permisos dinámico [SUPERADA, ver entrada de abajo]

**Decisión:** `auth/app/domain/users.py:ROLE_PERMISSIONS` ganó
`git_user`/`storage_user`/`cicd_user`/`monitoring_user`/`project_user`,
cada uno acotado a un solo servicio -- no una tabla de roles en base ni
permisos arbitrarios por usuario.

**Por qué:** pedido explícito del usuario ("solo quiero que pueda usar el
git... rol git_user"), y matchea el patrón ya existente (roles fijos con
permisos fijos) sin construir un motor de RBAC nuevo.

**Alternativa descartada:** permisos arbitrarios por usuario (más flexible,
pero es un cambio de schema -- tabla de permisos por usuario en vez de por
role -- que nadie pidió; roles con nombre siguen el ejemplo que dio el
usuario al pie de la letra).

**Superada el mismo día:** el usuario corrigió explícitamente el diseño --
"Debe haber solo 2 tipo de usuarios, no? admin y usuario. El segundo puede
tener diferentes roles segun los servicios que usara". Un rol con nombre
por servicio no escala (5 roles para 4 servicios, mutuamente excluyentes:
un usuario no podía tener git_user *y* cicd_user a la vez) y no era lo que
pidió, aunque en su momento pareció el ejemplo más literal de su frase
original. Rediseño real: `ROLE_PERMISSIONS` vuelve a sólo `user`/`admin`;
el acceso por servicio pasa a `users.extra_permissions` (columna
`text[]`, migración `0003_extra_permissions.sql`), una lista libre y
combinable validada contra `SERVICE_GRANTS` (git/cicd/monitoring/
project-manager). `full_permissions(role, extra_permissions)` mezcla
ambas. Ver `auth/app/domain/users.py`, `frontend/app/static/app.js`
(sección `admin-users`, checkboxes de acceso).

---

## 2026-08-22 — Borrado de usuario: DELETE real, no soft-delete

**Decisión:** `DELETE /admin/users/{id}` en auth borra la fila de verdad
(`gdb_mutate(..., action="delete")`), no marca `active=false`/`deleted_at`
aunque la columna `deleted_at` ya existe en el schema.

**Por qué:** el usuario pidió literalmente "elimina" para limpiar cuentas de
prueba: `refresh_tokens` tiene `ON DELETE CASCADE` sobre `user_id`, así que
un hard delete no deja basura huérfana.

**Alternativa descartada:** soft-delete (más reversible, más típico para un
CRUD de administración "de verdad" a largo plazo -- si hace falta
recuperar una cuenta borrada por error, hoy no se puede). Revisar si el
CRUD completo de usuarios (§3 del contrato, aún pendiente) debería migrar a
soft-delete más adelante.

---

## 2026-08-22 — Kanban: fix de fiabilidad del drag-and-drop

**Decisión:** el target del `drop` es la columna entera
(`.kanban-column`), con `preventDefault()` en `dragenter` Y `dragover`
(no sólo dragover), más un `draggedTaskId` en memoria como respaldo de
`dataTransfer.getData`.

**Por qué:** reportado en vivo como fallo intermitente ("a veces no se
puede agregar"). Es un gotcha conocido de la API HTML5 de drag-and-drop:
sin `preventDefault()` en `dragenter`, algunos navegadores rechazan el
drop de forma inconsistente. Ver comentario en `app/static/app.js`.

---

## 2026-08-22 — gamification: alcance de la Fase 10

Pedido del usuario: "sigue hasta el final del desarrollo de Freya." La
Fase 10 del ROADMAP tiene puntos genuinamente ambiguos o abiertos --
decisiones tomadas para poder construir algo real hoy, no quedarme
esperando una aclaración:

**"Expense Rewards" se interpretó como "recompensas que cada persona
define y compra con las monedas que gana"** (`gamification/app/domain/
rewards.py`), no como un rastreador de gastos reales. El nombre del
ROADMAP admite las dos lecturas; la primera encaja con el resto del
sistema (XP → monedas → algo que gastar) sin inventar un dominio nuevo
(categorías de gasto, moneda real, etc.) que nadie más pidió.

**Fórmula de XP: `dificultad_de_la_task * 15`** (`gamification/app/
domain/task_sync.py`). El ROADMAP dice "la XP sale de la dificultad de
las tasks" pero no da la fórmula. `difficulty` en project-manager es
1-5, así que esto da un rango de 15-75 XP por task -- ni trivial ni
desproporcionado frente al umbral de subir de nivel (nivel 2 a 50 XP).

**Curva de nivel: `50 * (nivel-1)²` XP acumulado** (`gamification/app/
domain/leveling.py`). Curva cuadrática clásica de RPG, elegida porque
ninguna fuente en el proyecto especifica una. Nivel 2 a 50 XP, nivel 5 a
800, nivel 10 a 4050 -- fácil de alcanzar los primeros niveles, cada vez
más lento después.

**Catálogo de logros fijo en código** (`gamification/app/domain/
achievements.py`), mismo patrón que `ROLE_PERMISSIONS` de auth -- una
tabla en código, no una API de administración de logros. Nadie pidió
poder crear logros nuevos sin tocar código; construir esa superficie de
administración hoy sería trabajo especulativo.

**Metas sin reinicio automático de periodo**
(`gamification/app/domain/goals.py`): crear una meta calcula
`period_start` una vez, al crearla, y el progreso se recalcula en vivo
desde ahí -- no hay un job que la reinicie sola cuando termina la
semana/mes/año. Construir reinicio recurrente de verdad (¿qué pasa con
una meta no cumplida al terminar el periodo? ¿se archiva sola? ¿se
notifica?) es una decisión de producto que nadie ha tomado todavía;
crear una meta nueva para el siguiente periodo es el escape manual
mientras tanto.

**Sincronización de tasks completadas por poll, no por webhook**
(`gamification/app/domain/task_sync.py`): no existe un bus de eventos en
la plataforma (la única cosa parecida es el webhook git→cicd, específico
de ese caso). Poll cada 15s sobre `GET /projects/{id}/tasks?status=done`
de cada proyecto, deduplicado por `gam_xp_events(source, source_ref)`
-- mismo patrón que `HealthMonitor`/`Scraper` de gestor-monitoring.
Verificado en vivo de punta a punta: completar una task en el panel
real (no con curl a mano) otorga XP, sube de nivel y desbloquea un logro
sin ninguna intervención, en menos de 15 segundos.

---

## 2026-08-22 — Fase 11: qué se construyó y qué queda deliberadamente fuera

El roadmap lista cinco puntos para "Endurecimiento". Se construyó el
único que es una pieza de ingeniería acotada; los otros cuatro son
decisiones de producto/operación que no tiene sentido inventar sin más
contexto -- mejor dejarlos anotados que construir algo arbitrario:

**Construido: rate limiting por tenant en frontend**
(`frontend/app/infra/rate_limit.py`). `SlidingWindowLimiter` se movió de
`auth` a `freya_common` (ya lo usaban dos servicios) y se aplicó como
middleware sobre `/api/*` en el gateway, con clave = tenant
(`X-Tenant-Context`) -- hoy sólo existe el tenant "freya", así que esto
es una única ventana compartida por toda la plataforma; protege el caso
multi-tenant futuro sin inventar todavía un límite por usuario/IP que
nadie ha pedido. Verificado: tráfico normal sigue en 200, `/health` está
exento, test unitario confirma el 429 al superar el máximo.

**Deliberadamente no construido:**

- *Rotación automática de certificados y secretos.* La emisión manual ya
  existe (`.\freya.ps1 renew-cert <servicio>`). Automatizarla de verdad
  necesita un scheduler que no existe en la plataforma (nada corre en
  cron hoy) y decisiones de política real: ¿cada cuánto? ¿reinicia el
  servicio solo tras rotar, con qué ventana de downtime aceptable?
  Construir esto a ciegas, sin esas respuestas, es el tipo de cambio que
  puede tumbar un servicio en producción si se equivoca la ventana de
  reinicio.
- *Backups de storage sobre sí mismo.* Los backups de `database` (Fase 11
  ya adelantada) usan `pg_dump`, un formato con el que la plataforma ya
  sabe trabajar. `storage` guarda los bytes de los objetos en su propio
  filesystem (`/data`), no en una base -- habría que empaquetarlo (tar) y
  subirlo a su propio bucket `backups`, con cuidado real de no incluir el
  propio `backups` en el tar (recursión). Es una pieza real, no
  imposible, pero con una decisión pendiente (¿qué formato, qué
  retención?) que no estaba en el pedido explícito de esta sesión.
- *Auditoría transversal.* No hay bus de eventos ni almacén de auditoría
  centralizado en la plataforma -- "auditoría transversal" implica
  decidir qué se audita, dónde vive, y cuánto se retiene, antes de que
  escribir código tenga sentido.
- *Onboarding de tenants externos.* Ahora mismo `default_tenant` es un
  único valor fijo ("freya") usado en casi todos los sitios -- soportar
  tenants externos de verdad es un cambio de fondo (aislamiento de
  datos, quién puede crear un tenant, cómo se factura o limita cada
  uno), no una feature aislada.

Si el usuario quiere que se construya alguno de estos, la pregunta que
falta responder para cada uno está en su punto de arriba.

---

## 2026-08-22/23 — Migración a GitHub: qué queda preparado, qué falta

Pedido del usuario: "se puede hacer github actions para que deploye en mi
propia pc. Eliminar git, project_manager y ci/cd, usar las de github."
Confirmado por su parte: project-manager se sustituye por GitHub Issues +
Projects (no se queda en paralelo), el runner autoalojado corre en
contenedor, los repos de GitHub no existen todavía (los crea él mismo), y
el orden es levantar el lado de GitHub primero y verificarlo antes de
apagar git/project-manager/cicd.

**Bloqueado por autenticación:** dos tokens de GitHub pegados en el chat
fallaron con `401 Bad Request` contra la API real de GitHub (no un fallo
de `gh` CLI -- probado también con `curl` directo, mismo resultado). El
usuario decidió gestionar el login de GitHub por su cuenta en vez de
seguir pegando tokens.

**Decisión: "deploy" es `git pull` en el propio checkout de este PC, no un
checkout aislado.** `services/github-runner/` monta
`D:\Proyectos\Freya` entero en `/workspace` -- el workflow
(`templates/github-workflow/deploy.yml`) hace `git fetch`/`reset --hard`
sobre el subdirectorio del servicio que cambió, ahí mismo, y luego
`docker compose build/up`. Evita a propósito el problema de que cada
servicio tendría su propio repo de GitHub sin sus hermanos al lado (todos
los Dockerfile de Freya construyen con `context: ..` para poder copiar
`freya-common`) -- publicar `freya-common` como paquete instalable es la
alternativa "correcta" para una CI distribuida de verdad, pero es trabajo
que nadie pidió resolver hoy y que ya se había descartado antes en esta
sesión (ver resumen de la conversación, "3 aún no").

**Construido y verificado (no depende de que la autenticación funcione):**
- `services/github-runner/` -- imagen del runner oficial de
  `actions/runner` (no una imagen comunitaria de terceros), con Docker
  CLI (habla con el Docker Desktop del host via socket montado) y git.
  Corre como root a propósito: el socket de Docker montado ya equivale a
  acceso root al host sea cual sea el UID del proceso, mismo
  razonamiento que ya se aplicó a `traefik`.
- El token de *registro* de un runner caduca en ~1h -- en vez de pedirle
  al usuario uno nuevo cada vez que el contenedor se recree
  (`restart: unless-stopped` puede hacerlo en cualquier momento),
  `entrypoint.sh` pide uno fresco en cada arranque usando un PAT de larga
  duración vía la API de GitHub (`infra/secrets/github-runner/github_pat`).
- `templates/github-workflow/deploy.yml` -- lint + test + security_scan +
  deploy, reproduciendo a mano los mismos pasos que corría el `cicd` que
  se retira (ver `cicd/app/domain/runner.py:_STEP_COMMANDS`). Ya generado
  para los 8 servicios que migran (auth, secrets, storage, gestor-db,
  gestor-monitoring, frontend, gamification, freya-common) en
  `<servicio>/.github/workflows/deploy.yml`, y `infra/scripts/
  new_service.sh` lo genera solo para cualquier servicio nuevo.
- `gamification/app/domain/github_task_sync.py` -- sincroniza XP desde
  Issues cerradas de GitHub en vez de tasks de project-manager. Apagado
  por defecto (`use_github_task_sync=false`); usa un "source" distinto en
  `gam_xp_events` al que usa el sincronizador de project-manager, así que
  activarlo no exige apagar el otro en el mismo instante -- corte seguro.
  **Decisión pendiente de responder, no de código:** GitHub Issues no
  tiene un "asignado" que mapee a un `user_id` de Freya sin construir un
  sistema de vínculo de identidades que nadie ha pedido -- hoy toda la XP
  de GitHub va a un único `github_default_user_id` configurado, razonable
  mientras esta plataforma tenga un solo usuario real. La "dificultad" de
  una task sale de una label `difficulty:N` (N entre 1 y 5) en el issue --
  si el usuario prefiere otra convención (Projects v2 con un campo
  personalizado, por ejemplo), este módulo hay que reescribirlo, no sólo
  reconfigurarlo.

**Actualización 2026-08-23: repo real creado y pipeline verificado
end-to-end.** El usuario creó `Mhiaghi-projects/Freya` (organización) como
monorepo único ("go with mono", confirmado tras preguntar si prefería 7
repos separados). Ver entrada de abajo ("Submódulos fantasma...") para el
bug que impidió que el código de 7 servicios llegara a GitHub durante la
primera mitad de esta migración -- una vez arreglado, push real →
GitHub Actions → runner autoalojado → deploy local se confirmó
funcionando para los 6 servicios afectados (auth, gestor-db,
gestor-monitoring, gamification, frontend, freya-common).

**No construido todavía, a propósito -- depende de decisiones que sólo
puede tomar el usuario:**
- `.env`: `GITHUB_RUNNER_URL`, `GITHUB_OWNER`,
  `GITHUB_GAMIFICATION_REPOS`, `GITHUB_DEFAULT_USER_ID`, y el PAT en
  `infra/secrets/github-runner/github_pat` /
  `infra/secrets/gamification/github_pat` (mismo token sirve para los
  dos, ver el README de la primera carpeta).
- Apagar `git`, `project-manager` y `cicd` -- deliberadamente NO se ha
  tocado ninguno de los tres: siguen funcionando exactamente igual que
  antes, el usuario pidió explícitamente levantar primero el lado de
  GitHub y verificarlo antes de decomisionar nada.
- Las vistas de `frontend` para git/CI-CD/proyectos (`app/api/{git,cicd,
  projects}.py`, `app/static/app.js`) siguen apuntando a los servicios
  viejos -- repuntarlas a la API de GitHub (repos, Actions runs, Issues)
  es trabajo real pendiente, no tiene sentido escribirlo a ciegas sin
  poder probarlo contra la API de GitHub de verdad todavía.

---

## 2026-08-23 — Submódulos fantasma: 7 servicios nunca llegaron a GitHub

**Bug encontrado, no pedido por el usuario.** Al hacer un push de rutina
tras arreglar `deploy-freya-common.yml`, `git add` sobre `auth` falló con
`fatal: Pathspec '...' is in submodule 'auth'`. `git ls-files -s` mostró
que `auth`, `freya-common`, `frontend`, `gamification`, `gestor-db`,
`gestor-monitoring` y `git` estaban registrados como gitlinks (modo
`160000`) en el índice del monorepo raíz -- resto de un `.git` anidado
que cada uno tuvo en la era de git-propio-por-servicio. Esos `.git`
anidados ya se habían borrado (con permiso explícito, antes en esta
sesión), pero el índice del repo raíz seguía apuntando a ellos como
submódulo opaco. Sin `.gitmodules`, así que ni siquiera se comportaban
como un submódulo real -- simplemente cualquier `git status`/`add`/`diff`
ignoraba en silencio TODO cambio dentro de esos 7 directorios, desde que
el monorepo se creó.

**Impacto real:** todo el trabajo de esta sesión dentro de esos 7
directorios -- la construcción completa de `frontend`, `gamification`
entero, el rediseño de roles de `auth`, el fix de `freya.health.scheme`
de `gestor-monitoring` -- nunca llegó a GitHub pese a que `git commit`/
`git push` en la raíz parecía funcionar (esos commits sólo tocaban
archivos fuera de los 7 directorios afectados).

**Arreglo:** `git rm --cached <7 dirs>` + `git add <7 dirs>` -- sin
`.git` anidado que reintroducir, se re-registran como árbol normal de
archivos. Commit `60637b5` (213 archivos, 13262 inserciones), push
exitoso. Disparó 6 workflows de deploy en paralelo (uno por servicio
afectado con cambios reales) -- primera vez que el código real de esos
7 servicios se despliega vía GitHub Actions.

---

## 2026-08-23 — Traefik: límite de memoria (128M) demasiado ajustado para su propio healthcheck

**Bug encontrado durante la verificación del batch de 6 deploys de
arriba, no pedido por el usuario.** `freya-traefik` llevaba 168 chequeos
de salud fallidos seguidos -- prácticamente desde que arrancó el
contenedor (2 horas antes), con el mensaje "timed out starting health
check". `docker exec freya-traefik echo hi` (el exec más simple posible,
sin relación con el healthcheck en sí) también se quedaba colgado
indefinidamente -- Docker no lograba ni arrancar un proceso nuevo dentro
del contenedor.

**Causa real:** `traefik healthcheck --ping` no es una llamada IPC al
proceso Traefik ya corriendo -- es un binario Go *nuevo* por cada
chequeo, con su propio arranque de runtime. El proceso base de Traefik
ya usaba ~96MiB de los 128MiB del límite (`deploy.resources.limits.
memory`) -- 75% ocupado en reposo. Sin margen real, el fork para ese
proceso nuevo se queda esperando memoria bajo el `memory.max` de cgroup
v2 (que puede estancar el proceso en vez de matarlo si el kernel cree
que hay memoria reclamable en otro sitio) -- de ahí el "colgado" en vez
de un error inmediato.

**Arreglo:** subir el límite de `services/traefik/docker-compose.yml` de
128M a 256M (mismo valor que ya usan otros servicios como `git` y
`gestor-db`). Redeploy manual (`docker compose --project-name freya -f
services/traefik/docker-compose.yml up -d`) confirmó healthy de
inmediato; el enrutado hacia `frontend` se verificó seguir funcionando
igual. No estaba en el batch de 6 servicios que dispararon workflows de
GitHub Actions -- el cambio en el compose todavía no está commiteado por
un push real, sólo aplicado en vivo en este host, pendiente de commit.

**Nota relacionada, no arreglada:** `freya-storage` se observó al 91.8%
de su límite de 256M (235MiB) durante la misma verificación, con el
mismo patrón de healthcheck basado en un proceso Python nuevo por
chequeo. Se recuperó solo (no llegó a acumular un streak de fallos como
Traefik) y no formaba parte de este batch de deploys, así que no se tocó
-- si vuelve a flaquear, aplicar el mismo diagnóstico.

---

## 2026-08-23 — Auditoría completa del proyecto: ~30 bugs reales corregidos

Pedido explícito del usuario: "haz todo lo que necesites y puedas hacer...
Necesito que te fijes en la seguridad." Auditoría en paralelo (5 agentes,
lectura completa de cada servicio, sin tocar código) sobre los 11
servicios Python del monorepo, seguida de corrección uno por uno y
verificación (lint + pytest limpios en los 11, stack completo
redesplegado y sano).

**Hallazgos de mayor impacto** (ver el comentario junto a cada fix para
el detalle exacto):
- `auth`: bypass real de aislamiento por tenant -- `admin_principal`/
  `user_principal` (`app/deps.py`) sólo comprobaban `role`, nunca
  `tenant_id` del JWT contra `X-Tenant-Context`. Un token admin de un
  tenant servía igual de bien contra cualquier otro.
- `storage`: IDOR en `get_object_metadata` (un `versionId` de otro objeto
  no se validaba contra el `object_id` del recurso pedido); `DELETE
  ?force=true` de un bucket no borraba objetos/blobs de verdad, dejándolos
  reaparecer si el nombre del bucket se reutilizaba.
- `cicd`: una excepción inesperada del runner dejaba `ci_runs` en
  "running" para siempre, sin forma de saber que la ejecución murió.
- `project-manager`: arrastrar una task a otra columna en un punto
  concreto descartaba la posición pedida (siempre al final).
- `freya-common`: cualquier JWT inválido/vencido forzaba un fetch en vivo
  del JWKS contra `auth`, anulando de hecho el cacheado de 10 min
  documentado en `docs/ARCHITECTURE.md` §7; el rate limiter no purgaba
  nunca claves vistas una sola vez (fuga de memoria proporcional a IPs/
  tenants vistos en la vida del proceso).
- `secrets`: borrar la versión "actual" de un secreto dejaba
  `current_version` apuntando a una versión ya borrada, bloqueando toda
  lectura por defecto aunque quedaran versiones anteriores válidas.
- `gamification`: achievements/goals sub-contaban tareas completadas --
  cada sincronizador (project-manager, GitHub Issues) sólo veía su propia
  fuente en `gam_xp_events`.

**No arreglado, a propósito, documentado en su lugar:**
- `storage`: el flag `encryption` de un bucket se acepta y guarda pero no
  cifra nada -- implementar cifrado real en reposo es una pieza de
  seguridad que merece su propio diseño (gestión de claves, rotación), no
  un efecto colateral de un barrido de bugs. Ver `storage/README.md`.
- `auth`: no hay forma de desactivar un usuario o cambiarle el rol sin
  borrado duro -- gap de funcionalidad, no bug; nadie lo ha pedido
  todavía.

Commit `f952c9f` (39 archivos). Detalle completo de cada hallazgo, con
archivo/línea y escenario de fallo concreto, en el historial de esta
conversación -- los comentarios junto a cada fix en el código son la
referencia permanente.

---

## 2026-08-23 — Pipeline de deploy: dos jobs, no uno (check en GitHub, deploy en el PC)

**Pedido del usuario:** "haz que el primer runbook se ejecute en github
aprovechando todas las funciones de github como check code, y luego se
ejecute el pipeline que deploya en mi pc."

**Decisión:** cada `deploy-<servicio>.yml` pasa de un job único (todo en
el runner autoalojado, incluido lint/test/security_scan) a dos jobs
encadenados con `needs:`:
1. `check` -- en `ubuntu-latest` (runner de GitHub, efímero, gratis para
   este repo público). `actions/checkout` real, build de la imagen `dev`,
   lint, test, `pip-audit`. Nunca toca el PC del usuario.
2. `deploy` -- sólo arranca si `check` pasó. Sigue en el runner
   autoalojado (`services/github-runner/`), ahora sólo hace `git fetch` +
   `reset --hard` y `deploy-service.sh`.

**Por qué:** antes, lint/test/security_scan corrían en el mismo runner
autoalojado que hace el deploy -- "CI" de nombre, pero en la práctica
todo ejecutaba en el propio PC del usuario, incluido código que podía
estar roto. Con `needs: check`, código que no pasa esas comprobaciones
JAMÁS llega a construirse ni ejecutarse localmente; las comprobaciones en
sí corren en infraestructura desechable de GitHub.

**También activado (funciones nativas de GitHub, gratis en un repo
público, vía API -- `gh api -X PATCH repos/.../ --f security_and_analysis...`):**
secret scanning + push protection (rechaza un push con un secreto
reconocible antes de que exista en el historial), Dependabot security
updates (PR automático al publicarse un CVE de una dependencia usada).
Nuevos: `.github/workflows/codeql.yml` (análisis semántico del código
propio -- inyección, path traversal, etc. -- en cada push y semanalmente)
y `.github/dependabot.yml` (PR semanal de versiones desactualizadas, uno
por servicio). Ninguno de estos bloquea el job `deploy` hoy -- acoplar el
deploy a CodeQL exigiría esperar un workflow aparte (`workflow_run`), más
complejidad de la que pide un repo de un solo desarrollador real; revisar
alertas queda manual por ahora.

**También añadido:** `workflow_dispatch: {}` en cada workflow -- permite
re-lanzar el mismo commit desde la pestaña Actions sin necesitar un push
nuevo (botón "Run workflow").

Plantilla actualizada en `templates/github-workflow/deploy.yml` (para que
`infra/scripts/new_service.sh` genere el patrón de dos jobs automáticamente
en cualquier servicio nuevo); los 8 workflows existentes regenerados desde
ella. Detalle operativo completo -- cómo verificar un deploy, redesplegar
sin cambio de código, el patrón de "unhealthy transitorio" bajo carga,
rollback -- en `docs/RUNBOOK.md`, nuevo.

**No tocado, a propósito:** `git`, `project-manager`, `cicd` siguen sin
workflow propio -- decisión ya tomada de no migrarlos a GitHub Actions
hasta decomisionarlos (ver entrada de migración a GitHub arriba).

---

## 2026-08-23/24 — Normalización e índices: auditoría de los 8 esquemas, 4 índices reales añadidos

Pedido del usuario: "necesito que apliques normalización, índices a la
tabla de base de datos."

**Normalización -- revisada, sin cambios.** Se leyeron los 12 ficheros de
migración de los 8 servicios con esquema propio (auth, cicd, gamification,
gestor-monitoring, git, project-manager, secrets, storage). Todas las
tablas usan una clave primaria de una sola columna (id con prefijo tipo
ULID) -- descarta por construcción cualquier dependencia parcial (2FN
trivialmente satisfecha) -- y no se encontró ninguna columna que dependa
de otra columna no-clave en vez de la clave primaria (sin violaciones de
3FN). Los casos que a primera vista parecen redundancia son patrones
deliberados y correctos, no bugs:
- Columnas `text[]` (`service_accounts.permissions`, `users.
  extra_permissions`, `pm_tasks.labels`, `pm_projects.team_members`):
  atributos genuinamente multivaluados donde asyncpg liga el array nativo
  sin codec aparte -- partirlos en tablas de unión no aportaría nada hoy.
- `gam_reward_redemptions.coin_cost` duplica `gam_rewards.coin_cost`: es
  el patrón estándar de "precio en el momento de la transacción" (igual
  que `order_items.price` en cualquier tienda) -- si el precio de la
  recompensa cambia después, el historial de canjes no debe cambiar con
  él. Quitar la columna sería el error, no dejarla.
- `secrets.current_version` / `storage_objects.current_version_id`:
  puntero materializado a la versión vigente en vez de calcularlo con
  `MAX(version)` en cada lectura -- denormalización deliberada por
  rendimiento, el mismo patrón en los dos servicios. (La versión anterior
  de `secrets.current_version` SÍ tenía un bug real de sincronización al
  borrar -- ver la entrada de la auditoría de arriba -- pero el patrón en
  sí es correcto, ya arreglado.)
- Ningún servicio referencia con FK las tablas de otro (p.ej.
  `gam_xp_events.user_id` no referencia `auth.users`): decisión ya
  documentada en el propio esquema -- cada servicio confía en el JWT, no
  en una FK cruzada a un schema que además puede no ser visible desde su
  propia conexión.

**Índices -- 4 añadidos, verificados contra patrones de consulta reales
(no especulativos).** Se revisó cada FK y columna filtrada por `WHERE` en
el código Python de cada servicio antes de añadir nada -- un índice sin
consulta real que lo use sólo añade coste de escritura sin beneficio.
Candidatos descartados tras verificar que ningún query los usa hoy:
`gam_reward_redemptions.reward_id`/`user_id` (tabla sólo de inserción,
sin endpoint de historial todavía), `ci_pipelines.service` (list_pipelines
no filtra por service), `pm_task_dependencies.depends_on_task_id`
(sólo se consulta por `task_id`, ya cubierto por ser la columna líder de
la PK compuesta), `secret_versions.data_key_id` (se usa como valor para
buscar en `secret_data_keys` por su propia PK, no como filtro).

Añadidos, cada uno con un `WHERE`/`ON DELETE CASCADE` real detrás:
- `auth/migrations/0004_refresh_tokens_user_idx.sql` --
  `refresh_tokens.user_id`: sin FK indexada, cada `delete_user` (borrado
  duro real) obligaba a un recorrido completo de la tabla para resolver
  el `ON DELETE CASCADE`.
- `project-manager/migrations/0002_missing_indexes.sql` --
  `pm_milestones.project_id` (`list_milestones`), `pm_sprints.project_id`
  (`list_sprints`), `pm_tasks.assigned_to` (`list_tasks?assigned_to=`).

Verificado en la base viva: `pg_indexes` confirma los 4 creados;
`EXPLAIN` con `enable_seqscan=off` confirma que el planner los usa
correctamente (`Index Scan` con `Index Cond` sobre la columna esperada).
Sin forzar eso, el plan por defecto hoy es `Seq Scan` en las cuatro --
correcto y esperado: con un puñado de filas por tabla (despliegue
personal, no producción a escala), el propio Postgres decide que
recorrer la tabla entera es más barato que la vuelta extra del índice.
El índice empieza a ganar solo, sin ningún cambio de código, en cuanto
el volumen de filas lo justifique -- no hace falta "activarlo" luego.
