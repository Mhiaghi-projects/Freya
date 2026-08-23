# secrets

Vault de secretos de Freya. Custodia API keys, contraseñas de servicio,
certificados y tokens de todos los tenants. Pasa por `gestor-db` para todo
dato, igual que cualquier otro servicio — sólo la master key vive fuera de
la base, en un fichero montado. Contrato: `docs/freya-api-contract.md` §9.

## Envelope encryption

Una **master key** (32 bytes, `.\freya.ps1 secret secrets master_key`,
montada en `/run/secrets/master_key`) nunca toca la base. Cifra una **DEK**
(clave de datos) aleatoria de 256 bits por tenant — se genera la primera
vez que un tenant guarda un secreto, y se reutiliza para todos los suyos.
La DEK es la que cifra cada valor, con AES-256-GCM y un nonce distinto por
cifrado. La base, robada entera, no revela nada sin la master key: ni
siquiera con todas las filas de `secrets`/`secret_versions` en la mano.

Rotar la master key (pendiente de construir) sólo tendría que re-envolver
la DEK de cada tenant, no re-cifrar cada secreto uno a uno — mucho más
barato.

## Namespace = tenant

Un tenant sólo accede a su propio namespace: el `{namespace}` de la ruta
tiene que coincidir con `X-Tenant-Context`, si no es `403 TENANT_MISMATCH`
— mismo principio que `gestor-db` con el `schema` del cuerpo.

## Endpoints

`Authorization: Bearer <jwt>`. Permisos: `read:secrets` / `write:secrets`
(y `write:certs` para `/certs/*`, aparte a propósito — ver abajo).

| Ruta | Método | Qué hace |
|---|---|---|
| `/secrets/{namespace}` | POST | `{key, value, type, expires_at, description, overwrite}`. Crea (versión 1) o, con `overwrite: true` sobre uno existente, añade versión nueva. |
| `/secrets/{namespace}` | GET | Lista claves del namespace, sin valores. |
| `/secrets/{namespace}/audit-logs` | GET | `?limit&action`. Accesos registrados: quién, qué, cuándo — nunca el valor. |
| `/secrets/{namespace}/{key}` | GET | `?version&metadata_only`. Sin `version`, la vigente. Descifra al vuelo. |
| `/secrets/{namespace}/{key}` | PUT | `{value, expires_at}`. Nueva versión (no destruye las anteriores). |
| `/secrets/{namespace}/{key}` | DELETE | `?version`. Sin `version`, borrado lógico del secreto entero. |
| `/secrets/{namespace}/{key}/rotate` | POST | `{new_value}`. Nueva versión + registra `previous_version`. |
| `/secrets/{namespace}/{key}/versions` | GET | Historial de versiones, sin valores. |
| `/certs/{service}/issue` | POST | Emite un certificado nuevo firmado por la CA interna. `{tls_key, tls_crt, ca_crt}` en PEM. |

El `value` nunca se devuelve en `POST`/`PUT` — sólo en el `GET` de lectura,
y sólo si `metadata_only` no está activo.

## CA interna (sec-05, ya no pendiente)

`gen_dev_ca.sh` (Fase 0) sigue emitiendo el primer certificado de cada
servicio — es irresoluble de otra forma: hace falta un cert antes de que
ningún contenedor, `secrets` incluido, pueda hablar HTTPS con nadie. Pero
a partir de ahí, la renovación pasa por aquí: `app/domain/ca.py` guarda la
clave privada de la CA como un secreto más (`_internal_ca_key`,
`overwrite: false` — una CA nueva no puede sustituir en silencio a la que
ya firma la malla en producción), protegida por la misma envelope
encryption que cualquier otro valor. `POST /certs/{service}/issue` genera
un par RSA 2048 nuevo, arma el certificado (SAN, `keyUsage`,
`extendedKeyUsage` — mismos parámetros que emitía `gen_dev_ca.sh`) y lo
firma con esa clave.

`infra/certs/ca/ca.key` ya no existe en disco — se importó una vez
(`.\freya.ps1 init-internal-ca`, idempotente) y se borró a mano tras
confirmar que los 8 servicios arrancaban con certificados nuevos. Sólo
queda `ca.crt` (público, la CA raíz que cada contenedor necesita para
confiar en la malla) y el primer certificado de cada servicio, ambos
imprescindibles para el arranque en frío. Renovar uno:
`.\freya.ps1 renew-cert <servicio>` seguido de
`.\freya.ps1 restart <servicio>`.

Pendiente: revocación (no hace falta todavía porque nada la ha pedido en
uso real) y rotación automática por caducidad (Fase 11).

## Un bug real que dejó una regresión en los tests

`GET /secrets/{namespace}/{key}` (genérico) capturaba
`/secrets/{namespace}/audit-logs` porque FastAPI resuelve por orden de
registro y el genérico estaba declarado antes. `tests/test_routing.py`
comprueba que `/audit-logs` sigue registrado primero.

## Estructura

```
app/
├── main.py                  creación de la app, lifespan, master key
├── config.py                  settings: ruta de la master key
├── deps.py                     JWT estándar de la plantilla
├── api/
│   ├── secrets.py                los ocho endpoints de §9
│   └── certs.py                   /certs/{service}/issue
├── domain/
│   ├── crypto.py                 envelope encryption AES-256-GCM
│   ├── vault.py                   CRUD versionado sobre gestor-db
│   └── ca.py                       emisión de certificados (sec-05)
└── models/requests.py
```

## Pendiente

Rotación de la master key (sec-04), revocación de certificados, y el
retorno donde `gestor-db` y `auth` piden sus propias credenciales a
`secrets` en vez de leerlas de ficheros montados (sec-07).

## Tests

```powershell
.\freya.ps1 test secrets
.\freya.ps1 lint secrets
```

`tests/test_crypto.py` cubre el cifrado sin red ni base.

## Despliegue

`git push` a `main` con cambios bajo `secrets/` dispara
`.github/workflows/deploy-secrets.yml` en el runner autoalojado
(`services/github-runner/`, `docs/DECISIONS.md`) -- build, lint, test,
security_scan y despliegue en este mismo PC, sin intervención manual.
