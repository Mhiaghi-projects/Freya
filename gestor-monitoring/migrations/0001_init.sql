-- Historial de health checks (docs/freya-api-contract.md §11.1: "uptime_percent_24h"
-- necesita historial, no sólo el estado actual). Las métricas en sí NO viven
-- aquí -- van a VictoriaMetrics (bucket de series temporales de verdad);
-- esta tabla es sólo la traza de /ready de cada servicio para calcular
-- disponibilidad.

CREATE TABLE mon_health_checks (
    id text PRIMARY KEY,
    service text NOT NULL,
    status text NOT NULL,
    response_time_ms int,
    error text,
    checked_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX mon_health_checks_service_time_idx
    ON mon_health_checks (service, checked_at DESC);
