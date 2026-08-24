-- Tres columnas usadas de verdad en WHERE (app/domain/milestones.py:78
-- list_milestones, app/domain/sprints.py:118 list_sprints, app/domain/
-- tasks.py:222-223 list_tasks ?assigned_to=) que se quedaron sin índice
-- cuando se creó cada tabla -- a diferencia de pm_tasks.project_id, que
-- sí lo tiene desde el principio (pm_tasks_project_status_idx). Sin
-- éstos, listar los milestones o sprints de un proyecto, o filtrar tasks
-- por responsable, recorre la tabla entera.

CREATE INDEX pm_milestones_project_idx ON pm_milestones (project_id);
CREATE INDEX pm_sprints_project_idx ON pm_sprints (project_id);
CREATE INDEX pm_tasks_assigned_to_idx ON pm_tasks (assigned_to);
