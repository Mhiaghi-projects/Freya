"""Catálogo estático de servicios (docs/ROADMAP.md Fase 9, punto 3).

No hay ningún servicio que exponga hoy "quién soy y qué expongo" por API
(cada README lo documenta a mano) -- este catálogo es la lista mínima que
permite construir la vista sin inventar ese contrato todavía. El estado
"vivo" sale de gestor-monitoring (app/api/dashboard.py), no de aquí.
"""

from __future__ import annotations

SERVICES: list[dict[str, str]] = [
    {
        "name": "gestor-db",
        "phase": "1",
        "description": "Acceso a datos multi-tenant sobre PostgreSQL.",
    },
    {
        "name": "auth",
        "phase": "2",
        "description": "Identidad: JWT, JWKS, autenticación de servicios y usuarios.",
    },
    {
        "name": "secrets",
        "phase": "3",
        "description": "Vault de secretos y CA interna.",
    },
    {
        "name": "storage",
        "phase": "4",
        "description": "Objetos versionados, tipo S3, sobre gestor-db.",
    },
    {
        "name": "git",
        "phase": "5",
        "description": "Control de versiones propio (smart HTTP + API REST).",
    },
    {
        "name": "project-manager",
        "phase": "6",
        "description": "Proyectos, tareas, sprints y milestones.",
    },
    {
        "name": "gestor-monitoring",
        "phase": "7",
        "description": "Salud, métricas y logs de la malla.",
    },
    {
        "name": "cicd",
        "phase": "8",
        "description": "Pipelines de lint/test/security_scan y despliegues.",
    },
    {
        "name": "frontend",
        "phase": "9",
        "description": "Este panel y sus API (Traefik termina TLS por delante).",
    },
]
