# dashboards

Grafana, bajo perfil opcional (ROADMAP.md mon-07: "apagado por defecto").

## Arranque

```powershell
.\freya.ps1 secret dashboards admin_password   # una sola vez
.\freya.ps1 up dashboards
```

`Start-FreyaService` añade `--profile dashboards` sólo para este servicio
(ver `infra/powershell/FreyaServices.psm1`): `docker compose up` a secas,
sin ese profile, ignora por completo el único servicio de este fichero —
es el mecanismo real que lo mantiene apagado, no una convención.

El secreto `admin_password` necesita el dueño 472:472 (usuario `grafana`
de la imagen oficial, no el 10001 de los servicios propios de Freya):

```powershell
.\freya.ps1 secret dashboards admin_password -Owner 472:472
```

## Fuentes de datos

Pre-provisionada en `infra/grafana/provisioning/datasources/datasources.yaml`:
sólo VictoriaMetrics (tipo `prometheus` incorporado, sin plugin), por su
nombre de contenedor en `freya-mon`. No editable desde la UI
(`editable: false`) — el fichero es la fuente de verdad.

VictoriaLogs **no** está provisionada: necesitaría el plugin
`victoriametrics-logs-datasource`, instalable sólo con salida a internet.
`freya-mon` es `--internal` (docs/ARCHITECTURE.md §4) a propósito, así que
Grafana no tiene esa salida — se intentó con `GF_INSTALL_PLUGINS` en
arranque y **tumbaba el proceso entero** al fallar la resolución DNS de
`grafana.com` (verificado en vivo, no una suposición). La única vía real
sería un `Dockerfile` propio para esta imagen que instale el plugin en
tiempo de construcción (con red), no en arranque del contenedor — queda
pendiente.

## Acceso

No publicado al host todavía (`docs/ARCHITECTURE.md`, tabla de
servicios): llegará a través del gateway de `frontend` en la Fase 9. Para
verlo localmente antes de eso, añade un override de compose con
`ports: ["3000:3000"]` — no se hace por defecto aquí.
