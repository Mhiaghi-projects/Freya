# storage

Almacenamiento de objetos versionados de Freya — el NAS de la plataforma:
todo lo que no sea código ni una fila de `database` vive aquí (backups,
packfiles de `git`, y lo que `secrets` gestione que no sean valores
cifrados en la base). Los bytes viven en `D:\share` del host (bind mount a
`/data`, fuera de la base); los metadatos —buckets, objetos, versiones—
pasan por `gestor-db` igual que cualquier otro dato de Freya. Contrato:
`docs/freya-api-contract.md` §5.

## Bytes fuera de la base, metadatos dentro, y en una carpeta legible

Cada versión de un objeto se guarda en su propio fichero, nombrado por su
id de versión (`ver_...`), dentro de una carpeta real
`D:\share\{tenant}\{bucket}\{key}\` — la `key` puede traer `/` (p.ej.
`{repo}/pack` en `git`) y se preserva como subcarpetas reales, no se
aplana (`app/domain/blob_store.py`). Es deliberado: `D:\share` tiene que
poder abrirse en el Explorador de Windows y verse como un NAS de verdad
("carpeta `git`", "carpeta `backups`"...), no como un espacio de hashes
opacos. Dos barreras contra un bucket/key con `..` o una ruta absoluta:
ningún segmento puede ser `.`/`..`/contener `/` o `\`, y el resultado final
se confirma dentro de `data_dir` con `resolve()` — la misma técnica de
`cicd/app/domain/runner.py`.

`gestor-db` sólo sabe qué versión es la vigente, su tamaño, su `etag`
(sha256 del contenido) y su estado (`ACTIVE`/`ARCHIVED`/`DELETED`) — nunca
ve el contenido en sí.

## Versionado

Con `versioning: true` en el bucket, un `PUT` sobre una `key` existente
archiva la versión anterior (`ARCHIVED`) en vez de borrarla; con
`versioning: false`, la purga de inmediato (fila y bytes). El ciclo de vida
completo más allá de eso —archivar tras N versiones, purgar tras M
(`max_versions`, §5.6 "retention_policy")— es tarea del futuro job
programado `storage_lifecycle` (§13.5), no de esta escritura: el `PUT`
nunca recorre todo el historial, sólo la versión inmediatamente anterior.

## `encryption` del bucket: aceptado, todavía no implementado

`PUT /storage/buckets/{bucket}` acepta y guarda `encryption`, pero
`blob_store.write`/`read` no lo miran -- los bytes se escriben en disco tal
cual, cifrados o no da igual. A diferencia de `max_versions` (arriba, tarea
explícita de `storage_lifecycle`), esto no estaba documentado como
pendiente en ningún sitio: un bucket creado con `encryption: true` no
protege el contenido más que uno con `encryption: false`. Cifrado real en
reposo (gestión de claves, IV/nonce, rotación) es una pieza de seguridad
que merece su propio diseño, no un efecto colateral de un barrido de bugs
-- ver `docs/DECISIONS.md`.

## Endpoints

`Authorization: Bearer <jwt>`. Permisos: `read:storage` / `write:storage`
(y el servicio necesita además `read:database` / `write:database` para
hablar con `gestor-db`, como cualquier otro servicio con estado).

| Ruta | Método | Qué hace |
|---|---|---|
| `/storage/buckets` | GET | Lista los buckets del tenant. |
| `/storage/buckets/{bucket}` | PUT | `{versioning, encryption, max_versions, quota_bytes}`. Crea el bucket (`409` si ya existe). |
| `/storage/buckets/{bucket}` | DELETE | `?force`. Sin `force`, `409` si el bucket tiene objetos. |
| `/storage/buckets/{bucket}/usage` | GET | Tamaño total/activo/archivado y `%` de cuota consumida. |
| `/storage/{bucket}` | GET | `?prefix&limit&cursor`. Lista objetos (versión vigente de cada uno). |
| `/storage/{bucket}/{key}` | PUT | Sube el contenido en crudo (no JSON). `If-None-Match: *` para exigir creación. `X-Object-Metadata` en base64. `413` si excede el máximo configurado. |
| `/storage/{bucket}/{key}` | GET | `?versionId`. Descarga; soporta `Range: bytes=...` (`206`). Devuelve `ETag`, `X-Version-Id`, `X-Version-Status`. |
| `/storage/{bucket}/{key}` | HEAD | Mismas cabeceras que `GET`, sin cuerpo. |
| `/storage/{bucket}/{key}` | DELETE | `?versionId`. Sin `versionId`, borra el objeto entero (todas sus versiones). |
| `/storage/{bucket}/{key}/versions` | GET | Historial de versiones de esa `key`. |

## Un riesgo de routing que había que probar en vivo

`{key:path}` es un converter "greedy": consume el resto de la URL,
barras incluidas. `/storage/{bucket}/{key:path}/versions` se registra
**antes** que `/storage/{bucket}/{key:path}` — si el orden fuera al
revés, `/storage/b/foo/versions` se leería como `key="foo/versions"` en
vez de resolver al listado de versiones de `foo`. Mismo principio con
`/storage/buckets` frente a `/storage/{bucket}`: el router de `buckets.py`
se incluye en `app/main.py` antes que el de `objects.py`, o `"buckets"` se
leería como nombre de bucket. `tests/test_routing.py` lo cubre, y además
se verificó en vivo contra el servicio desplegado (crear bucket, subir dos
versiones de un objeto, `Range`, listar versiones, listar objetos, uso del
bucket, borrar) — las 22 comprobaciones pasaron.

## El contenido de un objeto no pasa por el sobre genérico

`EnvelopeMiddleware` (`freya-common`) envuelve toda respuesta JSON en
`{"success": true, "data": ..., "meta": ...}` decidiendo por content-type —
pero el `GET`/`HEAD /storage/{bucket}/{key}` devuelve los bytes tal cual los
subió quien los subió, con el content-type que ese objeto tenga. Si alguien
sube un objeto con `Content-Type: application/json` (git subía así su
`refs.json`, ver `git/README.md`), esos bytes son indistinguibles
por content-type de una respuesta real de la API — sin el opt-out, el
middleware los envolvía igual y el consumidor recibía el sobre en vez del
contenido original, silenciosamente (ver el bug documentado en git).

Por eso `app/api/objects.py` marca la `Response` de descarga (200, 206 y
`HEAD`) con la cabecera `X-Freya-No-Envelope`
(`freya_common.NO_ENVELOPE_HEADER`): `EnvelopeMiddleware` la reconoce y deja
pasar la respuesta sin tocarla, sin importar el content-type, y retira la
cabecera antes de que llegue al cliente. Cualquier objeto se puede subir con
su content-type real — no hace falta evitar `application/json` como
workaround.

## Un límite real de gestor-db que rompió el cálculo de uso

`bucket_usage` recorre objeto por objeto (`gestor-db` no ofrece
`SUM`/`GROUP BY`, §4 no lo define) y al principio pedía páginas de hasta
10000/1000 filas — pero el DSL de `gestor-db` limita `limit` a 200
(`gestor-db/app/models/requests.py`). `app/domain/buckets.py` y
`app/domain/objects.py` pagina ahora con `_query_all` en páginas de 200.
Sigue siendo O(objetos) por lectura de uso: con muchos objetos, esto pide
un contador mantenido de forma incremental en vez de recalcularlo entero
en cada lectura.

## Estructura

```
app/
├── main.py                buckets ANTES que objects (ver arriba)
├── config.py               data_dir, max_upload_bytes, cuota por defecto
├── deps.py                  JWT estándar de la plantilla
├── api/
│   ├── buckets.py             alta, listado, borrado, uso
│   └── objects.py              PUT/GET/HEAD/DELETE, Range, versiones
├── domain/
│   ├── blob_store.py            bytes en /data, con sharding por id
│   ├── buckets.py                 CRUD + cuota sobre gestor-db
│   └── objects.py                  ciclo de vida de versiones
└── models/requests.py
```

## Pendiente

Subida multiparte (§5.8), restaurar una versión antigua como vigente
(§5.7), `/storage/usage` agregado de todo el tenant (§5.10), y la cascada
de retención de `max_versions` (`storage_lifecycle`, §13.5 — pertenece a
un futuro servicio de automatización, no a este).

## Tests

```powershell
.\freya.ps1 test storage
.\freya.ps1 lint storage
```

`tests/test_blob_store.py` cubre el almacén de bytes sin red ni base.
`tests/test_routing.py` cubre las dos ambigüedades de routing de arriba.
`tests/test_objects.py` cubre que la descarga de un objeto con content-type
JSON no se envuelva (ver "El contenido de un objeto no pasa por el sobre
genérico" arriba).
