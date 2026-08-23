# Freya

Plataforma de servicios autoalojada. Doce servicios que se apoyan unos en otros:
identidad, secretos, almacenamiento, versionado, gestión de proyectos, CI/CD,
monitorización y gamificación, todo bajo el mismo techo y consumido por la
propia plataforma.

Freya es multi-tenant: se usa a sí misma bajo el tenant `freya` y presta los
mismos servicios a proyectos externos bajo sus propios tenants.

## Estado

**Fase 2 — `auth` completa, migrada a [`docs/freya-api-contract.md`](docs/freya-api-contract.md).**
Ese documento es ahora la fuente de verdad del contrato de API — sustituye
lo que `docs/CONVENTIONS.md` decía sobre cabeceras, sobre de respuesta,
catálogo de errores y auth. `database` y `gestor-db` (Fase 1) migrados:
`gestor-db` expone el DSL estructurado de `/query`, `/mutate`,
`/transaction` (§4) en vez de SQL crudo, valida JWT RSA y cruza el `service`
del token contra `X-Service-Name` (nunca se fía de la cabecera sola).
`auth` firma JWT RSA (no EdDSA), publica JWKS, autentica servicios
(`POST /authenticate/service`) y usuarios (`/api/v1/auth/sign-up`,
`sign-in`, `refresh-token`, `sign-out`), con Argon2id, refresh rotativo con
revocación de familia, y permisos derivados del rol (`user`/`admin`). IDs
con prefijo tipo ULID (`usr_...`, `sva_...`) en vez de UUIDv7 puro. Retorno
completado: `gestor-db` rechaza el token de bootstrap y sólo acepta JWT
válidos de `auth` — ambos servicios se autentican mutuamente por HTTPS.

**Fase 3 — `secrets` (núcleo completo).** Vault con envelope encryption
AES-256-GCM: una master key en fichero monta una DEK por tenant, cifrada en
la base — la base robada no revela nada sin la master key. CRUD de secretos
versionado (`/secrets/{namespace}/{key}`), rotación, auditoría de cada
acceso. Verificado: el valor nunca está en claro en la base, `overwrite:
false` rechaza duplicados, versiones antiguas siguen siendo legibles tras
rotar.

Pendiente, sin bloquear lo siguiente: CA interna (emisión/renovación de
certificados de servicio, sustituyendo la CA de desarrollo), retorno de
`gestor-db`/`auth` para pedir sus credenciales a `secrets` en vez de leerlas
de ficheros montados, introspección/revocación de access token de `auth`
con propagación &lt;60s, auditoría de identidad persistida, CRUD completo
de administración de usuarios (`/auth/admin/*`), MFA, forgot/reset-password
— el contrato define mucha más superficie (storage, git, project-manager,
ci/cd, gamification, monitoring, webhooks, automation) de la que se ha
construido todavía.

**Fase 4 — `storage` completa.** Objetos versionados: bytes en un volumen
con nombre (`/data`), metadatos —buckets, objetos, versiones— en
`gestor-db` como cualquier otro dato de Freya. `PUT`/`GET`/`HEAD`/`DELETE`
por `key`, `Range` para descargas parciales (`206`), versionado por
bucket (archiva la versión anterior en vez de sobrescribirla), cuotas por
bucket con checksum SHA-256 como `ETag`. Verificado en vivo de punta a
punta con el servicio ya desplegado: crear bucket, subir dos versiones de
un objeto, descargar por rango, leer la versión antigua, listar versiones
y objetos, ver el uso del bucket, borrar objeto y bucket — 22
comprobaciones, todas en verde, usando el mismo circuito JWT que
cualquier otro servicio autenticado (el que usaría `auth` u otro
consumidor).

Pendiente: subida multiparte, restaurar una versión antigua como vigente,
`/storage/usage` agregado por tenant, y la cascada de retención de
`max_versions` (queda para el futuro servicio de automatización,
`storage_lifecycle`, §13.5 del contrato).

**Fase 5 — `git` (núcleo completo).** Envuelve el binario real de git
(`git http-backend`, nunca reimplementado): protocolo smart HTTP real
(`git clone`/`fetch`/`push` desde un cliente git estándar) más la API de
lectura/gestión de repos, branches, tags, commits, diff y árbol de
ficheros (docs/freya-api-contract.md §6). El contenedor no guarda estado
propio: cada repo son 2-3 objetos (un packfile + un snapshot de refs) en
el bucket `git` de storage, materializados bajo demanda en un directorio
efímero para operar con git de verdad y persistidos de vuelta tras cada
push. Verificado en vivo con un cliente git real: crear repo, clonar
vacío, dos commits y dos `push`, clonar de nuevo con los bytes íntegros,
listar branches/commits, crear y listar una tag anotada, diff, árbol de
ficheros, borrar — 22 comprobaciones, repetidas dos veces para descartar
estado que sólo funcionara "la primera vez". En el camino salieron dos
bugs reales: la advertencia de rama por defecto de un repo vacío necesita
reenviar la cabecera `Git-Protocol` como variable CGI (si no, un `git
clone` de un repo nuevo cae al `master` local del cliente en vez de
`main`), y subir un blob JSON a storage con `Content-Type:
application/json` atravesaba el `EnvelopeMiddleware` genérico de storage y
quedaba doblemente envuelto — arreglado de raíz en `storage` (marca su
`Response` de descarga con `X-Freya-No-Envelope`, que el middleware
respeta pase lo que pase el content-type), no con un workaround en `git`.

Pendiente: la política de retención de 5 commits + espejo bidireccional a
GitHub (git-05, git-06 — el criterio de salida completo de la fase),
marcado de repos sensibles para excluirlos del push a GitHub (depende de
lo anterior), webhooks de push firmados, validación anti-secretos en push,
`blame` y `deployment-history`. Sin caché de refs todavía: cada lectura
rematerializa el repo entero desde storage.

**Fase 6 — `project-manager` (núcleo completo).** Backlog de Freya:
proyectos, tasks, Kanban con columnas por proyecto (no un enum global),
milestones, sprints, esfuerzo y vínculo a commits de `git`
(docs/freya-api-contract.md §7). Sin dependencia de `storage` ni `git`:
sólo gestor-db, como cualquier servicio de datos. Dos extensiones sobre el
contrato que ROADMAP.md exige explícitamente: `difficulty` (1-5, la misma
escala que ya usan `projects/*.yaml` en este repo) y `acceptance_criteria`
por task; `estimated_hours` se deriva de la dificultad si no se da
explícita. Una task con dependencias sin completar no puede avanzar más
allá de `backlog`/`todo` — verificado moviendo una task bloqueada (`409`)
y la misma task tras completar su dependencia (`200`). El progreso de un
milestone se calcula por la dificultad de sus tasks, no por su recuento
(ROADMAP.md pm-05, literal). El backlog de la propia Freya ya vive dentro
de Freya: `.\freya.ps1 import-backlog` importó los 12 `projects/*.yaml` y
sus 92 tasks por la propia API REST del servicio (sin lógica de
importación dentro del servicio — el script vive en `infra/scripts/`,
mismo principio que cualquier otra orquestación de `infra/`), con
dificultad y criterio de aceptación correctos y las dependencias entre
tasks del mismo proyecto resueltas de verdad.

Pendiente: `freya_access_enabled` (crear tenant + cuenta de servicio +
secreto al crear un proyecto — cruza `auth`/`secrets`/`gestor-db`, merece
su propio diseño), integración iCloud y diseños de electrónica (ninguna
tiene sentido sin la integración externa que implican), XP al completar
una task (depende de `gamification`, Fase 10), webhooks, vínculo
automático commit↔task por mensaje de commit, snapshot diario de
burndown (pide un job programado que no existe todavía).

**Fase 7 — `gestor-monitoring` (núcleo completo).** "Gestor" como
`gestor-db`: descubre servicios por la etiqueta `freya.service` a través
del socket de Docker (sólo lectura — única excepción del proyecto a "nada
toca Docker salvo `freya.ps1`", elegida en vivo con el usuario frente a
una lista estática, porque una lista sólo se actualiza si todo pasa por
`freya.ps1`), hace scrape de `/metrics` de cada uno y lo importa a
VictoriaMetrics (`freya-mon`, red privada `--internal`), golpea `/ready`
periódicamente y guarda el historial para calcular disponibilidad de 24h
(Cloud Health, docs/freya-api-contract.md §11). Consultas por PromQL de
verdad: nombres "amigables" (`request_rate`, `error_rate`,
`response_time_ms`) para lo común, PromQL crudo como vía de escape para
todo lo demás. Grafana bajo perfil opcional, con VictoriaMetrics
pre-provisionada como fuente de datos.

Ninguno de los seis servicios ya construidos tenía en realidad un
`/metrics` que sirviera algo: la etiqueta existía desde la Fase 0, pero
`create_app()` nunca montaba esa ruta. Se añadió a `freya-common`
(`prometheus_client`, la librería oficial — reimplementar el formato de
exposición a mano no aportaba nada) enganchado donde `ContextMiddleware`
ya mide cada petición para el log de acceso, así que los seis servicios
exponen métricas reales en cuanto se reconstruyen — verificado
redesplegándolos todos y viendo sus siete series aparecer en
VictoriaMetrics.

Verificado en vivo, dos veces seguidas: listar los servicios descubiertos,
detalle de uno, `404` de uno inexistente, forzar un health-check
inmediato, tablero de dashboard, consulta de métrica amigable con puntos
reales (esperando los ciclos de scrape necesarios para que `rate()`
tuviera con qué calcular), consulta PromQL cruda, PromQL inválida → `400`
— 12 comprobaciones. Tres bugs reales de despliegue, no de la lógica de
negocio: el socket de Docker es `660 root:root` (necesita `group_add:
["0"]`, nunca ejecutar como root); `GF_INSTALL_PLUGINS` de Grafana
intentaba salir a internet desde `freya-mon`, que es `--internal` a
propósito, y tumbaba el proceso entero al fallar — se quitó, junto con la
fuente de datos de VictoriaLogs que dependía de ese plugin; la imagen de
VictoriaLogs no tiene ni `/bin/sh` ni `wget`, así que su `HEALTHCHECK`
basado en `CMD-SHELL` fallaba siempre — se quitó, `gestor-monitoring` ya
lo vigila desde fuera.

Pendiente: recolección de logs (mon-04 — el contenedor `logs` existe y
tiene retención acotada, pero nada le envía datos todavía; seguir stdout
de cada contenedor por el socket de Docker es un subsistema en sí mismo).
Reglas de alerta y notificaciones (mon-06), y con ellas
`/monitoring/alerts` e incidentes. `/monitoring/sla` y
`/monitoring/deployment-log` (depende de `cicd`). Webhooks. Dashboard de
VictoriaLogs en Grafana (necesitaría un `Dockerfile` propio que instale el
plugin en tiempo de construcción, con red — no en arranque del
contenedor).

**Fase 8 — `cicd` (núcleo, alcance recortado en vivo con el usuario).**
Esta fase tiene dos tareas de dificultad 5 — el runner de pipelines
(ci-03) y el Deployment Manager (ci-06) — que son, por diseño, las
capacidades más peligrosas de la plataforma hasta ahora: ejecución de
código con privilegios de host, y control sobre el resto de los servicios
de Freya. Se preguntó antes de escribir código (`AskUserQuestion`), no se
asumió. Lo que se construyó es deliberadamente estrecho: el runner
(`app/domain/runner.py`) no ejecuta pipelines arbitrarios definidos por
YAML — sólo sabe reproducir exactamente lo que ya hacía
`.\freya.ps1 test`/`lint` (`docker build --target dev` + `ruff check` +
`pytest`, para un `<servicio>` validado contra un patrón estricto y la
existencia real de su Dockerfile, nunca contra lo que mande quien llama).
El Deployment Manager (`app/domain/deployments.py`) sólo modela el flujo
que pidió el usuario — "antes de ejecutar algo debe correr con un
pipeline; si falla, no se ejecuta" — exigiendo una ejecución exitosa antes
de aceptar un despliegue, pero el registro que queda siempre dice
`status: "simulated"`: nunca toca otro contenedor.

Esto sigue necesitando el socket de Docker, esta vez en **escritura**
(construir y correr imágenes, no sólo listarlas) — la segunda excepción
del proyecto a "nada toca Docker salvo `freya.ps1`", documentada como
regla explícita en `docs/ARCHITECTURE.md`. El cliente de `docker` (no un
daemon propio: "Docker fuera de Docker") se copia de la imagen oficial
`docker:27-cli`; el repositorio se monta de sólo lectura como contexto de
build.

Verificado en vivo: crear un pipeline `standard-tests`, rechazar un
`pipeline_type` no soportado (`422`), disparar un build+lint+test real
contra `storage` — los tres jobs en verde, el log del job de test
contiene "passed" de verdad, no simulado —, crear un despliegue simulado
sobre esa ejecución exitosa, `404` al disparar un servicio inexistente,
`404` al desplegar sobre una ejecución que no existe — 14 comprobaciones.
Después, siguiendo el pedido explícito del usuario de migrar las pruebas
unitarias ya construidas al CI/CD de Freya: se creó un pipeline
`standard-tests` para cada uno de los ocho servicios ya construidos
(`gestor-db`, `auth`, `secrets`, `storage`, `git`, `project-manager`,
`gestor-monitoring`, el propio `cicd`) y se disparó de verdad contra este
servicio — build+lint+test reales para los ocho, no simulados.

Pendiente, deliberadamente fuera de alcance: runner general con pipelines
definidos por YAML del repo (necesita su propio diseño de aislamiento
antes de aceptar código arbitrario), disparadores por push a `git` (`git`
no tiene todavía ningún mecanismo de webhook saliente), artefactos reales
a `storage` (los jobs de hoy sólo producen logs), Dependency Updater,
inyección de credenciales desde `secrets`, y el Deployment Manager real —
dar a un servicio containerizado control sobre el resto de la plataforma
merece su propio diseño de seguridad, no un añadido de esta fase.

Siguiente: Fase 9 — `frontend`.

## Estructura

```
freya.ps1        único punto de entrada. Todo se controla desde aquí
docs/            arquitectura, convenciones y roadmap
projects/        backlog: un YAML por servicio, con tasks y dificultad
templates/       plantilla de servicio Python
<servicio>/      un directorio por proyecto (gestor-db/, auth/, storage/,
                 freya-common/...) -- cada uno su propio repo git y su
                 propio pipeline en cicd (docs/ARCHITECTURE.md §2.1)
services/        sólo backends de terceros sin código propio que separar
                 (database, metrics, logs, dashboards)
infra/
  powershell/    módulos que respaldan freya.ps1
  toolbox/       imagen con bash, git, openssl y python para tareas puntuales
  scripts/       lo que corre dentro del toolbox, nunca en el host
  certs/         certificados de desarrollo (no versionados)
  secrets/       secretos de bootstrap (no versionados)
```

## Arranque

**Requisito único: Docker Desktop en modo contenedores Linux.** No hace falta
WSL, ni Python, ni openssl, ni Git Bash en el host. Todo corre en contenedores;
PowerShell sólo los levanta.

```powershell
cd D:\Proyectos\Freya

# Sólo la primera vez, si PowerShell bloquea los scripts locales
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned

# Redes de Docker, imagen del toolbox y certificados de desarrollo
.\freya.ps1 init

# Crear un servicio desde la plantilla (el puerto sale del registro)
.\freya.ps1 new gestor-db

# Levantar un servicio, o una fase entera
.\freya.ps1 up gestor-db
.\freya.ps1 phase 1

.\freya.ps1 status
.\freya.ps1 logs gestor-db -Follow
```

Si algo no arranca, el primer comando es siempre:

```powershell
.\freya.ps1 doctor
```

Comprueba Docker, el modo de contenedor, las cuatro redes, los certificados y
los finales de línea de los scripts. `.\freya.ps1 help` lista todo lo demás.

### Por qué hay un toolbox

Emitir certificados y generar servicios desde la plantilla necesita `openssl`,
`bash` y `python`. En lugar de exigir esas herramientas en Windows, viven en una
imagen Alpine de unos 60 MB que `freya.ps1` construye la primera vez y usa
montando el repositorio en `/workspace`. El host sigue sin instalar nada.

### Finales de línea

Los scripts de `infra/scripts/` se montan dentro de contenedores Linux. Si Git
los convierte a CRLF, `bash` falla con `bad interpreter: ...^M`. El
`.gitattributes` del repositorio lo evita; si clonaste sin él, `.\freya.ps1
fix-eol` lo corrige.

## Reglas que no se negocian

1. Todo corre en contenedores. En el host sólo hay Docker y `freya.ps1`.
2. Los servicios hablan entre sí por HTTPS, siempre.
3. Sólo un gestor toca el protocolo nativo de sus contenedores, en red privada.
4. Ningún servicio se conecta a PostgreSQL: se pasa por `gestor-db`.
5. Ningún secreto en el repositorio.
6. Ningún fichero pasa de 500 líneas.
7. Freya usa Freya: la propia plataforma es su primer cliente.

## Documentación

- [Arquitectura](docs/ARCHITECTURE.md) — servicios, redes, puertos, tecnología
- [Convenciones](docs/CONVENTIONS.md) — API, errores, logs, contenedores, datos
- [Runbook de despliegue](docs/RUNBOOK.md) — de `git push` a corriendo en tu PC, vía GitHub Actions
- [Decisiones](docs/DECISIONS.md) — porqués de diseño, encontrados en vivo
- [Roadmap](docs/ROADMAP.md) — las 11 fases y sus criterios de salida
- [Backlog](projects/README.md) — 90 tasks con dificultad

## Presupuesto de recursos

Objetivo con toda la plataforma en marcha, sin Grafana:

| Componente | RAM |
|---|---|
| PostgreSQL | 256 MB |
| 10 servicios propios | 10 × 128–256 MB |
| VictoriaMetrics + VictoriaLogs | 96 MB |
| **Total estimado** | **~2 GB** |

Grafana suma unos 200 MB y por eso vive en un perfil opcional.
