#!/usr/bin/env python3
"""Importa projects/*.yaml a project-manager por su propia API
(ROADMAP.md pm-08: "el backlog de Freya pasa a gestionarse desde su propia
API"). No es un endpoint del servicio -- es un script de un solo uso, en la
misma línea que gen_dev_ca.sh o New-FreyaSecret: orquestación desde fuera,
nunca lógica de importación dentro del propio servicio.

    python3 infra/scripts/import_backlog.py

Necesita red hacia freya-mesh (el toolbox corre con --network none por
defecto; .\\freya.ps1 import-backlog lo invoca con -Network) y el
api_secret de project-manager montado en /run/secrets/api_secret.

Las dependencias de PROYECTO en YAML (depends_on entre servicios, p.ej.
git depende de storage/auth/gestor-db) no tienen hueco en el schema de
project-manager -- sólo modela dependencias entre TASKS del mismo proyecto
(el bloqueo real del Kanban, ROADMAP.md pm-03). Se anotan como texto en la
descripción para no perder la información, no como relación real.
"""

from __future__ import annotations

import json
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PROJECTS_DIR = ROOT / "projects"
AUTH_URL = "https://freya-auth:8002"
PM_URL = "https://freya-project-manager:8006"
CTX = ssl._create_unverified_context()


def call(method: str, url: str, headers: dict, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    h = {"Content-Type": "application/json", **headers}
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15, context=CTX) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def get_token() -> str:
    api_secret = Path("/run/secrets/api_secret").read_text(encoding="utf-8").strip()
    status, body = call(
        "POST",
        f"{AUTH_URL}/authenticate/service",
        {},
        {"service": "project-manager", "api_secret": api_secret},
    )
    if status != 200:
        print(f"No se pudo autenticar: {status} {body}", file=sys.stderr)
        raise SystemExit(1)
    return body["data"]["access_token"]


def find_project(headers: dict, name: str) -> dict | None:
    status, body = call("GET", f"{PM_URL}/projects", headers)
    if status != 200:
        return None
    for project in body["data"]:
        if project["project_name"] == name:
            return project
    return None


def import_project(headers: dict, project_yaml: dict) -> None:
    name = project_yaml["id"]
    existing = find_project(headers, name)
    if existing:
        print(f"  {name}: ya existe, se omite")
        return

    depends_on = project_yaml.get("depends_on", [])
    description = project_yaml.get("description", "").strip()
    if depends_on:
        description += f"\n\nDepende de: {', '.join(depends_on)}"

    status, body = call(
        "POST",
        f"{PM_URL}/projects",
        headers,
        {
            "project_name": name,
            "description": description,
            "project_type": "programming",
            "difficulty": project_yaml["difficulty"],
        },
    )
    if status != 201:
        print(f"  {name}: fallo creando el proyecto: {status} {body}", file=sys.stderr)
        return
    project_id = body["data"]["project_id"]
    print(f"  {name}: proyecto creado ({project_id})")

    # Un único paso, en el orden del YAML: las dependencias de cada task
    # siempre apuntan a tasks anteriores del mismo fichero (es una lista en
    # orden de construcción), así que para cuando toca crear una task sus
    # dependencias ya tienen id real -- no hace falta un segundo paso ni un
    # endpoint para añadir dependencias después de crear la task.
    yaml_id_to_task_id: dict[str, str] = {}
    created = 0
    for task in project_yaml["tasks"]:
        yaml_deps = task.get("depends_on", [])
        real_deps = [yaml_id_to_task_id[d] for d in yaml_deps if d in yaml_id_to_task_id]
        missing = [d for d in yaml_deps if d not in yaml_id_to_task_id]
        if missing:
            print(
                f"    {task['id']}: depende de {missing}, no importada(s) todavía "
                "-- se crea sin esa(s) dependencia(s)",
                file=sys.stderr,
            )

        status, body = call(
            "POST",
            f"{PM_URL}/projects/{project_id}/tasks",
            headers,
            {
                "title": task["title"],
                "acceptance_criteria": task.get("acceptance", ""),
                "difficulty": task["difficulty"],
                "depends_on": real_deps,
            },
        )
        if status != 201:
            print(
                f"    {task['id']}: fallo creando la task: {status} {body}",
                file=sys.stderr,
            )
            continue
        yaml_id_to_task_id[task["id"]] = body["data"]["id"]
        created += 1

    print(f"    {created}/{len(project_yaml['tasks'])} tasks importadas")


def main() -> int:
    files = sorted(PROJECTS_DIR.glob("*.yaml"))
    if not files:
        print("No hay ficheros de proyecto en projects/", file=sys.stderr)
        return 1

    token = get_token()
    headers = {"Authorization": f"Bearer {token}"}

    print(f"Importando {len(files)} proyectos...")
    for file in files:
        project_yaml = yaml.safe_load(file.read_text(encoding="utf-8"))
        import_project(headers, project_yaml)

    print("Listo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
