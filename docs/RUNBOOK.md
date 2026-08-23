# Runbook: de `git push` a corriendo en tu PC

Guía operativa del pipeline de despliegue de Freya. `docs/DECISIONS.md`
tiene el porqué de cada decisión de diseño; esto es "qué hago cuando
pasa X" — el día a día de operarlo.

> **Peligro real, encontrado en vivo:** el job `deploy` hace `git fetch` +
> `git reset --hard origin/main` dentro de `/workspace`, que es
> `../..:/workspace` montado desde el propio checkout de este repo en el
> host (`services/github-runner/docker-compose.yml`) -- el MISMO
> directorio donde trabajas normalmente, no una copia aislada. Cualquier
> cambio sin commitear que tengas ahí cuando un job `deploy` corre
> (aunque sea de otro servicio) se pierde sin aviso. Commitea (aunque sea
> a una rama aparte) antes de dejar el repo con cambios sueltos si hay
> algún push reciente que pueda disparar un deploy.

## El pipeline en una frase

Un `git push` a `main` que toca `<servicio>/**` dispara
`.github/workflows/deploy-<servicio>.yml`, que corre en dos fases
secuenciales:

1. **`check`** — en un runner de GitHub (`ubuntu-latest`), efímero, nunca
   toca tu PC. Checkout real, build de la imagen `dev`, lint (`ruff`),
   tests (`pytest`), escaneo de dependencias (`pip-audit`).
2. **`deploy`** — sólo arranca si `check` pasó (`needs: check`). Corre en
   `services/github-runner/`, el runner autoalojado que vive en tu propio
   Docker Desktop. Actualiza su checkout local (`git fetch` + `reset
   --hard`) y ejecuta `services/github-runner/deploy-service.sh
   <servicio>`, que reconstruye la imagen "runtime" y hace `docker compose
   up -d`, verificando que el contenedor llegue a `healthy` antes de dar
   el paso por bueno.

Código que no pasa lint/test/security_scan **nunca llega a ejecutarse en
tu PC** — ese es el punto de separar las dos fases en dos jobs con
`needs:`, no sólo dos pasos de un mismo job.

## Qué se despliega así hoy, y qué no

**Con workflow propio (push-triggered):** `auth`, `secrets`, `storage`,
`gestor-db`, `gestor-monitoring`, `frontend`, `gamification`,
`freya-common` (sólo corre `check` — es una librería de build, no un
servicio HTTP, así que su job `deploy` no tiene nada que reiniciar).

**Todavía no migrados, deploy manual vía `freya.ps1`:** `git`,
`project-manager`, `cicd`. Decisión deliberada (`docs/DECISIONS.md`,
"Migración a GitHub"): se quedan como están hasta decomisionarlos, no
tiene sentido montarles un pipeline que va a desaparecer pronto. Para
desplegar un cambio en estos tres a mano:

```powershell
.\freya.ps1 up git           # o project-manager, o cicd
```

## Flujo normal: hacer un cambio

1. Edita el código del servicio que toque.
2. `git add`, `git commit`, `git push origin main`.
3. En GitHub → pestaña **Actions**, aparece `Deploy <servicio>` corriendo.
   El job `check` tarda ~30–90s (runner de GitHub, sin contención con tu
   PC). Si falla ahí, el job `deploy` ni se intenta — arregla lo que
   marque `check` y vuelve a empujar.
4. Si `check` pasa, `deploy` arranca en tu runner local. Tarda más
   (reconstruye la imagen `runtime`, espera hasta 60s a que el
   healthcheck de Docker confirme `healthy`).
5. Verifica en tu PC:
   ```bash
   docker ps --format "{{.Names}}: {{.Status}}"
   ```

## Verificar que un deploy salió bien

- **GitHub, sin tocar tu PC:** pestaña Actions del repo, o
  `gh run list --workflow=deploy-<servicio>.yml --limit 5`.
- **En tu PC:** `docker ps` (arriba) o `docker logs freya-<servicio>
  --tail 50`.
- **El propio runner:** `docker logs freya-github-runner --tail 30` — cada
  job que corre queda como `Running job: deploy` / `Job deploy completed
  with result: Succeeded|Failed`.

Un `docker compose up -d` que "termina bien" NO es lo mismo que el
contenedor quedando sano — `deploy-service.sh` ya lo verifica con un
`docker inspect --format '{{.State.Health.Status}}'` en bucle (hasta 60s)
antes de dar el paso por éxito, así que un `Failed` en el log del runner
es señal real de que algo no llegó a `healthy`, no un falso positivo.

## Desplegar sin un cambio de código

A veces hace falta re-desplegar el mismo commit (p.ej. recuperarse del
patrón de "unhealthy transitorio" de abajo, o tras cambiar algo fuera del
código versionado como un secreto). Dos formas:

```bash
# Desde dentro del contenedor del runner (mismo mecanismo que usa el job
# "deploy" de verdad, sin necesidad de un push):
docker exec freya-github-runner bash -c "cd /workspace && bash services/github-runner/deploy-service.sh <servicio>"
```

```powershell
# Directo desde el host, sin pasar por el runner (más simple si sólo
# quieres el efecto, no probar el pipeline en sí):
.\freya.ps1 up <servicio>
```

## Problema conocido: "unhealthy" transitorio tras una tanda de deploys

Cuando varios `deploy-*.yml` corren seguidos (p.ej. un push que toca
varios servicios, o una racha de pushes), el host puede quedarse sin
margen de CPU/IO durante unos minutos: los healthchecks de Docker de
contenedores QUE NO TIENEN NADA QUE VER con el deploy en curso empiezan a
fallar por *timeout de la propia sonda* (3–5s), no porque el servicio esté
realmente roto — las peticiones reales siguen respondiendo en
milisegundos si las pruebas a mano (`docker exec <contenedor> curl
https://127.0.0.1:<puerto>/health` o el equivalente en Python, ver
`docs/DECISIONS.md` para el diagnóstico completo con `gestor-db` y
`traefik`). Se autorecupera solo en 1–5 minutos según baje la carga.

**Cómo distinguirlo de un fallo real:**
```bash
docker inspect freya-<servicio> --format '{{json .State.Health}}' | python3 -m json.tool
```
Si el `Output` dice `"Health check exceeded timeout (Ns)"` (no un error de
conexión ni un status HTTP de error) y `docker logs freya-<servicio>
--tail 20` muestra peticiones reales respondiendo con `200` normal,
es contención transitoria — espera. Si el log muestra excepciones,
tracebacks, o conexiones rechazadas de verdad, es un fallo real —
investiga el `docker logs` a fondo.

Si un servicio se queda persistentemente unhealthy (streak de decenas de
fallos, no unos pocos) incluso con el host en reposo, es la otra causa ya
encontrada una vez: el límite de memoria del `docker-compose.yml`
(`deploy.resources.limits.memory`) demasiado ajustado para que el propio
proceso de healthcheck (a veces un binario/intérprete nuevo por chequeo)
tenga margen para arrancar — ver el fix de `traefik` en
`docs/DECISIONS.md` como plantilla del diagnóstico y la solución.

## El runner se cayó o no aparece en GitHub

```bash
docker logs freya-github-runner --tail 50
docker ps --filter name=freya-github-runner
```

Si no está corriendo: `.\freya.ps1 up github-runner`. El registro contra
GitHub se renueva solo en cada arranque del contenedor (pide un token de
registro fresco con el PAT de larga duración en
`infra/secrets/github-runner/github_pat` — los tokens de registro en
crudo caducan en ~1h, por eso no se guarda uno fijo). Si el PAT en sí
caducó o perdió permisos, `entrypoint.sh` falla con un mensaje explícito
al arrancar (`docker logs` lo muestra) — genera uno nuevo (scope `repo`
para un repo, `admin:org` para nivel organización) y reemplaza el fichero.

## Rollback

No hay un botón "deshacer deploy". El camino real:

```bash
git revert <commit-malo>
git push origin main
```
Esto dispara el pipeline normal (`check` → `deploy`) con el código
revertido — mismo camino que cualquier otro cambio, nada especial que
recordar. Para revertir sin esperar al pipeline (emergencia real, ya en
tu PC):
```powershell
git -C D:\Proyectos\Freya reset --hard <commit-bueno-anterior>
.\freya.ps1 up <servicio>
```
Ten en cuenta que esto deja tu checkout LOCAL por delante/detrás de
`origin/main` — el próximo `deploy` de cualquier servicio hará `git fetch
+ reset --hard origin/main` y lo devolverá a lo que haya en GitHub,
incluido el commit malo si no lo revertiste allí también.

## Funciones de seguridad de GitHub activas en este repo

Además de lint/test/pip-audit por servicio (arriba):

- **CodeQL** (`.github/workflows/codeql.yml`) — análisis semántico del
  código propio (inyección, path traversal, SSRF, etc.), no de
  dependencias de terceros. Corre en cada push a `main` y semanalmente.
  Resultados: pestaña **Security → Code scanning alerts** del repo.
- **Secret scanning + push protection** — GitHub rechaza un `push` que
  contenga un patrón de secreto reconocible (token de API, clave privada,
  etc.) antes de que llegue a existir en el historial. Pestaña
  **Security → Secret scanning alerts**.
- **Dependabot security updates** — PR automático tan pronto se publica
  un CVE para una dependencia que uses (activado a nivel de repo, no
  necesita workflow).
- **Dependabot version updates** (`.github/dependabot.yml`) — PR semanal
  por servicio con dependencias desactualizadas (no ligado a un CVE,
  barrido rutinario).

Ninguno de estos bloquea el `deploy` job hoy (sólo `check` lo hace) —
acoplar el deploy a CodeQL/Dependabot añadiría una dependencia entre
workflows separados (`workflow_run`) que este repo de un solo
desarrollador real no necesita todavía; revisar las alertas es manual.

## Añadir un servicio nuevo a este pipeline

```bash
bash infra/scripts/new_service.sh <nombre> <puerto>
```
Genera `.github/workflows/deploy-<nombre>.yml` a partir de
`templates/github-workflow/deploy.yml` (mismo patrón de dos jobs de
arriba) automáticamente — no hace falta copiarlo a mano.
