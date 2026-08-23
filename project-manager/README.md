# project-manager

Backlog de Freya: proyectos, tasks, Kanban, milestones, sprints y esfuerzo.
Contrato: `docs/freya-api-contract.md` §7, extendido con dos cosas que el
contrato no cubre pero que ROADMAP.md exige explícitamente (tarea pm-03):
`difficulty` (1-5, el mismo campo que usan `projects/*.yaml` en este mismo
repo) y `acceptance_criteria`. Sin dependencia de `storage` ni de `git`:
sólo habla con `gestor-db`, como cualquier servicio de datos.

## Dificultad, no story points, como unidad principal

El contrato modela el esfuerzo con `story_points` (Fibonacci: 1, 2, 3, 5, 8,
13, 21) para el burndown de sprint. ROADMAP.md pide además `difficulty`
(1-5) para que el backlog de la propia Freya —que ya usa esa escala en sus
YAML— se pueda importar tal cual. Una task admite ambos campos; sólo
`difficulty` es obligatorio. `estimated_hours` se deriva de la dificultad
si no se da explícito (`HOURS_BY_DIFFICULTY` en `app/domain/tasks.py`:
1→2h, 2→4h, 3→8h, 4→16h, 5→32h — dobla por nivel, tan arbitrario y
suficiente como la propia escala Fibonacci del contrato).

## Kanban con columnas por proyecto, no un enum global

Cada proyecto tiene su propia fila de columnas (`pm_board_columns`),
sembrada con las 5 por defecto del contrato (`backlog`, `todo`,
`in_progress`, `testing`, `done`) al crearlo. El `status` de una task se
valida contra las columnas de SU proyecto, no contra un enum fijo — así
"columnas definibles por proyecto" (ROADMAP.md pm-04) es real, aunque hoy
no haya todavía un endpoint para añadir/quitar columnas más allá de la
semilla inicial.

## Una task bloqueada no puede avanzar

`pm_task_dependencies` guarda qué tasks bloquean a cuáles. Mover una task a
cualquier columna que no sea `backlog`/`todo` comprueba primero que todas
sus dependencias estén en `done`; si no, `409 DUPLICATE_RESOURCE` con
`blocking_task_ids` en los detalles (el catálogo de errores no tiene un
código más específico para "bloqueada por dependencia" — se deja anotado
como limitación menor, no como bug).

## Progreso por dificultad, no por recuento

El progreso de un milestone (`GET /milestones/{id}`) es
`suma(difficulty de tasks done) / suma(difficulty de todas)`, no
`tasks_done / tasks_total` — dos tasks triviales completas no deberían
pesar como una sola tarea grande sin empezar (ROADMAP.md pm-05, literal).
Las métricas de sprint sí usan `story_points`, tal como las describe el
contrato (§7.6) — campos distintos para preguntas distintas.

## El backlog de Freya se gestiona desde su propia API (pm-08)

`infra/scripts/import_backlog.py` lee los doce `projects/*.yaml` de este
repo y los crea vía la API REST del propio servicio — no hay lógica de
importación dentro del servicio, ni un endpoint especial para ello, mismo
principio que cualquier otra tarea de orquestación de `infra/scripts/`.
Se invoca con:

```powershell
.\freya.ps1 import-backlog
```

Necesita red hacia `freya-mesh`, así que es la única excepción documentada
al `toolbox` sin red (`Invoke-Toolbox -Network freya-mesh`, ver
`infra/powershell/FreyaCore.psm1`). Idempotente: un proyecto que ya existe
por nombre se omite. Las dependencias ENTRE proyectos del YAML (p.ej. `git`
depende de `storage`/`auth`/`gestor-db`) no tienen hueco en el schema —
sólo se modelan dependencias entre tasks del mismo proyecto, que es lo que
de verdad bloquea el Kanban — así que quedan anotadas como texto en la
descripción del proyecto, no como relación real. Las dependencias entre
TASKS sí se resuelven de verdad: el script procesa cada proyecto en el
orden del YAML (las dependencias siempre apuntan a tasks anteriores del
mismo fichero) y las pasa ya resueltas a `depends_on` en la creación,
porque la API no tiene ni necesita un endpoint para añadir una dependencia
después de crear la task.

Verificado en vivo: los 12 proyectos y sus 92 tasks se importaron con la
dificultad y el criterio de aceptación correctos, y mover una task
importada (p.ej. "Protocolo Git smart HTTP", que depende de "Almacén de
repositorios sobre storage") a `in_progress` antes de completar su
dependencia devolvió el `409` esperado.

## Endpoints

`Authorization: Bearer <jwt>`. Permisos:
`read:project-manager` / `write:project-manager` / `admin:project-manager`.

| Ruta | Método | Qué hace |
|---|---|---|
| `/projects` | POST / GET | `409` si el nombre ya existe. `422` si `ci_cd_enabled` con `project_type != programming`, o `linked_git_repo` con `project_type: general`. |
| `/projects/{id}` | GET / DELETE | |
| `/projects/{id}/kanban` | GET | Columnas del proyecto con sus tasks, en el shape de §7.5. |
| `/projects/{id}/tasks` | POST / GET | `GET` filtra por `?status&sprint_id&milestone_id&assigned_to`. |
| `/tasks/{id}` | GET / PUT / DELETE | `PUT` cambia status (con el chequeo de bloqueo), priority, assigned_to, actual_hours o position. |
| `/tasks/{id}/link-commit` | POST | `{repo_id, commit_hash}`. No valida contra `git` que el commit exista (ver Pendiente). |
| `/tasks/{id}/commits` | GET | Commits vinculados a la task. |
| `/projects/{id}/milestones` | POST / GET | |
| `/milestones/{id}` | GET | Progreso calculado por dificultad. |
| `/projects/{id}/sprints` | POST / GET | |
| `/projects/{id}/sprints/{id}` | GET / PUT | `GET` incluye métricas en vivo (sin snapshot diario de burndown, ver Pendiente). |

## Estructura

```
app/
├── main.py                  sólo gestor-db: sin storage, sin git
├── api/
│   ├── projects.py            proyectos + kanban
│   ├── tasks.py                tasks + link-commit
│   ├── milestones.py            progreso por dificultad
│   └── sprints.py                métricas en vivo
└── domain/
    ├── projects.py             reglas de §7.1, columnas
    ├── tasks.py                 dificultad→horas, bloqueo por dependencias
    ├── milestones.py            suma de dificultad
    ├── sprints.py                suma de story_points
    └── commits.py                vínculo task-commit
```

## Pendiente

`freya_access_enabled` (§7.1: crear tenant + cuenta de servicio + secreto
al crear un proyecto) — orquestación real entre `auth`, `secrets` y
`gestor-db` que merece su propio diseño, no encaja como añadido de esta
fase. Integración iCloud (§7.9) y diseños de electrónica (§7.8) — ninguna
de las dos tiene sentido sin la integración externa/de storage real que
implican. Cálculo de XP y `events_emitted` al completar una task (§7.3) —
depende de `gamification`, que no existe todavía (Fase 10); hoy `PUT
/tasks/{id}` con `status: done` sólo marca `completed_at`/`completed_by`,
sin esos campos. Webhooks. Vínculo automático commit↔task por mensaje
(`#tsk_...`, alternativa de §7.4) — necesitaría que `git` parseara
mensajes de commit en cada push y llamara aquí; por ahora sólo existe el
vínculo manual. Snapshot diario de burndown — pide un job programado
(futura "automation", §13). Validar contra `git` que un commit vinculado
existe de verdad.

## Tests

```powershell
.\freya.ps1 test project-manager
.\freya.ps1 lint project-manager
```

`tests/test_validation.py` cubre las validaciones puras (tipo de proyecto,
dificultad, prioridad, story points) sin red ni base. Verificado además en
vivo contra el servicio desplegado: crear proyecto, rechazar
`ci_cd_enabled` inválido, crear milestone y dos tasks dependientes, mover
la bloqueada (`409`), completar la que bloquea, mover la que ya no está
bloqueada, tablero Kanban, progreso de milestone por dificultad (60%),
sprint, vincular y listar un commit, borrar — 21 comprobaciones, dos veces
seguidas.
