"""IDs con prefijo tipo ULID (docs/freya-api-contract.md): "<prefijo>_<ulid>".

26 caracteres en base32 de Crockford, ordenables por tiempo de creación —
mismo criterio que UUIDv7, pero es el formato que exige el contrato
(`usr_01H8X...`, `tsk_01H8X...`) y además legible/tecleable.
"""

from __future__ import annotations

import os
import time

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def ulid() -> str:
    """48 bits de timestamp en ms + 80 bits aleatorios, en Crockford base32."""
    millis = int(time.time() * 1000)
    randomness = int.from_bytes(os.urandom(10), "big")
    value = (millis << 80) | randomness

    chars = [""] * 26
    for i in range(25, -1, -1):
        chars[i] = _CROCKFORD[value & 0x1F]
        value >>= 5
    return "".join(chars)


def new_id(prefix: str) -> str:
    """Id de recurso con prefijo, p.ej. new_id("usr") -> "usr_01H8X...."."""
    return f"{prefix}_{ulid()}"
