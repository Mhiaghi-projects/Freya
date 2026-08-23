#!/usr/bin/env python3
"""Valida el backlog de projects/ y recalcula la tabla de estado.

    python3 infra/scripts/backlog_stats.py

Comprueba: dificultades en rango, identificadores de task únicos, dependencias
de proyecto y de task existentes. Sale con código 1 si algo no cuadra.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

XP_BY_DIFFICULTY = {1: 10, 2: 25, 3: 60, 4: 150, 5: 400}

ROOT = Path(__file__).resolve().parents[2]
PROJECTS_DIR = ROOT / "projects"


def main() -> int:
    files = sorted(PROJECTS_DIR.glob("*.yaml"))
    if not files:
        print("No hay ficheros de proyecto en projects/", file=sys.stderr)
        return 1

    projects: list[dict] = [yaml.safe_load(f.read_text(encoding="utf-8")) for f in files]
    project_ids = {p["id"] for p in projects}
    seen_tasks: set[str] = set()
    problems: list[str] = []

    rows: list[tuple[str, int, int, int, int]] = []

    for project in projects:
        local_ids = {t["id"] for t in project["tasks"]}
        total_xp = 0

        for dependency in project.get("depends_on", []):
            if dependency not in project_ids:
                problems.append(
                    f"{project['id']}: depende del proyecto inexistente '{dependency}'"
                )

        for task in project["tasks"]:
            difficulty = task["difficulty"]
            if difficulty not in XP_BY_DIFFICULTY:
                problems.append(f"{task['id']}: dificultad {difficulty} fuera de 1-5")
                continue
            if task["id"] in seen_tasks:
                problems.append(f"{task['id']}: identificador de task duplicado")
            seen_tasks.add(task["id"])
            total_xp += XP_BY_DIFFICULTY[difficulty]

            for dependency in task.get("depends_on", []):
                if dependency not in local_ids:
                    problems.append(
                        f"{task['id']}: depende de '{dependency}', que no está en el proyecto"
                    )

        rows.append(
            (
                project["id"],
                project["phase"],
                project["difficulty"],
                len(project["tasks"]),
                total_xp,
            )
        )

    print("| Proyecto | Fase | Dificultad | Tasks | XP total |")
    print("|---|---|---|---|---|")
    for row in sorted(rows, key=lambda r: r[1]):
        print("| %s | %s | %s | %s | %s |" % row)
    print(
        "| **Total** | | | **%d** | **%d** |"
        % (sum(r[3] for r in rows), sum(r[4] for r in rows))
    )

    if problems:
        print("\nProblemas encontrados:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    print("\nBacklog válido.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
