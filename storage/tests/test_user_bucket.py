"""Aislamiento del bucket reservado 'users' (docs/ARCHITECTURE.md §2.1):
un JWT de usuario sólo puede tocar su propio prefijo, nunca el de otro
usuario ni un servicio actuando en su nombre."""

from __future__ import annotations

import pytest
from freya_common import Forbidden

from app.api.objects import _check_user_bucket_access, _resolve_user_bucket_prefix

_USER = {"sub": "usr_abc123", "permissions": ["read:storage", "write:storage"]}
_SERVICE = {"service": "storage", "permissions": ["read:storage", "write:storage"]}


def test_otro_bucket_no_tiene_restriccion() -> None:
    _check_user_bucket_access("backups", "cualquier/cosa", _SERVICE)


def test_usuario_accede_a_su_propio_espacio() -> None:
    _check_user_bucket_access("users", "usr_abc123", _USER)
    _check_user_bucket_access("users", "usr_abc123/foto.png", _USER)


def test_usuario_no_puede_acceder_a_otro_usuario() -> None:
    with pytest.raises(Forbidden):
        _check_user_bucket_access("users", "usr_otro/foto.png", _USER)


def test_servicio_no_puede_tocar_users() -> None:
    with pytest.raises(Forbidden):
        _check_user_bucket_access("users", "usr_abc123/foto.png", _SERVICE)


def test_sin_sub_no_puede_tocar_users() -> None:
    with pytest.raises(Forbidden):
        _check_user_bucket_access("users", "usr_abc123", {"permissions": []})


def test_listar_users_sin_prefix_lo_fuerza_al_propio() -> None:
    assert _resolve_user_bucket_prefix("users", None, _USER) == "usr_abc123/"


def test_listar_users_con_prefix_propio_se_respeta() -> None:
    assert (
        _resolve_user_bucket_prefix("users", "usr_abc123/fotos/", _USER)
        == "usr_abc123/fotos/"
    )


def test_listar_users_con_prefix_ajeno_lanza() -> None:
    with pytest.raises(Forbidden):
        _resolve_user_bucket_prefix("users", "usr_otro/", _USER)


def test_listar_otro_bucket_no_toca_el_prefix() -> None:
    assert _resolve_user_bucket_prefix("backups", "database/", _SERVICE) == "database/"
