"""Humo: freya_common nunca tuvo tests propios -- cada servicio la
probaba sólo de forma indirecta, usándola. Ahora que es su propio
proyecto (freya-common/), publica un wheel real como artefacto
de cicd (ver README.md), así que necesita algo mínimo que confirme que
el paquete se puede importar entero antes de publicarlo."""

from __future__ import annotations

import freya_common


def test_simbolos_publicos_principales_existen() -> None:
    for name in (
        "create_app",
        "ServiceClient",
        "ServiceTokenProvider",
        "TokenVerifier",
        "JwksCache",
        "BaseServiceSettings",
        "MigrationRunner",
        "gdb_query",
        "gdb_mutate",
        "new_id",
        "require_permissions",
        "current_tenant",
        "FreyaError",
        "NotFound",
        "Conflict",
        "BadRequest",
        "Unauthorized",
    ):
        assert hasattr(freya_common, name), f"falta {name} en freya_common"


def test_new_id_tiene_el_formato_prefijo_ulid() -> None:
    identifier = freya_common.new_id("test")
    prefix, _, ulid = identifier.partition("_")
    assert prefix == "test"
    assert len(ulid) == 26
