"""Refresh token rotativo con revocación de familia (docs/freya-api-contract.md §2.3).

El token que ve el cliente es "<id>.<secret>": id es el selector (columna
indexada, no secreto — permite localizar la fila sin fuerza bruta contra
todos los hashes), secret es lo que se verifica con Argon2id. Si un id ya
marcado revoked_at vuelve a presentarse, es la señal de que ese token fue
robado y reutilizado por dos partes: se revoca la familia entera.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

from freya_common import ServiceClient, Unauthorized, gdb_mutate, gdb_query, new_id

from app.domain.passwords import hash_secret, verify_secret


def _split(raw: str) -> tuple[str, str]:
    token_id, _, secret = raw.partition(".")
    if not token_id or not secret:
        raise Unauthorized("refresh token con formato inválido")
    return token_id, secret


async def issue_refresh_token(
    client: ServiceClient,
    tenant: str,
    *,
    user_id: str,
    ttl_days: int,
    family_id: str | None = None,
) -> str:
    token_id = new_id("rft")
    secret = secrets.token_urlsafe(32)
    family = family_id or new_id("rff")
    expires_at = (datetime.now(UTC) + timedelta(days=ttl_days)).isoformat()

    await gdb_mutate(
        client,
        tenant,
        table="refresh_tokens",
        action="insert",
        data={
            "id": token_id,
            "user_id": user_id,
            "family_id": family,
            "secret_hash": hash_secret(secret),
            "expires_at": expires_at,
        },
    )
    return f"{token_id}.{secret}"


async def rotate_refresh_token(
    client: ServiceClient, tenant: str, raw_token: str, *, ttl_days: int
) -> tuple[str, str]:
    """Verifica, revoca el usado, emite uno nuevo de la misma familia.

    Devuelve (nuevo_refresh_token, user_id).
    """
    token_id, secret = _split(raw_token)
    rows = await gdb_query(
        client,
        tenant,
        table="refresh_tokens",
        select=["user_id", "family_id", "secret_hash", "expires_at", "revoked_at"],
        where={"id": token_id},
    )
    if not rows:
        raise Unauthorized("refresh token desconocido")
    record = rows[0]

    if record["revoked_at"] is not None:
        await gdb_mutate(
            client,
            tenant,
            table="refresh_tokens",
            action="update",
            where={"family_id": record["family_id"], "revoked_at": {"is_null": True}},
            data={"revoked_at": datetime.now(UTC).isoformat()},
        )
        raise Unauthorized("refresh token reutilizado; familia revocada")

    if not verify_secret(secret, record["secret_hash"]):
        raise Unauthorized("refresh token inválido")

    if datetime.fromisoformat(record["expires_at"]) < datetime.now(UTC):
        raise Unauthorized("refresh token caducado")

    await gdb_mutate(
        client,
        tenant,
        table="refresh_tokens",
        action="update",
        where={"id": token_id},
        data={"revoked_at": datetime.now(UTC).isoformat()},
    )
    new_token = await issue_refresh_token(
        client,
        tenant,
        user_id=record["user_id"],
        ttl_days=ttl_days,
        family_id=record["family_id"],
    )
    return new_token, record["user_id"]
