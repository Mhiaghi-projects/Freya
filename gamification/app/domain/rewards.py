"""Expense Rewards (docs/ROADMAP.md Fase 10): interpretado como recompensas
que cada persona define para sí misma y "compra" con las monedas que gana
completando tasks -- no un rastreador de gastos reales (ambiguo en el
roadmap; ver docs/DECISIONS.md, entrada de gamification)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from freya_common import BadRequest, ServiceClient, gdb_mutate, gdb_query, new_id

from app.domain.stats import get_stats, spend_coins


async def create_reward(
    client: ServiceClient, tenant: str, *, user_id: str, name: str, coin_cost: int
) -> dict[str, Any]:
    if coin_cost <= 0:
        raise BadRequest("coin_cost debe ser mayor que cero")
    reward_id = new_id("rwd")
    await gdb_mutate(
        client,
        tenant,
        table="gam_rewards",
        action="insert",
        data={
            "id": reward_id,
            "user_id": user_id,
            "name": name,
            "coin_cost": coin_cost,
        },
    )
    return {"id": reward_id, "user_id": user_id, "name": name, "coin_cost": coin_cost}


async def list_rewards(
    client: ServiceClient, tenant: str, user_id: str
) -> list[dict[str, Any]]:
    return await gdb_query(
        client,
        tenant,
        table="gam_rewards",
        where={"user_id": user_id, "archived_at": {"is_null": True}},
        order_by=[{"field": "coin_cost", "direction": "asc"}],
    )


async def archive_reward(
    client: ServiceClient, tenant: str, *, reward_id: str, user_id: str
) -> None:
    await gdb_mutate(
        client,
        tenant,
        table="gam_rewards",
        action="update",
        where={"id": reward_id, "user_id": user_id},
        data={"archived_at": datetime.now(UTC).isoformat()},
    )


async def redeem_reward(
    client: ServiceClient, tenant: str, *, reward_id: str, user_id: str
) -> dict[str, Any]:
    rows = await gdb_query(
        client, tenant, table="gam_rewards", where={"id": reward_id, "user_id": user_id}
    )
    if not rows:
        raise BadRequest("recompensa desconocida o de otro usuario")
    reward = rows[0]

    stats = await get_stats(client, tenant, user_id)
    if stats["coins"] < reward["coin_cost"]:
        raise BadRequest(
            "saldo insuficiente",
            details={"coins": stats["coins"], "coin_cost": reward["coin_cost"]},
        )

    await spend_coins(client, tenant, user_id=user_id, amount=reward["coin_cost"])
    await gdb_mutate(
        client,
        tenant,
        table="gam_reward_redemptions",
        action="insert",
        data={
            "id": new_id("rdm"),
            "reward_id": reward_id,
            "user_id": user_id,
            "coin_cost": reward["coin_cost"],
        },
    )
    return {"reward": reward["name"], "coins_spent": reward["coin_cost"]}
