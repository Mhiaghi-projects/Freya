"""app/domain/tenant_keys.py: generación de key_id/secret, sin red ni base
(pedido explícito del usuario: "que se genere api key con api secret, como
lo hacen las nubes")."""

from __future__ import annotations

from app.domain.tenant_keys import _generate_key_id, _generate_secret


def test_key_id_lleva_el_prefijo_de_freya() -> None:
    assert _generate_key_id().startswith("FRAK")


def test_key_id_evita_caracteres_ambiguos() -> None:
    # 0/1/O/I se confunden entre sí al transcribir una key a mano -- no
    # deberían aparecer nunca en la parte generada.
    key_id = _generate_key_id()
    body = key_id.removeprefix("FRAK")
    assert not any(c in body for c in "01OI")


def test_key_id_es_distinto_cada_vez() -> None:
    assert _generate_key_id() != _generate_key_id()


def test_secret_es_distinto_cada_vez_y_suficientemente_largo() -> None:
    a, b = _generate_secret(), _generate_secret()
    assert a != b
    assert len(a) >= 32
