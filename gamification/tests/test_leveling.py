from __future__ import annotations

from app.domain.leveling import level_for_xp, xp_for_level, xp_to_next_level


def test_nivel_1_en_cero_xp() -> None:
    assert level_for_xp(0) == 1


def test_umbral_exacto_sube_de_nivel() -> None:
    assert level_for_xp(xp_for_level(3)) == 3
    assert level_for_xp(xp_for_level(3) - 1) == 2


def test_xp_to_next_level_es_consistente() -> None:
    info = xp_to_next_level(75)
    assert info["level"] == level_for_xp(75)
    assert 0 <= info["xp_into_level"] < info["xp_for_next_level"]
