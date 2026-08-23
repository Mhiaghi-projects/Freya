-- Metadatos de repositorios (docs/freya-api-contract.md §6). Los objetos y
-- packfiles en sí NO viven aquí: van a storage (bucket "git"), materializados
-- bajo demanda por app/domain/repo_store.py. Esta tabla es sólo el catálogo:
-- qué repos existen, su visibilidad y su configuración de espejo a GitHub.
--
-- git_refs / git_commits / seguimiento del espejo a GitHub quedan para
-- cuando se construya la retención de 5 commits (Fase 5, tarea git-05): su
-- forma depende de cómo se modele "qué vive sólo en GitHub", y diseñarla
-- antes de esa lógica sería adivinar.

CREATE TABLE git_repositories (
    id text PRIMARY KEY,
    repo_name text NOT NULL,
    description text NOT NULL DEFAULT '',
    default_branch text NOT NULL DEFAULT 'main',
    visibility text NOT NULL DEFAULT 'private',
    sensitive boolean NOT NULL DEFAULT false,
    github_mirror_url text,
    github_sync_enabled boolean NOT NULL DEFAULT false,
    secret_validation_enabled boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz
);

CREATE UNIQUE INDEX git_repositories_name_idx
    ON git_repositories (repo_name) WHERE deleted_at IS NULL;
