# gamification

Fase 10 del roadmap: XP, niveles, monedas, rachas, logros, Habit Tracker,
Expense Rewards, metas y leaderboard. Criterio de salida: cerrar una task
en `project-manager` otorga XP y mueve el nivel sin intervención --
verificado en vivo end-to-end (completar una task real en el panel de
`frontend` desbloqueó XP, nivel y un logro en menos de 15s).

Decisiones de diseño sobre partes ambiguas del roadmap (interpretación de
"Expense Rewards", fórmula de XP, curva de nivel, catálogo de logros fijo,
metas sin reinicio automático) están en `docs/DECISIONS.md` en la raíz del
repo, no aquí -- son decisiones de producto, no de este servicio en
concreto.

## De dónde sale la XP: poll, no webhook

`app/domain/task_sync.py:TaskSyncer` pide cada 15s (`FREYA_TASK_SYNC_
INTERVAL_SECONDS`) `GET /projects/{id}/tasks?status=done` a
`project-manager`, para cada proyecto. No hay bus de eventos en la
plataforma -- mismo patrón que `HealthMonitor`/`Scraper` de
gestor-monitoring. `gam_xp_events(source, source_ref)` es la clave de
deduplicación real: una task ya premiada nunca se vuelve a premiar aunque
el poll la siga viendo en `status=done`. Sólo se premia si `completed_by`
parece un usuario (`usr_...`) -- una task cerrada por una cuenta de
servicio no tiene un "yo" al que dar XP.

## Estructura de dominio

```
app/domain/
├── leveling.py       curva de nivel (funciones puras, sin DB)
├── stats.py          XP, monedas, racha -- award_xp() es el único punto
│                      que muta gam_user_stats de forma consistente
├── achievements.py    catálogo fijo + desbloqueo (mismo patrón que
│                      ROLE_PERMISSIONS de auth)
├── task_sync.py       el poll que cierra el criterio de salida
├── habits.py          Habit Tracker
├── rewards.py         Expense Rewards (ver docs/DECISIONS.md)
└── goals.py           metas diarias/semanales/mensuales/anuales
```

## API (sin prefijo `/api/v1`, todas de autoservicio -- gamifican a quien
hizo la petición, nunca a otro usuario)

| Ruta | Qué hace |
|---|---|
| `GET /me` | Estadísticas propias + progreso hacia el siguiente nivel |
| `GET /leaderboard?limit=` | Ranking por XP total |
| `GET /achievements` | Catálogo completo + cuáles desbloqueó el usuario |
| `GET/POST /habits`, `POST /habits/{id}/log`, `DELETE /habits/{id}` | Habit Tracker |
| `GET/POST /rewards`, `POST /rewards/{id}/redeem`, `DELETE /rewards/{id}` | Expense Rewards |
| `GET/POST /goals`, `DELETE /goals/{id}` | Metas, con progreso calculado en vivo |

## Tests

```powershell
.\freya.ps1 test gamification
.\freya.ps1 lint gamification
```

`tests/test_leveling.py` cubre la curva de nivel (funciones puras). El
resto de dominio necesita gestor-db real -- no hay tests de integración
todavía, sólo la verificación en vivo end-to-end ya mencionada.
