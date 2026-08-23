-- Cursor por servicio para el archivador de logs (ROADMAP.md mon-04,
-- acotado: archiva stdout/stderr en storage, no monta ingesta real en
-- VictoriaLogs -- ver app/domain/log_archiver.py). Sin esto cada ciclo
-- volvería a subir el historial entero de cada contenedor.

CREATE TABLE mon_log_cursors (
    service text PRIMARY KEY,
    last_fetched_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);
