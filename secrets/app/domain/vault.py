"""CRUD de secretos con versionado y envelope encryption (sec-02, sec-03).

Cada tenant tiene una única DEK activa (generada la primera vez que hace
falta). Los valores se cifran con esa DEK; la DEK está cifrada con la master
key. La base, robada, no revela nada sin la master key — ni siquiera con
todas las filas de `secrets`/`secret_versions` en la mano.
"""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime
from typing import Any

from freya_common import (
    Conflict,
    FreyaError,
    NotFound,
    ServiceClient,
    gdb_mutate,
    gdb_query,
    new_id,
)

from app.domain.crypto import MasterKey, decrypt_value, encrypt_value, new_data_key

# El ciphertext vive en storage, no en gestor-db (docs/ARCHITECTURE.md
# §2.1): storage nunca ve el DEK ni la master key, sólo un blob opaco, así
# que sacarlo de gestor-db no reduce la protección -- sólo evita que una
# fila crezca sin límite (una clave RSA hoy, certificados más grandes
# mañana). Un bucket por instalación, aislado por tenant igual que
# cualquier otro dato de Freya (el tenant va en la llamada a storage, no
# en el nombre del bucket).
_VALUES_BUCKET = "secrets"


def _storage_key(secret_id: str, version: int) -> str:
    return f"{secret_id}/v{version}"


async def _ensure_values_bucket(storage: ServiceClient, tenant: str) -> None:
    """Idempotente y por tenant: cada tenant tiene su propio espacio en
    storage, así que el bucket 'secrets' se crea la primera vez que ESE
    tenant guarda algo, no una sola vez al arrancar el servicio."""
    try:
        await storage.put(f"/storage/buckets/{_VALUES_BUCKET}", tenant=tenant, json={})
    except FreyaError as exc:
        if exc.status_code != 409:
            raise


async def _put_ciphertext(
    storage: ServiceClient,
    tenant: str,
    *,
    secret_id: str,
    version: int,
    ciphertext: str,
) -> str:
    await _ensure_values_bucket(storage, tenant)
    key = _storage_key(secret_id, version)
    await storage.put(
        f"/storage/{_VALUES_BUCKET}/{key}",
        tenant=tenant,
        content=ciphertext.encode("utf-8"),
        headers={"Content-Type": "application/octet-stream"},
    )
    return key


async def _get_ciphertext(
    storage: ServiceClient, tenant: str, *, storage_key: str
) -> str:
    response = await storage.get(
        f"/storage/{_VALUES_BUCKET}/{storage_key}", tenant=tenant
    )
    return response.content.decode("utf-8")


async def _delete_ciphertext(
    storage: ServiceClient, tenant: str, *, storage_key: str
) -> None:
    # Limpieza de mejor esfuerzo: un blob huérfano sigue cifrado (no es una
    # fuga), así que nunca debe poder bloquear el borrado del secreto.
    with contextlib.suppress(Exception):
        await storage.delete(f"/storage/{_VALUES_BUCKET}/{storage_key}", tenant=tenant)


async def _active_data_key(
    client: ServiceClient, tenant: str, master_key: MasterKey
) -> tuple[str, bytes]:
    rows = await gdb_query(
        client,
        tenant,
        table="secret_data_keys",
        select=["id", "wrapped_dek", "dek_nonce"],
        where={"is_active": True},
        limit=1,
    )
    if rows:
        dek = master_key.unwrap(rows[0]["wrapped_dek"], rows[0]["dek_nonce"])
        return rows[0]["id"], dek

    dek = new_data_key()
    wrapped, nonce = master_key.wrap(dek)
    key_id = new_id("dek")
    await gdb_mutate(
        client,
        tenant,
        table="secret_data_keys",
        action="insert",
        data={"id": key_id, "wrapped_dek": wrapped, "dek_nonce": nonce},
    )
    return key_id, dek


async def _get_secret_row(
    client: ServiceClient, tenant: str, key: str
) -> dict[str, Any] | None:
    rows = await gdb_query(
        client,
        tenant,
        table="secrets",
        select=["id", "type", "description", "current_version", "expires_at"],
        where={"namespace": tenant, "key": key, "deleted_at": {"is_null": True}},
        limit=1,
    )
    return rows[0] if rows else None


def _summary(namespace: str, key: str, row: dict[str, Any]) -> dict[str, Any]:
    return {
        "namespace": namespace,
        "key": key,
        "type": row["type"],
        "version": row["current_version"],
        "created_at": row.get("created_at"),
        "expires_at": row.get("expires_at"),
    }


async def create_secret(
    client: ServiceClient,
    tenant: str,
    master_key: MasterKey,
    storage: ServiceClient,
    *,
    key: str,
    value: str,
    type_: str,
    description: str,
    expires_at: str | None,
    overwrite: bool,
) -> dict[str, Any]:
    existing = await _get_secret_row(client, tenant, key)
    if existing and not overwrite:
        raise Conflict(
            f"El secreto '{key}' ya existe en '{tenant}'",
            details={"namespace": tenant, "key": key},
        )

    data_key_id, dek = await _active_data_key(client, tenant, master_key)
    ciphertext, nonce = encrypt_value(dek, value)

    if existing:
        secret_id = existing["id"]
        version = existing["current_version"] + 1
        await gdb_mutate(
            client,
            tenant,
            table="secrets",
            action="update",
            where={"id": secret_id},
            data={
                "type": type_,
                "description": description,
                "current_version": version,
                "expires_at": expires_at,
                "updated_at": _now(),
            },
        )
    else:
        secret_id = new_id("sec")
        version = 1
        await gdb_mutate(
            client,
            tenant,
            table="secrets",
            action="insert",
            data={
                "id": secret_id,
                "namespace": tenant,
                "key": key,
                "type": type_,
                "description": description,
                "current_version": version,
                "expires_at": expires_at,
            },
        )

    storage_key = await _put_ciphertext(
        storage, tenant, secret_id=secret_id, version=version, ciphertext=ciphertext
    )
    await gdb_mutate(
        client,
        tenant,
        table="secret_versions",
        action="insert",
        data={
            "id": new_id("scv"),
            "secret_id": secret_id,
            "version": version,
            "data_key_id": data_key_id,
            "value_storage_key": storage_key,
            "value_nonce": nonce,
        },
    )
    return {
        "namespace": tenant,
        "key": key,
        "type": type_,
        "version": version,
        "created_at": _now(),
        "expires_at": expires_at,
    }


async def get_secret(
    client: ServiceClient,
    tenant: str,
    master_key: MasterKey,
    storage: ServiceClient,
    *,
    key: str,
    version: int | None,
    metadata_only: bool,
) -> dict[str, Any]:
    row = await _get_secret_row(client, tenant, key)
    if row is None:
        raise NotFound(f"El secreto '{key}' no existe en '{tenant}'")

    target_version = version or row["current_version"]
    version_rows = await gdb_query(
        client,
        tenant,
        table="secret_versions",
        select=["value_storage_key", "value_nonce", "data_key_id", "created_at"],
        where={"secret_id": row["id"], "version": target_version},
        limit=1,
    )
    if not version_rows:
        raise NotFound(
            f"La versión {target_version} de '{key}' no existe",
            details={"namespace": tenant, "key": key, "version": target_version},
        )
    version_row = version_rows[0]

    result: dict[str, Any] = {
        "namespace": tenant,
        "key": key,
        "type": row["type"],
        "version": target_version,
        "created_at": version_row["created_at"],
        "expires_at": row["expires_at"],
    }
    if not metadata_only:
        data_key_rows = await gdb_query(
            client,
            tenant,
            table="secret_data_keys",
            select=["wrapped_dek", "dek_nonce"],
            where={"id": version_row["data_key_id"]},
            limit=1,
        )
        dek = master_key.unwrap(
            data_key_rows[0]["wrapped_dek"], data_key_rows[0]["dek_nonce"]
        )
        ciphertext = await _get_ciphertext(
            storage, tenant, storage_key=version_row["value_storage_key"]
        )
        result["value"] = decrypt_value(dek, ciphertext, version_row["value_nonce"])
    return result


async def list_secrets(client: ServiceClient, tenant: str) -> list[dict[str, Any]]:
    rows = await gdb_query(
        client,
        tenant,
        table="secrets",
        select=["key", "type", "current_version", "created_at", "expires_at"],
        where={"namespace": tenant, "deleted_at": {"is_null": True}},
        limit=200,
    )
    return [
        {
            "key": row["key"],
            "type": row["type"],
            "version": row["current_version"],
            "created_at": row["created_at"],
            "expires_at": row["expires_at"],
        }
        for row in rows
    ]


async def rotate_secret(
    client: ServiceClient,
    tenant: str,
    master_key: MasterKey,
    storage: ServiceClient,
    *,
    key: str,
    new_value: str,
) -> dict[str, Any]:
    row = await _get_secret_row(client, tenant, key)
    if row is None:
        raise NotFound(f"El secreto '{key}' no existe en '{tenant}'")

    data_key_id, dek = await _active_data_key(client, tenant, master_key)
    ciphertext, nonce = encrypt_value(dek, new_value)
    previous_version = row["current_version"]
    new_version = previous_version + 1

    storage_key = await _put_ciphertext(
        storage, tenant, secret_id=row["id"], version=new_version, ciphertext=ciphertext
    )
    await gdb_mutate(
        client,
        tenant,
        table="secret_versions",
        action="insert",
        data={
            "id": new_id("scv"),
            "secret_id": row["id"],
            "version": new_version,
            "data_key_id": data_key_id,
            "value_storage_key": storage_key,
            "value_nonce": nonce,
        },
    )
    await gdb_mutate(
        client,
        tenant,
        table="secrets",
        action="update",
        where={"id": row["id"]},
        data={"current_version": new_version, "updated_at": _now()},
    )
    return {
        "namespace": tenant,
        "key": key,
        "version": new_version,
        "previous_version": previous_version,
        "rotated_at": _now(),
    }


async def delete_secret(
    client: ServiceClient,
    tenant: str,
    storage: ServiceClient,
    *,
    key: str,
    version: int | None,
) -> None:
    row = await _get_secret_row(client, tenant, key)
    if row is None:
        raise NotFound(f"El secreto '{key}' no existe en '{tenant}'")

    if version is None:
        versions = await gdb_query(
            client,
            tenant,
            table="secret_versions",
            select=["value_storage_key"],
            where={"secret_id": row["id"]},
            limit=200,
        )
        for v in versions:
            await _delete_ciphertext(
                storage, tenant, storage_key=v["value_storage_key"]
            )
        await gdb_mutate(
            client,
            tenant,
            table="secrets",
            action="update",
            where={"id": row["id"]},
            data={"deleted_at": _now()},
        )
    else:
        version_rows = await gdb_query(
            client,
            tenant,
            table="secret_versions",
            select=["value_storage_key"],
            where={"secret_id": row["id"], "version": version},
            limit=1,
        )
        if version_rows:
            await _delete_ciphertext(
                storage, tenant, storage_key=version_rows[0]["value_storage_key"]
            )
        await gdb_mutate(
            client,
            tenant,
            table="secret_versions",
            action="delete",
            where={"secret_id": row["id"], "version": version},
        )


async def list_versions(
    client: ServiceClient, tenant: str, *, key: str
) -> list[dict[str, Any]]:
    row = await _get_secret_row(client, tenant, key)
    if row is None:
        raise NotFound(f"El secreto '{key}' no existe en '{tenant}'")
    rows = await gdb_query(
        client,
        tenant,
        table="secret_versions",
        select=["version", "created_at"],
        where={"secret_id": row["id"]},
        order_by=[{"field": "version", "direction": "desc"}],
        limit=200,
    )
    current = row["current_version"]
    return [
        {
            "version": r["version"],
            "created_at": r["created_at"],
            "is_current": r["version"] == current,
        }
        for r in rows
    ]


async def record_audit(
    client: ServiceClient, tenant: str, *, key: str, action: str, actor_service: str
) -> None:
    await gdb_mutate(
        client,
        tenant,
        table="secrets_audit_log",
        action="insert",
        data={
            "id": new_id("aud"),
            "namespace": tenant,
            "key": key,
            "action": action,
            "actor_service": actor_service,
        },
    )


async def list_audit_logs(
    client: ServiceClient, tenant: str, *, limit: int, action_filter: str | None
) -> list[dict[str, Any]]:
    where: dict[str, Any] = {"namespace": tenant}
    if action_filter:
        where["action"] = action_filter
    rows = await gdb_query(
        client,
        tenant,
        table="secrets_audit_log",
        select=["key", "action", "actor_service", "created_at"],
        where=where,
        order_by=[{"field": "created_at", "direction": "desc"}],
        limit=limit,
    )
    return rows


def _now() -> str:
    return datetime.now(UTC).isoformat()
