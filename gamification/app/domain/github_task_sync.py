"""Sincroniza XP desde GitHub Issues, en vez de project-manager
(docs/DECISIONS.md, "migrar git/project-manager/cicd a GitHub").

Apagado por defecto (`settings.use_github_task_sync`): activarlo pide
`github_owner`, `github_repos` y un PAT en
infra/secrets/gamification/github_pat -- mismo PAT que
services/github-runner/ (ver infra/secrets/github-runner/README.md).
Mientras no esté todo eso, TaskSyncer (app/domain/task_sync.py) sigue
siendo el que corre.

GitHub Issues no tiene un campo "dificultad" nativo: se lee de una label
con el patrón `difficulty:N` (N entre 1 y 5, igual que project-manager).
Sin esa label, se usa la dificultad por defecto (3, igual que
task_sync.py). El "quién" no sale del issue -- GitHub no tiene un usuario
de Freya que mapear sin construir un sistema de vínculo de identidades que
nadie ha pedido todavía (ver docs/DECISIONS.md): toda la XP de GitHub va a
`settings.github_default_user_id`, razonable para una plataforma de un
único usuario real como ésta hoy.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
from datetime import UTC, datetime

import httpx
from freya_common import FreyaError, gdb_mutate, gdb_query, new_id
from freya_common import ServiceClient as GestorDbClient

from app.domain.achievements import check_and_unlock
from app.domain.stats import award_xp, count_completed_tasks, get_stats

logger = logging.getLogger(__name__)

_SOURCE = "github_issue"
_XP_PER_DIFFICULTY = 15
_DEFAULT_DIFFICULTY = 3
_DIFFICULTY_LABEL = re.compile(r"^difficulty:([1-5])$")


def _difficulty_from_labels(labels: list[dict]) -> int:
    for label in labels:
        match = _DIFFICULTY_LABEL.match(label.get("name", ""))
        if match:
            return int(match.group(1))
    return _DEFAULT_DIFFICULTY


class GitHubTaskSyncer:
    def __init__(
        self,
        http: httpx.AsyncClient,
        gestor_db: GestorDbClient,
        tenant: str,
        *,
        github_pat: str,
        owner: str,
        repos: list[str],
        default_user_id: str,
        interval_seconds: int,
    ) -> None:
        self._http = http
        self._gestor_db = gestor_db
        self._tenant = tenant
        self._pat = github_pat
        self._owner = owner
        self._repos = repos
        self._default_user_id = default_user_id
        self._interval = interval_seconds
        self._task: asyncio.Task | None = None
        self.last_result: str = "sin ejecutar todavía"

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task

    async def _loop(self) -> None:
        while True:
            try:
                awarded = await self.sync_once()
                self.last_result = f"ok, {awarded} issues premiadas"
            except FreyaError as exc:
                self.last_result = f"error: {exc}"
                logger.warning("fallo sincronizando XP desde GitHub: %s", exc)
            except httpx.HTTPError as exc:
                self.last_result = f"error de red: {exc}"
                logger.warning("fallo de red sincronizando XP desde GitHub: %s", exc)
            except Exception:
                self.last_result = "error inesperado"
                logger.exception("fallo inesperado sincronizando XP desde GitHub")
            await asyncio.sleep(self._interval)

    async def _closed_issues(self, repo: str) -> list[dict]:
        response = await self._http.get(
            f"https://api.github.com/repos/{self._owner}/{repo}/issues",
            params={"state": "closed", "per_page": 100},
            headers={
                "Authorization": f"Bearer {self._pat}",
                "Accept": "application/vnd.github+json",
            },
            timeout=15.0,
        )
        response.raise_for_status()
        # Los pull requests salen mezclados en /issues (son issues para la
        # API de GitHub) -- se descartan explícitamente, no son tasks.
        return [issue for issue in response.json() if "pull_request" not in issue]

    async def sync_once(self) -> int:
        awarded = 0
        for repo in self._repos:
            for issue in await self._closed_issues(repo):
                if await self._maybe_award(repo, issue):
                    awarded += 1
        return awarded

    async def _maybe_award(self, repo: str, issue: dict) -> bool:
        source_ref = f"{repo}#{issue['number']}"
        existing = await gdb_query(
            self._gestor_db,
            self._tenant,
            table="gam_xp_events",
            where={"source": _SOURCE, "source_ref": source_ref},
        )
        if existing:
            return False

        difficulty = _difficulty_from_labels(issue.get("labels", []))
        xp = difficulty * _XP_PER_DIFFICULTY
        coins = xp
        user_id = self._default_user_id

        await gdb_mutate(
            self._gestor_db,
            self._tenant,
            table="gam_xp_events",
            action="insert",
            data={
                "id": new_id("xpe"),
                "user_id": user_id,
                "source": _SOURCE,
                "source_ref": source_ref,
                "xp": xp,
                "coins": coins,
                "created_at": datetime.now(UTC).isoformat(),
            },
        )
        await award_xp(
            self._gestor_db, self._tenant, user_id=user_id, xp=xp, coins=coins
        )

        task_count = await count_completed_tasks(self._gestor_db, self._tenant, user_id)
        stats = await get_stats(self._gestor_db, self._tenant, user_id)
        unlocked = await check_and_unlock(
            self._gestor_db,
            self._tenant,
            user_id=user_id,
            task_count=task_count,
            level=stats["level"],
            current_streak=stats["current_streak"],
        )
        if unlocked:
            logger.info(
                "logros desbloqueados (GitHub)",
                extra={"user_id": user_id, "codes": [a["code"] for a in unlocked]},
            )
        return True
