-- Backlog de Freya (docs/freya-api-contract.md §7, con extensiones que el
-- contrato no cubre pero que ROADMAP.md exige explícitamente: "dificultad"
-- 1-5 por task/proyecto, igual que projects/*.yaml de este mismo repo, y
-- criterio de aceptación en texto libre.

CREATE TABLE pm_projects (
    id text PRIMARY KEY,
    project_name text NOT NULL,
    description text NOT NULL DEFAULT '',
    project_type text NOT NULL,
    visibility text NOT NULL DEFAULT 'private',
    difficulty int,
    linked_git_repo text,
    ci_cd_enabled boolean NOT NULL DEFAULT false,
    team_members text[] NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz
);

CREATE UNIQUE INDEX pm_projects_name_idx
    ON pm_projects (project_name) WHERE deleted_at IS NULL;

-- Columnas del Kanban por proyecto: "configurable" (ROADMAP.md pm-04)
-- significa que el status de una task se valida contra las columnas de SU
-- proyecto, no contra un enum global. create_project siembra las 5 por
-- defecto del contrato (§7.2).
CREATE TABLE pm_board_columns (
    id text PRIMARY KEY,
    project_id text NOT NULL REFERENCES pm_projects (id) ON DELETE CASCADE,
    key text NOT NULL,
    label text NOT NULL,
    position int NOT NULL,
    wip_limit int,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX pm_board_columns_project_key_idx
    ON pm_board_columns (project_id, key);

CREATE TABLE pm_milestones (
    id text PRIMARY KEY,
    project_id text NOT NULL REFERENCES pm_projects (id) ON DELETE CASCADE,
    title text NOT NULL,
    description text NOT NULL DEFAULT '',
    target_date date,
    created_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz
);

CREATE TABLE pm_sprints (
    id text PRIMARY KEY,
    project_id text NOT NULL REFERENCES pm_projects (id) ON DELETE CASCADE,
    name text NOT NULL,
    goal text NOT NULL DEFAULT '',
    status text NOT NULL DEFAULT 'planned',
    start_date date,
    end_date date,
    created_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz
);

CREATE TABLE pm_tasks (
    id text PRIMARY KEY,
    project_id text NOT NULL REFERENCES pm_projects (id) ON DELETE CASCADE,
    title text NOT NULL,
    description text NOT NULL DEFAULT '',
    acceptance_criteria text NOT NULL DEFAULT '',
    status text NOT NULL DEFAULT 'backlog',
    priority text NOT NULL DEFAULT 'medium',
    difficulty int NOT NULL DEFAULT 3,
    story_points int,
    estimated_hours numeric(6, 2),
    actual_hours numeric(6, 2),
    assigned_to text,
    milestone_id text REFERENCES pm_milestones (id) ON DELETE SET NULL,
    sprint_id text REFERENCES pm_sprints (id) ON DELETE SET NULL,
    labels text[] NOT NULL DEFAULT '{}',
    position int NOT NULL DEFAULT 0,
    start_date date,
    due_date date,
    completed_at timestamptz,
    completed_by text,
    created_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz
);

CREATE INDEX pm_tasks_project_status_idx ON pm_tasks (project_id, status);
CREATE INDEX pm_tasks_milestone_idx ON pm_tasks (milestone_id);
CREATE INDEX pm_tasks_sprint_idx ON pm_tasks (sprint_id);

-- "una task bloqueada no puede pasar a en curso" (ROADMAP.md pm-03): task
-- bloqueada mientras cualquier fila aquí con task_id = ella apunte a una
-- depends_on_task_id que no esté en status 'done'.
CREATE TABLE pm_task_dependencies (
    task_id text NOT NULL REFERENCES pm_tasks (id) ON DELETE CASCADE,
    depends_on_task_id text NOT NULL REFERENCES pm_tasks (id) ON DELETE CASCADE,
    PRIMARY KEY (task_id, depends_on_task_id)
);

-- repo_id no es FK: vive en el schema de git, otro servicio (docs/freya-api-contract.md §7.4).
CREATE TABLE pm_task_commits (
    id text PRIMARY KEY,
    task_id text NOT NULL REFERENCES pm_tasks (id) ON DELETE CASCADE,
    repo_id text NOT NULL,
    commit_hash text NOT NULL,
    linked_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX pm_task_commits_unique_idx
    ON pm_task_commits (task_id, repo_id, commit_hash);
