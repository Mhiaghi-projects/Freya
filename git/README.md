# git

Control de versiones de Freya. Envuelve el binario real de `git`
(docs/ARCHITECTURE.md §5: "propio: FastAPI sobre `git http-backend`") — no
reimplementa el protocolo ni el modelo de objetos. Contrato:
docs/freya-api-contract.md §6, con una ruta de protocolo smart HTTP que el
contrato no detalla (§6.1 sólo da el `clone_url`) y un endpoint de árbol de
ficheros que tampoco está en el contrato pero exige el roadmap (tarea
git-04, "árbol de ficheros por API").

## El contenedor no guarda estado propio

Cada repo son 2-3 objetos en el bucket `git` de storage (nunca uno por
objeto git suelto — storage no está pensado para miles de ficheros
diminutos por bucket, ver `storage/README.md`):

- `{repo}/pack` — un único packfile consolidado con todo el historial.
- `{repo}/refs.json` — `{"head": "refs/heads/main", "refs": {"refs/heads/main": "<sha>", ...}}`.

Antes de cualquier operación (clone, fetch, push, o cualquier lectura de la
API — branches, tags, commits, diff, tree) se **materializa** un repo bare
efímero en `/scratch` (volumen con nombre, pero tratado como caché
desechable, nunca como fuente de verdad): `git init --bare`, se indexa el
pack descargado (`git index-pack --stdin`, sin `-o` — deja que git derive
el nombre de pack+idx de su propio hash de contenido) y se escribe cada ref
con `git update-ref`. Tras un `git-receive-pack` que escribe, se vuelve a
empaquetar (`git repack -a -d`) y se sube. El directorio se borra al
terminar la petición: si el contenedor muriera a mitad, no se pierde nada
— la próxima petición lo reconstruye desde storage.

## Protocolo smart HTTP

```
GET  /git/{tenant}/{repo}.git/info/refs?service=git-upload-pack|git-receive-pack
POST /git/{tenant}/{repo}.git/git-upload-pack
POST /git/{tenant}/{repo}.git/git-receive-pack
```

Tenant y repo van en la ruta, no en `X-Tenant-Context`: un cliente git real
no manda esa cabecera. La autenticación sigue siendo un JWT de Freya, vía
`-c http.extraHeader="Authorization: Bearer <jwt>"` en el cliente:

```bash
git -c http.extraHeader="Authorization: Bearer $JWT" \
    clone https://freya-git:8005/git/freya/mi-repo.git
```

Cada ruta invoca `git http-backend` como subproceso CGI
(`app/domain/cgi_bridge.py`): variables de entorno (`GIT_PROJECT_ROOT`,
`PATH_INFO`, `GIT_HTTP_EXPORT_ALL=1`, ...) + stdin para la petición, y se
traduce su salida CGI (cabeceras + línea en blanco + cuerpo) a una
`Response` normal.

### El gotcha que costó tres iteraciones: rama por defecto de un repo vacío

Un `git clone` de un repo recién creado (sin commits) necesita que el
*servidor* le diga qué nombre de rama usar localmente — si no, el cliente
cae a su propio `init.defaultBranch` (normalmente "master"), y el primer
`push` falla con `src refspec main does not match any`. Esa negociación
sólo existe bajo el protocolo v2 de git (capacidad `ls-refs=unborn`); v0 no
la tiene. Un cliente git moderno manda la cabecera `Git-Protocol:
version=2`, pero `git http-backend` sólo la ve si se la reenviamos como
variable de entorno CGI `HTTP_GIT_PROTOCOL` (convención CGI: cabecera
`Git-Protocol` → `HTTP_GIT_PROTOCOL`). Sin esto, todo funciona salvo el
nombre de la rama en un clone vacío — un fallo silencioso y fácil de no
notar. `app/api/smart_http.py` reenvía `request.headers.get("git-protocol")`
en las tres rutas.

## Un bug real de integración con storage: el sobre genérico corrompía un blob JSON

`refs.json` se subía con `Content-Type: application/json`. El
`EnvelopeMiddleware` de storage envolvía **cualquier** respuesta con ese
content-type en `{"success": true, "data": ..., "meta": ...}` — no
distinguía una respuesta de su propia API de un blob descargado que
simplemente resultaba ser JSON. El resultado: cada `GET .../refs.json`
devolvía el sobre completo en vez del contenido original, así que
`refs.get("refs", {})` siempre veía `{}` (la clave real estaba anidada bajo
`data`) y ningún ref se escribía nunca — sin ningún error visible, porque
`git update-ref` con una lista vacía simplemente no hace nada. Se detectó
comparando la respuesta cruda de storage con lo que `materialize()`
terminaba escribiendo en disco.

Workaround temporal: subir `refs.json` como `application/octet-stream`. El
arreglo real llegó del lado de storage: la ruta de descarga de objetos
(`storage/app/api/objects.py`) marca su `Response` con la cabecera
`X-Freya-No-Envelope` (`freya_common.NO_ENVELOPE_HEADER`), y
`EnvelopeMiddleware` (`freya-common/freya_common/envelope.py`) la
respeta pase lo que pase el content-type — la retira antes de responder al
cliente, así que nunca es visible fuera del propio middleware. Con eso en
su sitio, `repo_store.py` volvió a subir `refs.json` como
`application/json`, que es lo que realmente es.

## API de lectura y gestión (docs/freya-api-contract.md §6)

`Authorization: Bearer <jwt>`. Permisos: `read:git` / `write:git` /
`admin:git`.

| Ruta | Método | Qué hace |
|---|---|---|
| `/git/repos` | POST | `{repo_name, description, default_branch, visibility, sensitive, github_mirror_url, github_sync_enabled, secret_validation_enabled}`. `409` si el nombre ya existe. |
| `/git/repos` | GET | Lista los repos del tenant. |
| `/git/repos/{repo_id}` | GET / DELETE | DELETE también borra el pack/refs.json de storage. |
| `/git/repos/{repo_id}/branches` | GET / POST / DELETE `/{branch}` | `POST` crea a partir de `from_commit`. La rama por defecto sale marcada `protected`. |
| `/git/repos/{repo_id}/tags` | GET / POST / DELETE `/{tag}` | Tags siempre anotadas (`git tag -a`): mensaje y tagger viven en el propio objeto git, no en un canal aparte. Nombre debe seguir semver (§6.4). |
| `/git/repos/{repo_id}/commits` | GET | `?branch&limit&cursor&author&since&until`. `storage_location` siempre `"local"` por ahora (ver Pendiente). |
| `/git/repos/{repo_id}/diff` | GET | `?base&head&path`. Incluye parche unificado y estadísticas por fichero. |
| `/git/repos/{repo_id}/tree` | GET | `?ref&path`. **No está en el contrato** — lo exige ROADMAP.md (git-04). |

## Estructura

```
app/
├── main.py                  storage Y gestor-db como dependencias (no sólo gestor-db)
├── config.py                  scratch_dir, git_bucket, git_binary
├── api/
│   ├── smart_http.py            protocolo git real
│   └── repos.py                  API REST de §6
└── domain/
    ├── git_ops.py                subprocess sobre git: init, index-pack, repack, refs
    ├── cgi_bridge.py              puente CGI hacia git http-backend
    ├── repo_store.py              materializar/persistir contra storage
    ├── repos.py                   catálogo de repos en gestor-db
    └── history.py                 branches/tags/commits/diff/tree sobre un repo materializado
```

## Push dispara el pipeline standard-tests (ci-04/git-08)

`app/domain/webhooks.py`: tras un `git-receive-pack` que persiste con
éxito, se dispara (en segundo plano, `BackgroundTasks` -- un pipeline real
tarda decenas de segundos y `git push` no debería quedarse colgado
esperando) un intento de trigger contra `cicd` para un pipeline llamado
`<repo>-standard-tests`. Sin ese pipeline, no pasa nada -- no es una
condición de error, la mayoría de repos no tienen uno. Mejor esfuerzo
total: cualquier fallo hablando con `cicd` se registra como aviso, nunca
tumba ni retrasa la respuesta al cliente git real.

Verificado en vivo con un cliente `git` real, no simulado: se creó un repo
`storage` en este servicio, se le hizo `git init` + commit + `push` al
propio `storage/` (autoalojado -- exactamente lo que describe
ci-04, "Freya se apoya en los demás servicios de Freya"), y el push disparó
de verdad el pipeline `storage-standard-tests` ya existente en `cicd` --
`triggered_by: "push"` en el run, build+lint+test+security_scan en verde,
sin ninguna intervención manual tras el `git push`. Alojar el resto de
servicios es el mismo mecanismo repetido, no trabajo de ingeniería nuevo;
un disparo consciente del diff (qué servicio cambió dentro de un monorepo
único, para no repetir esto ocho veces) queda para cuando haga falta.

## Pendiente

Política de retención de 5 commits + espejo a GitHub (git-05, git-06):
requiere decidir cómo se modela "qué vive sólo en GitHub" antes de diseñar
el schema, así que se deja para cuando se construya de verdad — hoy
`storage_location` en `/commits` siempre es `"local"`. Marcado de repos
sensibles para excluirlos del push a GitHub (git-07, depende de git-05).
Validación anti-secretos en push (`POST /validate-secrets`, §6.9) y
bloqueo de commits con credenciales. `blame` (§6.7) y
`deployment-history` (§6.8). Multipart / repos muy grandes: cada operación
reempaqueta el historial completo, que no escala indefinidamente (mismo
tipo de límite que el recuento de uso de storage). Sin caché de refs: cada
lectura de branches/tags/commits vuelve a materializar el repo entero
desde storage; para repos grandes esto pide, en algún punto, una tabla de
refs mantenida incrementalmente en gestor-db.

## Tests

```powershell
.\freya.ps1 test git
.\freya.ps1 lint git
```

`tests/test_history.py` corre contra un repo bare real construido con el
propio binario de git (sin red, sin gestor-db, sin storage) — cubre el
parseo más delicado (separadores de `git log --numstat`, tags anotadas,
diff, árbol). `tests/test_cgi_bridge.py` cubre el parseo de la salida CGI
de `http-backend`, incluyendo cuerpos binarios. Verificado además en vivo
contra el servicio desplegado con un cliente `git` de verdad: crear repo,
clonar vacío, dos commits y dos `push`, clonar de nuevo y comprobar bytes
íntegros, listar branches/commits, crear y listar tag, diff, tree, borrar
— 22 comprobaciones, dos veces seguidas (para descartar estado que sólo
funcione "la primera vez").
