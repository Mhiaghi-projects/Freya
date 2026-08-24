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

---

## 2026-08-24 — Vulnerabilidades comunes + optimización de RAM

Pedido del usuario: "haz una lista de las vulnerabilidades mas comunes y
protege a Freya. Tambien optimizalo a mas no poder. Toda me cuesta 1.36 GB
ram."

**Vulnerabilidades revisadas (OWASP Top 10), con lo ya arreglado en
sesiones anteriores marcado como tal:**
- A01 Broken Access Control -- bypass real de tenant en `auth` e IDOR en
  `storage`, arreglados en la auditoría de bugs (ver entrada de arriba).
- A02 Cryptographic Failures -- argon2 (contraseñas), AES-256-GCM real
  con envelope encryption (secretos), RS256 fijado en JWT, cookies
  httponly+secure+samesite=lax. Ya revisado, sin hallazgos nuevos.
- A03 Injection -- SQL siempre parametrizado, identificadores contra
  regex estricta; subprocess siempre en forma de lista, nunca
  `shell=True`; sin `eval`/`exec`/`pickle` en todo el repo. Ya revisado.
- A05 Security Misconfiguration -- **dos hallazgos nuevos reales, ambos
  arreglados hoy** (detalle abajo): sin cabeceras de seguridad en ninguna
  respuesta, y `frontend` exponía `/api/v1/docs`+`/openapi.json`
  públicamente (único servicio alcanzable desde fuera).
- A06 Vulnerable Components -- `pip-audit` en cada `check` de CI +
  Dependabot security updates (activado por API, ver entrada del
  runbook) + Dependabot version updates semanales. Ya cubierto.
- A07 Auth Failures -- rate limiting en sign-in/sign-up/authenticate-
  service, refresh tokens con revocación de familia ante reuso. Ya
  arreglado (sign-up) en el repaso de seguridad anterior.
- A08 Software/Data Integrity -- pipeline de dos fases (check en GitHub
  antes de tocar el PC), migraciones con checksum (rechaza reaplicar un
  fichero con contenido distinto), CodeQL semanal. Ya cubierto.
- A09 Logging Failures -- logs de acceso con request_id/tenant/caller,
  historial de health checks. No hay un log de eventos de seguridad
  aparte (intentos de login fallidos no se marcan de forma especial más
  allá del log de acceso genérico) -- gap real pero menor, no construido
  hoy: nadie lo ha pedido y es una pieza nueva, no un fix.
- A10 SSRF -- `git_repositories.github_mirror_url` se guarda pero nunca
  se hace fetch de él en el servidor; ningún endpoint acepta una URL de
  terceros para pedirla server-side. Ya revisado.

**Arreglado hoy -- A05:**
- `freya-common/freya_common/security_headers.py` (nuevo):
  `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy: no-referrer`, `Strict-Transport-Security`, y una
  `Content-Security-Policy` estricta (`default-src 'self'`, sin
  `unsafe-inline`/`unsafe-eval` -- seguro porque `frontend` no usa
  scripts ni estilos inline en ningún sitio, confirmado leyendo
  `index.html` y `app.js`). Universal en los 10 servicios vía
  `create_app()`, registrado como la más externa de las dos
  BaseHTTPMiddleware (Security fuera de Envelope) para que sobreviva al
  reenvuelto de una respuesta JSON.
- `create_app(..., expose_docs: bool = True)`: `frontend` es el único de
  los 10 servicios alcanzable desde fuera (vía Traefik) -- antes,
  `/api/v1/docs`+`/openapi.json` regalaban el mapa completo de rutas
  internas (admin, storage, git, cicd...) a cualquiera sin credencial,
  puro reconocimiento gratis. `frontend/app/main.py` ahora pasa
  `expose_docs=False`; los otros 9 (sin puerto publicado, sólo
  alcanzables desde dentro de freya-mesh) se quedan como estaban --
  seguirlos usando para depurar en local no cuesta nada ahí.

**No tocado, a propósito:** imágenes base (`python:3.12-slim`) sin fijar
a un digest concreto. Fijar a un `@sha256:...` da reproducibilidad exacta
pero exige actualizarlo a mano para recibir parches de seguridad del
propio SO -- con Dependabot ya vigilando dependencias Python y `apt`
dentro de la imagen slim recibiendo parches al reconstruir, fijar el
digest cambiaría un riesgo (imagen movediza) por otro (parches de SO que
dejan de llegar solos) sin que nadie lo esté pidiendo.

**Optimización de RAM.** `docker stats` con la plataforma entera arriba:
~1.45 GiB reales repartidos en 16 contenedores, ninguno con fugas
obvias salvo uno muy concreto:

- **`storage`: 255.8/256 MiB (99.9% de su límite), con VmSwap real (~84
  MiB) y VmHWM en 284 MiB.** Causa raíz encontrada, no adivinada:
  `PUT`/`GET` leían el objeto ENTERO en memoria de golpe
  (`await request.body()` en la subida, `path.read_bytes()` en la
  bajada) antes de tocar la red o el disco -- con un objeto grande (tope
  hoy: 50 MiB), el pico de RSS se dispara y CPython/glibc no le
  devuelven esa memoria al SO después, así que el proceso se queda
  "marcado en alto" para siempre aunque vuelva a servir peticiones
  pequeñas. Mismo patrón de fondo que el fix de memoria de `traefik` de
  ayer (healthcheck sin margen), pero aquí la causa era la propia lógica
  de la aplicación, no el límite del contenedor.

  **Arreglo real, no un parche:** `storage/app/domain/blob_store.py`
  reescrito para streaming de verdad -- `write()` recibe un
  `AsyncIterator[bytes]` (`request.stream()` de FastAPI) y escribe en
  trozos de 1 MiB, calculando el sha256 de forma incremental
  (`hashlib.sha256().update()` por trozo) en vez de sobre el buffer
  entero; `read()`/`read_range()` son generadores async que leen del
  disco en trozos de 1 MiB, servidos con `StreamingResponse` en vez de
  `Response(content=...)`. El pico de memoria de una petición pasa a ser
  ~1 MiB, sea cual sea el tamaño real del objeto. Efecto colateral de
  seguridad, no sólo de rendimiento: el tope de 50 MiB (`max_bytes`)
  ahora se aplica byte a byte MIENTRAS se escribe, no sólo contra la
  cabecera `Content-Length` -- antes, un cliente con `transfer-encoding:
  chunked` y sin esa cabecera (o mintiendo en ella) podía hacer que el
  servidor bufferizara un cuerpo sin límite real antes de rechazarlo.
  30/30 tests de `storage` pasan (incluida cobertura nueva del corte por
  `max_bytes` a mitad de escritura, y que no deja un fichero parcial
  atrás).

- **`MALLOC_ARENA_MAX=2` en los 10 servicios Python.** glibc crea una
  arena de malloc por hilo por defecto, lo que puede inflar el RSS de un
  proceso async con I/O en threadpool (asyncpg, `asyncio.to_thread` del
  streaming de arriba) sin que haya ningún leak real detrás --
  mitigación estándar y de coste cero para contenedores Python, no algo
  específico de Freya.

- **`services/github-runner/docker-compose.yml`: límite de memoria real
  (768M), antes sin ninguno.** Era el único servicio de la plataforma
  sin techo -- en uso real mide ~210 MiB (el propio proceso .NET del
  runner + git/bash/curl), 768M da margen sin dejarlo abierto de par en
  par. Nota real: esto NO acota los `docker build`/`docker compose
  build` que el runner dispara -- son Docker-outside-of-Docker (hablan
  con el daemon del HOST por el socket montado), así que ese trabajo
  corre fuera del cgroup de este contenedor pase lo que pase.

**Considerado y descartado, con motivo:** apagar `git`/`project-manager`/
`cicd` para ahorrar sus ~180 MiB combinados -- `frontend` todavía no
repunta sus vistas de git/CI-CD/kanban a la API de GitHub (gap ya
documentado en la entrada de migración a GitHub), y `project-manager` en
concreto tiene datos reales en uso (`gamification` sincroniza XP desde
ahí). Apagarlos ahora rompería funcionalidad real que el usuario sigue
usando, no es optimización -- sería regresión disfrazada de ahorro.

---

## 2026-08-24 — Más allá de OWASP: API Security Top 10, Trivy, CIS Docker Benchmark

Pedido del usuario: "además de OWASP, que más podrías agregar? ... hazlo
todo, cuando acabes apagas."

**OWASP API Security Top 10** (distinto del Top 10 web general -- pensado
para APIs REST como las de Freya). Repaso categoría por categoría:
- API1 BOLA -- ya cubierto (IDOR de `storage` en la auditoría de bugs,
  `_check_namespace` en `secrets` confirmado en las 9 rutas).
- API3 Broken Object Property Level Auth -- confirmado que
  `_PROFILE_FIELDS` de `auth` nunca incluye `password_hash`; los
  modelos Pydantic de creación nunca aceptan `id` del caller (siempre
  `new_id()` server-side).
- **API4 Unrestricted Resource Consumption -- hallazgo real, arreglado.**
  `POST /pipelines/{id}/trigger` de `cicd` no tenía ningún límite:
  cada disparo hace un `docker build` + `docker run` de verdad
  (`runner.run_standard_tests`), y nada impedía N triggers simultáneos
  lanzando N builds a la vez -- el mismo patrón de contención que ya
  causó horas de "unhealthy transitorio" esta sesión, pero aquí
  disparable a demanda por cualquiera con `write:cicd`. Arreglo:
  `cicd/app/domain/runs.py` gana un `asyncio.Semaphore(2)` real (no sólo
  una ventana de tiempo, que no habría evitado que 2 triggers
  simultáneos se solaparan) -- la fila de `ci_runs` ahora pasa por
  `queued` de verdad mientras espera un hueco, con un tope de espera de
  5 min antes de fallar con un error claro.
- API5 Broken Function Level Auth -- escaneado programáticamente: cada
  ruta de los 8 servicios no-auth tiene `require_permissions`/`AdminDep`/
  `UserDep`; las únicas rutas sin gate son las de `auth` que por
  definición no pueden tenerlo (sign-in, sign-up, refresh-token,
  jwks.json...).
- API7 SSRF, API9 Improper Inventory -- ya revisados en el repaso de
  seguridad anterior.
- API10 Unsafe Consumption of APIs -- revisado
  `gamification/app/domain/github_task_sync.py`: sólo lee `labels`
  (regex estricta `^difficulty:([1-5])$`) y el número de issue de la
  respuesta de GitHub; nunca lee ni guarda el título ni el cuerpo del
  issue, así que no hay vector de XSS almacenado aunque `frontend`
  llegara a mostrar datos de GitHub sin escapar en el futuro.

**Escaneo de imagen (Trivy)** -- complementa a `pip-audit`, que sólo mira
dependencias Python: Trivy escanea la imagen `runtime` completa
(incluido `python:3.12-slim` y sus paquetes `apt`, que `pip-audit` nunca
ve). Nuevo paso en `templates/github-workflow/deploy.yml` (y los 8
workflows regenerados desde ella): construye la imagen `runtime` de
verdad (no la `dev` que ya se escanea con pip-audit) y falla el job
`check` sólo en `CRITICAL` con parche disponible
(`ignore-unfixed: true`) -- bloquear en `HIGH` o en CVEs sin parche
convertiría el pipeline en un muro sin salida. `freya-common` queda
excluido de este paso a propósito: no tiene etapa `runtime` (nunca se
despliega como contenedor propio), así que no hay imagen que escanear.

**CIS Docker Benchmark 5.28 (límite de PIDs)** -- ningún
`docker-compose.yml` de los 10 servicios propios tenía `pids` fijado:
sin él, nada frena un fork-bomb dentro de un contenedor si alguna vez
apareciera una vulnerabilidad que permitiera lanzar procesos arbitrarios.
Añadido en `deploy.resources.limits.pids` de los 10 (128 para los 7
servicios FastAPI puros; 256 para `git`/`cicd`, que sí lanzan
subprocesos reales con más profundidad -- `git`, y `docker build`/`docker
run` respectivamente). Nota técnica encontrada en vivo: el campo
"pids_limit" de nivel de servicio y "deploy.resources.limits.pids" son,
para Docker Compose, el mismo ajuste bajo dos nombres -- con un bloque
`deploy:` ya presente (los 10 lo tienen, para cpu/memoria), fijar
`pids_limit` aparte hace que `docker compose config` rechace el fichero
entero ("can't set distinct values"). Van siempre juntos bajo
`deploy.resources.limits`, nunca como campo de servicio aparte.

**Resto del CIS Docker Benchmark, revisado sin cambios:** `no-new-
privileges`, `cap_drop: ALL`, `read_only: true`, límites de cpu/memoria
y usuario no-root ya estaban en los 10 servicios propios desde antes.
Las imágenes de terceros (Postgres, Grafana, VictoriaMetrics, Loki,
Traefik) no tienen el mismo nivel de endurecimiento por motivos ya
razonados (necesitan escribir su propio directorio de datos, o en el
caso de Traefik podrían necesitar una capability para el puerto 443) --
no se ha tocado nada ahí en esta pasada.

**Peligro real repetido durante este mismo trabajo:** el runner
autoalojado, arrancado para drenar la cola de CI pendiente, hizo `git
reset --hard origin/main` sobre este mismo directorio MIENTRAS se
escribían los cambios de arriba -- se perdieron dos ediciones sin
commitear (el fix de `cicd` y la plantilla de Trivy) y hubo que
rehacerlas. Confirma en vivo la advertencia ya escrita en
`docs/RUNBOOK.md`: no dejar el runner corriendo mientras hay cambios
sueltos en el árbol de trabajo.

---

## 2026-08-24 — RAM, segunda pasada: el propio error de operación, no código

Pedido del usuario: "optimiza Freya al maximo. Debe consumir la minima
RAM posible" (repetido tras la pasada de `storage`/`MALLOC_ARENA_MAX` de
antes).

**Hallazgo real, no de código sino de operación:** al levantar la
plataforma de nuevo tras el apagado, un `docker start` general incluyó
`freya-dashboards` (Grafana) -- pero `services/dashboards/docker-
compose.yml` lo documenta explícitamente como "apagado por defecto"
(ROADMAP.md mon-07, `profiles: [dashboards]`, sólo se levanta con `.
\freya.ps1 up dashboards`, que añade el profile a mano). `docker start`
opera sobre un contenedor YA CREADO sin mirar profiles en absoluto, así
que el opt-out del propio diseño no protegió nada aquí -- Grafana quedó
corriendo por un `docker start` genérico, no por decisión de nadie.
Estaba consumiendo 209.5/220 MiB, con diferencia el mayor consumidor de
toda la plataforma después del arreglo de `storage`. Parado
(`docker stop freya-dashboards`) -- recuperable en cualquier momento con
`.\freya.ps1 up dashboards` cuando de verdad haga falta ver un panel.

**Revisado y descartado, con motivo, antes de tocar nada:**
- Límites del pool de `httpx` (`freya_common/http.py`,
  `max_connections=32`) -- httpx no reserva conexiones por adelantado,
  sólo abre hasta el tope bajo carga real; bajarlo no reduciría memoria
  ya en uso hoy, sólo el techo bajo concurrencia, que este platform no
  alcanza en la práctica.
- Pool de asyncpg de `gestor-db` (`pool_max_size=10`) -- cada conexión
  extra sólo se abre bajo demanda (arranca en `pool_min_size=2`), y
  bajarlo arriesgaría contención justo en el escenario que más ha costado
  esta sesión: varios servicios redesplegando/consultando a la vez
  durante una tanda de CI. El ahorro de memoria sería marginal frente al
  riesgo de reintroducir el propio patrón de "unhealthy transitorio" que
  ya se investigó a fondo.
- `services/database/docker-compose.yml` -- ya afinado desde una sesión
  anterior (`db-03`: `shared_buffers=64MB`, `work_mem=4MB`,
  `max_connections=40`, objetivo explícito "quedarse bajo 256 MB en
  reposo"). En uso real: 46 MiB. Nada que mejorar aquí hoy.
- `metrics`/`logs` (VictoriaMetrics/Loki) -- ya muy por debajo de su
  límite (45 MiB / 160M y 3 MiB / 160M) sin tocar nada. Ningún Dockerfile
  usa `--reload` (que añadiría un proceso vigía de ficheros); todos usan
  `uvicorn[standard]`, que ya trae `uvloop` -- sin margen real ahí.

**Total con la plataforma completa arriba (los 14 servicios que corren
siempre, sin `dashboards` ni `github-runner`, este último sólo activo
mientras hay CI en curso):** ~703 MiB, frente a los ~1.36-1.45 GiB
reportados por el usuario al empezar este tramo de optimización -- caída
de aproximadamente un tercio a la mitad, la mayor parte gracias al
streaming real de `storage` (~200 MiB) y a no dejar Grafana corriendo por
error (~210 MiB).
