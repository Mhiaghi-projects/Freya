"""user_id_of debe rechazar tokens de servicio y de cuentas admin --
gamification es de autoservicio sólo para cuentas "user" (pedido explícito
del usuario: "admin users do not go with gamification service")."""

from __future__ import annotations

import pytest
from freya_common import Forbidden

from app.deps import user_id_of


async def test_acepta_token_de_usuario_normal() -> None:
    user_id = await user_id_of({"sub": "usr_abc123", "role": "user"})
    assert user_id == "usr_abc123"


async def test_rechaza_token_de_admin() -> None:
    with pytest.raises(Forbidden):
        await user_id_of({"sub": "usr_admin1", "role": "admin"})


async def test_rechaza_token_de_servicio() -> None:
    with pytest.raises(Forbidden):
        await user_id_of({"service": "cicd", "permissions": []})
