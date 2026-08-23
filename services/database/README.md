# database

PostgreSQL 16 (Alpine). Persistencia de toda Freya y de los tenants externos.

No es un servicio HTTP: no tiene `/health` ni `/api/v1`. El único cliente es
`gestor-db`, que le habla el protocolo nativo de PostgreSQL por la red privada
`freya-db`. Ningún otro contenedor tiene ruta de red hasta aquí — ver
`docs/ARCHITECTURE.md` §3-4.

## Arranque

```powershell
.\freya.ps1 secret database postgres_password   # una sola vez
.\freya.ps1 up database
```

La misma contraseña debe existir también en `infra/secrets/gestor-db/postgres_password`
(gestor-db es el único otro consumidor del protocolo nativo). Fase 3 (`secrets`)
elimina esta duplicación.

## Ajuste de memoria (db-03)

`shared_buffers=64MB`, `work_mem=4MB`, `effective_cache_size=192MB`,
`max_connections=40` — ver `docker-compose.yml`. Objetivo: quedarse bajo
256 MB en reposo, con margen para el pool de conexiones de `gestor-db`.

## Backup y restauración (db-04, ROADMAP.md Fase 11 adelantada)

```powershell
.\freya.ps1 backup database
.\freya.ps1 restore-check database <clave-storage>   # p.ej. database/freya-20260821-203735.dump
```

`backup` genera un volcado con `pg_dump -Fc`, lo sube al bucket `backups` de
`storage` (clave `database/<fichero>`, vía la identidad operativa
`freya-ops` — ver `infra/scripts/backup_upload.py`) y borra la copia local:
nada del volcado sobrevive en el host más que el instante entre `pg_dump` y
la subida. `restore-check` hace el camino inverso — descarga la clave dada,
la recupera en una base temporal (`freya_restore_check`), confirma que
`pg_restore` termina sin errores y borra tanto la base temporal como el
fichero descargado — nunca toca los datos reales.
