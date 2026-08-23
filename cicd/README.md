# cicd

Pipelines de Freya. Contrato: docs/freya-api-contract.md §8, con el
alcance decidido en vivo con el usuario antes de escribir una sola línea
(`AskUserQuestion`, no una suposición): esta fase tiene dos tareas de
dificultad 5 (ci-03, el runner; ci-06, el Deployment Manager) que son, por
diseño, las capacidades más peligrosas de toda la plataforma —
ejecución de código con privilegios de host y control sobre el resto de
los servicios de Freya. Ninguna de las dos se construyó en su forma
general.

## El runner no ejecuta pipelines arbitrarios

Un runner "de verdad" (ci-03 tal cual la describe ROADMAP.md: contenedores
efímeros por job, definidos por un `.freya/pipeline.yaml` en el repo) es
ejecución remota de código arbitrario como servicio. Lo que se construyó
en su lugar es mucho más estrecho: `app/domain/runner.py` sólo sabe hacer
una cosa, reproduciendo exactamente `Invoke-FreyaTest` de
`infra/powershell/FreyaServices.psm1`:

```
docker build --target dev --tag freya/<servicio>:test \
    --file <servicio>/Dockerfile .
docker run --rm --network none freya/<servicio>:test ruff check /srv/app
docker run --rm --network none freya/<servicio>:test pytest -q /srv/tests
```

`pipeline_type` sólo admite `"standard-tests"` — no hay forma de que
quien llama a la API defina qué imagen, Dockerfile o comando se ejecuta.
`<servicio>` se valida contra un patrón estricto (`^[a-z][a-z0-9-]{0,62}$`)
y, sólo si pasa eso, contra la existencia real de
`<servicio>/Dockerfile` dentro del workspace — las dos
comprobaciones antes de construir cualquier ruta o lanzar cualquier
subproceso, y siempre con `subprocess` en forma de lista de argumentos,
nunca `shell=True`. `tests/test_runner.py` prueba explícitamente que
intentos de recorrido de ruta e inyección de comandos (`../../etc`,
`storage;rm -rf /`, backticks, mayúsculas, rutas absolutas...) se
rechazan.

Aun así, esto necesita el socket de Docker en **escritura** — a
diferencia de `gestor-monitoring`, que sólo lee para descubrir
contenedores, aquí hace falta crear y correr imágenes de verdad. Es la
segunda excepción del proyecto a "nada toca Docker salvo `freya.ps1`"
(ver `docs/ARCHITECTURE.md` regla 6), y la más amplia con diferencia. El
contenedor sigue como UID 10001 (nunca root; `group_add: ["0"]` para el
permiso de grupo del socket, `660 root:root` en Docker Desktop), pero
quien comprometa este servicio tiene, de facto, control del daemon de
Docker del host.

## Docker fuera de Docker, no Docker dentro de Docker

`Dockerfile` copia sólo el **cliente** de `docker:27-cli` (no un daemon
propio): habla con el socket montado del host, el mismo patrón que usa
cualquier herramienta tipo Portainer. El repo completo se monta de sólo
lectura en `/workspace` (`docker-compose.yml`) porque `docker build`
necesita ese contexto para el `COPY libs/`, `COPY <nombre>/...`
de cada Dockerfile — cicd nunca escribe ahí.

## Los pasos del pipeline, elegidos por YAML -- nunca el comando

Petición explícita posterior ("todo esté en yaml", ver el historial de
esta fase): cada servicio puede traer `<servicio>/.freya/pipeline.yaml`
con una lista `steps` que elige QUÉ de un catálogo cerrado correr y en qué
orden -- `lint`, `test`, `security_scan` -- nunca QUÉ COMANDO ejecuta cada
uno, que sigue fijo en `_STEP_COMMANDS` de `app/domain/runner.py`. Sin el
fichero, el pipeline por defecto sigue siendo lint+test, igual que antes de
que existiera este mecanismo. `security_scan` corre `pip-audit` contra la
imagen de test -- a diferencia de lint/test, necesita salida a red (la
misma excepción ya documentada en `docs/ARCHITECTURE.md` §4 para
registros de paquetes), así que es el único paso que NO corre con
`--network none`. Encontró de verdad un CVE real (pip desactualizado en la
imagen base de Python) la primera vez que se activó contra los ocho
servicios -- se corrigió con un `pip install --upgrade pip` en la etapa de
build de cada Dockerfile, no ignorando el hallazgo.

## Disparo automático por push, ya no pendiente (ci-04)

`git` dispara este pipeline solo tras un push real (ver
`git/README.md`): ya no hace falta "sin intervención manual" como
pendiente de la fase. Verificado con un cliente `git` real -- no un
`POST /trigger` simulado -- alojando `storage/` como su propio
repo y viendo el pipeline `storage-standard-tests` dispararse de verdad
tras el `push`, con `triggered_by: "push"` en el run.

## Las pruebas unitarias ya construidas, migradas de verdad

La migración pedida ("todas las pruebas unitarias que creaste migralas al
ci/cd de Freya") no mueve ni un fichero de test: cada servicio sigue
guardando los suyos en su propio `tests/`. Lo que cambia es quién los
ejecuta — se creó un pipeline `standard-tests` por cada uno de los ocho
servicios ya construidos (`gestor-db`, `auth`, `secrets`, `storage`,
`git`, `project-manager`, `gestor-monitoring`, el propio `cicd`) y se
disparó de verdad contra este servicio, con build+lint+test reales para
los ocho. Cualquier servicio nuevo se suma igual: `POST /pipelines` con
su nombre.

## Deployment Manager: sólo el modelo, nunca toca otro contenedor

`app/domain/deployments.py` modela el flujo que pidió el usuario
("antes de ejecutar algo debe correr con un pipeline; si falla, no se
ejecuta"): `POST /deployments` exige `pipeline_run_id` de una ejecución
con `status: success` — si no, `409`. Pero incluso cuando se acepta, el
registro que queda grabado tiene `status: "simulated"` siempre: no se
despliega nada de verdad, ni siquiera a sí mismo. Dar a un servicio
containerizado la capacidad de reconfigurar el resto de la plataforma
—lo que pide ci-06 tal cual— es una decisión de seguridad que merece su
propio diseño (qué puede desplegar, con qué autorización, cómo se
audita), no un añadido de esta fase.

## Endpoints

`Authorization: Bearer <jwt>`. Permisos: `read:cicd` / `write:cicd`.

| Ruta | Método | Qué hace |
|---|---|---|
| `/pipelines` | POST / GET | `pipeline_type` sólo `standard-tests` por ahora; cualquier otro valor → `422`. |
| `/pipelines/{id}` | GET | |
| `/pipelines/{id}/trigger` | POST | Build + lint + pytest reales. Devuelve la ejecución completa con sus jobs. `404` si el servicio no existe de verdad. |
| `/pipelines/{id}/runs` | GET | Historial. |
| `/runs/{id}` | GET | Con sus jobs. |
| `/jobs/{id}/log` | GET | Salida completa (recortada a los últimos 20000 caracteres) del job. |
| `/deployments` | POST | `409` si `pipeline_run_id` no fue un éxito. Siempre queda `status: simulated`. |
| `/deployments` | GET | `?service` |
| `/deployments/{id}` | GET | |

## Estructura

```
app/
├── main.py                  /ready incluye "docker": docker version por el socket
├── config.py                  workspace_dir, docker_binary, timeouts de build/run
├── api/
│   ├── pipelines.py            pipelines, trigger, runs, jobs, logs
│   └── deployments.py           Deployment Manager simulado
└── domain/
    ├── runner.py                 el único camino que toca `docker build`/`run`
    ├── pipelines.py                CRUD, tipo fijo a standard-tests
    ├── runs.py                      ejecuta + persiste jobs
    └── deployments.py                gateado por pipeline_run_id exitosa
```

## Pendiente

Runner general con pipelines definidos por YAML en el repo que acepten
comando/imagen arbitrarios (ci-02, ci-03 en su forma completa) — necesita
su propio diseño de aislamiento (red, límites, timeouts, kill switches)
antes de aceptar código arbitrario; lo que sí existe hoy es YAML eligiendo
pasos de un catálogo cerrado (ver arriba), deliberadamente no lo mismo.
Artefactos reales a `storage` (ci-05): los jobs de hoy (lint/test/scan) no
producen nada más que logs, así que `ci_artifacts` existe en el schema
pero no se usa todavía. Dependency Updater (ci-07). Inyección de
credenciales desde `secrets` sin aparecer en logs (ci-08) — no hace falta
todavía porque ningún job que existe consume secretos. Deployment Manager
real (ci-06 completo) — deliberadamente fuera de alcance, ver arriba.
Disparo consciente del diff cuando un único repo aloje varios servicios a
la vez (hoy el disparo por push es 1:1 `<repo>-standard-tests`, ver
`git/README.md`).

## Tests

```powershell
.\freya.ps1 test cicd
.\freya.ps1 lint cicd
```

`tests/test_runner.py` es el más importante de todo el servicio: prueba
la barrera de seguridad de `validate_service_name` contra recorrido de
rutas e inyección de comandos, sin red ni Docker real (un workspace de
mentira en `tmp_path`). Verificado además en vivo contra el servicio
desplegado: crear un pipeline, rechazar un `pipeline_type` no soportado,
disparar un build+lint+test real contra `storage` (los tres jobs en verde,
el log del job de test contiene "passed" de verdad), crear un despliegue
simulado sobre esa ejecución exitosa, `404` al disparar un servicio
inexistente, `404` al desplegar sobre una ejecución que no existe — 14
comprobaciones. Después, los ocho servicios ya construidos se migraron a
sendos pipelines `standard-tests` y se dispararon todos de verdad.
