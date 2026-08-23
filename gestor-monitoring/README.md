# gestor-monitoring

Métricas, health checks y (más adelante) logs de Freya. Es un "gestor"
como `gestor-db`: habla el protocolo nativo de sus contenedores
(VictoriaMetrics, VictoriaLogs) por la red privada `freya-mon`, y es el
único servicio con esa ruta de red (docs/ARCHITECTURE.md §2, §4). Contrato:
docs/freya-api-contract.md §11, con la superficie recortada al núcleo —
ver Pendiente.

## La única excepción a "nada toca Docker salvo freya.ps1"

Descubrir servicios "sin reinicio" cuando se añade uno nuevo (ROADMAP.md
mon-02) necesita saber qué contenedores existen. La alternativa sin tocar
Docker —una lista estática que `freya.ps1` regenera— no es descubrimiento
de verdad: depende de que todo cambio pase por `freya.ps1`, y dejaría de
funcionar en el momento en que algo no lo haga. Se eligió montar
`/var/run/docker.sock` **de sólo lectura** (`docker-compose.yml`), en la
línea de cómo Traefik, Prometheus o cAdvisor resuelven exactamente este
problema. `app/domain/docker_client.py` es un cliente HTTP mínimo sobre
ese socket (no el SDK de Docker, que pesa mucho más de lo que hace falta):
lista contenedores por la etiqueta `freya.service` y lee
`freya.metrics.port`/`freya.metrics.path`. Nunca crea, para ni modifica
nada — sólo `GET /containers/json`.

Esto es una concesión de seguridad real: el socket de Docker equivale a
control total del host si el contenedor se viera comprometido. Se acota
todo lo posible (montaje `:ro`, `read_only: true` en el resto del
filesystem, `cap_drop: ALL`, usuario sin privilegios) pero la superficie
de riesgo del socket en sí no desaparece con eso.

El socket es `660 root:root` en Docker Desktop (comprobado en vivo, no
asumido): el proceso sigue como UID 10001 -- nunca root -- pero necesita
el grupo 0 como suplementario (`group_add: ["0"]` en `docker-compose.yml`)
para que el permiso de grupo del socket le alcance. Es la única cesión de
privilegio de este servicio; todo lo demás sigue igual de restringido que
cualquier otro.

## `/metrics` no existía todavía en ningún servicio

Cada `docker-compose.yml` propio ya declaraba las etiquetas
`freya.metrics.port`/`freya.metrics.path` desde la Fase 0, pero
`create_app()` (`freya-common`) nunca había montado una ruta
`/metrics` real — sin esto, este servicio no tendría nada que scrapear.
Se añadió en `freya-common/freya_common/metrics.py` (contadores y
histograma con `prometheus_client`, la librería oficial: reimplementar el
formato de exposición Prometheus a mano es reinventar algo ya resuelto) y
se conectó donde `ContextMiddleware` ya mide método/ruta/estado/duración
de cada petición para el log de acceso — se registra la misma medición
como métrica ahí mismo, sin una segunda pasada de timing. Efecto: los seis
servicios ya construidos (`gestor-db`, `auth`, `secrets`, `storage`,
`git`, `project-manager`) exponen métricas reales en cuanto se
reconstruyen con la versión nueva de `freya_common`.

## Scrape y "consultable por PromQL" de verdad

`app/domain/scraper.py` descubre contenedores, pide `/metrics` a cada uno
por HTTPS (misma malla, mismo JWT que cualquier llamada de servicio) y
reenvía el texto **tal cual** a VictoriaMetrics vía
`/api/v1/import/prometheus` — no se parsea ni se reinterpreta, VictoriaMetrics
ya sabe leer el formato Prometheus. Se añade `service="<nombre>"` como
`extra_label` porque las métricas de `freya_common` no lo incluyen (cada
proceso sólo conoce su propio nombre a través de este import).

`GET /monitoring/metrics/{service}?metric=...` traduce un puñado de
nombres "amigables" (`request_rate`, `error_rate`, `response_time_ms`) a
PromQL real contra las series que expone `freya_common.metrics`
(`app/domain/query.py`) — pero cualquier otro valor de `metric` se trata
como una expresión PromQL **cruda**, pasada a
`/api/v1/query_range` sin traducir. Es la vía de escape que hace la
consulta "por PromQL" de verdad, no sólo los tres atajos previstos.

## Cloud Health necesita historial, no sólo el estado de ahora

`uptime_percent_24h` (§11.1) no se puede calcular sin guardar cada
comprobación. `app/domain/health_monitor.py` golpea `/ready` de cada
servicio descubierto cada `scrape_interval_seconds` y guarda el resultado
en `mon_health_checks` (gestor-db) — `GET /monitoring/services` cruza el
último resultado en memoria (rápido) con el % calculado sobre las últimas
24h en la base (bkg/history).

## Endpoints

`Authorization: Bearer <jwt>`. Permisos: `read:monitoring` / `write:monitoring`.

| Ruta | Método | Qué hace |
|---|---|---|
| `/monitoring/services` | GET | Estado agregado de todos los servicios descubiertos + resumen. |
| `/monitoring/services/{service}` | GET | Detalle de uno. `404` si no está descubierto. |
| `/monitoring/services/{service}/health-check` | POST | Fuerza una comprobación inmediata (no espera al próximo ciclo). |
| `/monitoring/metrics/{service}` | GET | `?metric&resolution&since_seconds`. Ver arriba. |
| `/monitoring/dashboard` | GET | Mismo resumen que `/services`, forma reducida. |

## Estructura

```
app/
├── main.py                   arranca Scraper y HealthMonitor como tareas de fondo
├── config.py                   metrics_url, logs_url, docker_socket, intervalos
├── api/monitoring.py            los endpoints de §11 recortados al núcleo
└── domain/
    ├── docker_client.py          socket de Docker, sólo lectura
    ├── scraper.py                  /metrics de cada servicio -> VictoriaMetrics
    ├── health_monitor.py            /ready de cada servicio -> mon_health_checks
    ├── query.py                     nombre amigable o PromQL cruda -> query_range
    └── services.py                   agregación para Cloud Health
```

`services/metrics/`, `services/logs/` y `services/dashboards/` son
contenedores de terceros (VictoriaMetrics, VictoriaLogs, Grafana) con su
propio `docker-compose.yml`, sin código propio — mismo patrón que
`services/database/`.

## Grafana, apagado por defecto

`services/dashboards/docker-compose.yml` marca su único servicio con
`profiles: [dashboards]`: `docker compose up` a secas lo ignora. Sólo se
levanta con:

```powershell
.\freya.ps1 up dashboards
```

(`Start-FreyaService` añade `--profile dashboards` sólo para este
servicio — ver `infra/powershell/FreyaServices.psm1`.) No está publicado
al host todavía (docs/ARCHITECTURE.md, tabla de servicios): llegará a
través del gateway de `frontend` en la Fase 9. Las fuentes de datos
(VictoriaMetrics, VictoriaLogs) ya están pre-provisionadas
(`infra/grafana/provisioning/datasources/`).

## Pendiente

Recolección de logs (mon-04): el contenedor `logs` (VictoriaLogs) ya
existe y tiene retención acotada, pero nada envía datos ahí todavía —
necesita seguir el stream de stdout de cada contenedor por el mismo socket
de Docker (`/containers/{id}/logs?follow=true`), parsear las líneas JSON
de `freya_common.logging` y reenviarlas a VictoriaLogs; es un subsistema
en sí mismo, se deja para su propia pasada. Reglas de alerta y
notificaciones (mon-06), y con ellas `/monitoring/alerts` e incidentes
(§11.3, §11.4) — dependen de mon-04 y de tener un canal de notificación
real. `/monitoring/sla` y `/monitoring/deployment-log` (depende de
`cicd`, que no existe todavía). Webhooks (`alert.triggered`, etc.).

## Tests

```powershell
.\freya.ps1 test gestor-monitoring
.\freya.ps1 lint gestor-monitoring
```

`tests/test_query.py` cubre la traducción de métricas amigables a PromQL y
la vía de escape de PromQL cruda, sin red.
