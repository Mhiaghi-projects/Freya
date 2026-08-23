# Plantilla de servicio Python

Base de todos los servicios propios de Freya. No se toca directamente: se copia
con `.\freya.ps1 new <nombre>`, que la clona dentro del contenedor toolbox y
sustituye los marcadores `__SERVICE_NAME__` y `__SERVICE_PORT__`.

## Qué trae ya resuelto

- Logging JSON con `request_id`, `tenant` y `subject`, y redacción automática de
  campos sensibles.
- Middleware que propaga `X-Request-ID` y resuelve el tenant (`X-Tenant-Context`).
- Formato de error único de Freya en todas las respuestas de error.
- `/health` (sin dependencias) y `/ready` (con comprobaciones en paralelo).
- Cliente de servicio con renovación automática del JWT y validación local
  contra el JWKS cacheado de `auth`.
- Dockerfile multi-stage, usuario sin privilegios, filesystem de sólo lectura,
  límites de recursos y healthcheck.

## Al crear un servicio

1. `.\freya.ps1 new <nombre>` — crea el servicio, su certificado y su secreto.
2. Borrar `app/api/example.py` y escribir los routers reales.
3. Añadir los ajustes propios en `app/config.py`.
4. Registrar las comprobaciones de `/ready` que correspondan en `app/main.py`.
5. Poner las migraciones SQL en `migrations/NNNN_nombre.sql`.
6. Documentar los endpoints en el `README.md` del servicio.
7. Añadir las variables nuevas al `.env.example` de la raíz.

## Estructura

```
app/
├── main.py       creación de la app, lifespan, montaje de routers
├── config.py     settings desde entorno
├── deps.py       dependencias FastAPI (autenticación, tenant)
├── api/          routers, un fichero por recurso
├── domain/       lógica de negocio, sin FastAPI ni SQL
├── infra/        clientes de otros servicios
└── models/       esquemas pydantic
```

Ningún fichero pasa de 500 líneas.

## Tests

Los tests corren dentro del contenedor del servicio, nunca en el host:

```powershell
docker compose -f services\<nombre>\docker-compose.yml run --rm `
  --entrypoint pytest <nombre> -q
```

Los tests de `tests/test_health.py` son el mínimo obligatorio y no se borran.
