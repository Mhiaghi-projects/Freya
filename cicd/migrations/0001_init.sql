-- CI/CD de Freya (docs/freya-api-contract.md §8), alcance recortado a lo
-- que se aprobó en vivo con el usuario: sólo el pipeline "standard-tests"
-- (build de la etapa `dev` del Dockerfile del servicio + lint/pytest,
-- exactamente lo que ya hace `.\freya.ps1 test`/`lint`, ahora ejecutado de
-- verdad por este servicio) y un Deployment Manager que sólo MODELA el
-- despliegue -- nunca toca otros contenedores -- y que bloquea si la
-- ejecución que lo respalda no fue un éxito. Ver README.

CREATE TABLE ci_pipelines (
    id text PRIMARY KEY,
    name text NOT NULL,
    service text NOT NULL,
    pipeline_type text NOT NULL DEFAULT 'standard-tests',
    created_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz
);

CREATE UNIQUE INDEX ci_pipelines_name_idx
    ON ci_pipelines (name) WHERE deleted_at IS NULL;

CREATE TABLE ci_runs (
    id text PRIMARY KEY,
    pipeline_id text NOT NULL REFERENCES ci_pipelines (id) ON DELETE CASCADE,
    status text NOT NULL DEFAULT 'queued',
    triggered_by text NOT NULL DEFAULT 'manual',
    trigger_ref text,
    started_at timestamptz,
    finished_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ci_runs_pipeline_idx ON ci_runs (pipeline_id, created_at DESC);

CREATE TABLE ci_jobs (
    id text PRIMARY KEY,
    run_id text NOT NULL REFERENCES ci_runs (id) ON DELETE CASCADE,
    name text NOT NULL,
    status text NOT NULL DEFAULT 'queued',
    exit_code int,
    log text NOT NULL DEFAULT '',
    started_at timestamptz,
    finished_at timestamptz
);

CREATE INDEX ci_jobs_run_idx ON ci_jobs (run_id);

-- Reservada para cuando haya algo real que subir (hoy los jobs son
-- lint/test, sin artefacto más allá del log) -- completa el schema que
-- pide ROADMAP.md ci-01, sin uso todavía.
CREATE TABLE ci_artifacts (
    id text PRIMARY KEY,
    run_id text NOT NULL REFERENCES ci_runs (id) ON DELETE CASCADE,
    job_id text REFERENCES ci_jobs (id) ON DELETE CASCADE,
    storage_bucket text NOT NULL,
    storage_key text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- Sólo el modelo: nunca toca otros contenedores (ver README, "Deployment
-- Manager simulado"). status siempre queda en 'simulated' si se crea, o el
-- alta se rechaza con 409 si pipeline_run_id no es una ejecución exitosa.
CREATE TABLE ci_deployments (
    id text PRIMARY KEY,
    service text NOT NULL,
    version_ref text NOT NULL,
    status text NOT NULL DEFAULT 'simulated',
    pipeline_run_id text NOT NULL REFERENCES ci_runs (id),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ci_deployments_service_idx ON ci_deployments (service, created_at DESC);
