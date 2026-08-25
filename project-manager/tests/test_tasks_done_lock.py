"""update_task: una task en "done" queda cerrada -- pedido explícito del
usuario ("no se podrán mover"). El guard corre antes de tocar columnas o
dependencias, así que un gestor-db falso mínimo (sólo get_task) alcanza."""

from __future__ import annotations

import json

import httpx
import pytest
from freya_common import FreyaError, ServiceClient

from app.domain.tasks import DONE_STATUS, update_task


def _client(task_status: str) -> ServiceClient:
    state = {"status": task_status, "priority": "medium"}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["table"] == "pm_tasks"
        if request.url.path == "/mutate":
            state.update(body.get("data") or {})
            return httpx.Response(200, json={"success": True, "data": {}})
        row = {
            "id": "tsk_1", "project_id": "prj_1", "title": "t", "description": "",
            "acceptance_criteria": "", "priority": "medium",
            "difficulty": 1, "story_points": None, "estimated_hours": 1,
            "actual_hours": None, "assigned_to": None, "milestone_id": None,
            "sprint_id": None, "labels": [], "position": 0, "start_date": None,
            "due_date": None, "completed_at": None, "completed_by": None,
            "created_at": "2026-01-01T00:00:00Z",
            **state,
        }
        return httpx.Response(200, json={"success": True, "data": {"rows": [row]}})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return ServiceClient("https://freya-gestor-db:8001", "project-manager", http)


async def test_task_done_no_se_puede_mover() -> None:
    client = _client(DONE_STATUS)
    with pytest.raises(FreyaError) as exc_info:
        await update_task(
            client, "freya", task_id="tsk_1", status="in_progress",
            priority=None, assigned_to=None, actual_hours=None,
            position=None, completed_by=None,
        )
    assert exc_info.value.status_code == 409


async def test_task_no_done_si_se_puede_actualizar_otros_campos() -> None:
    client = _client("in_progress")
    # priority solo, sin tocar status -- no debe pasar por el guard.
    result = await update_task(
        client, "freya", task_id="tsk_1", status=None,
        priority="high", assigned_to=None, actual_hours=None,
        position=None, completed_by=None,
    )
    assert result["status"] == "in_progress"
