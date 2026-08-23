"""Curva de nivel: nivel N empieza en 50*(N-1)^2 XP total -- crecimiento
cuadrático clásico de RPG (nivel 2 a 50 XP, nivel 5 a 800, nivel 10 a 4050).
"""

from __future__ import annotations

_BASE = 50


def xp_for_level(level: int) -> int:
    return _BASE * (level - 1) ** 2


def level_for_xp(total_xp: int) -> int:
    level = 1
    while xp_for_level(level + 1) <= total_xp:
        level += 1
    return level


def xp_to_next_level(total_xp: int) -> dict[str, int]:
    level = level_for_xp(total_xp)
    floor = xp_for_level(level)
    ceiling = xp_for_level(level + 1)
    return {
        "level": level,
        "xp_into_level": total_xp - floor,
        "xp_for_next_level": ceiling - floor,
    }
