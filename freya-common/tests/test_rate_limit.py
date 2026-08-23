"""SlidingWindowLimiter: puro, sin red. Se movió aquí desde auth (ver
freya_common/rate_limit.py) cuando frontend lo necesitó también."""

from __future__ import annotations

import pytest

from freya_common import RateLimited, SlidingWindowLimiter


def test_permite_hasta_el_limite() -> None:
    limiter = SlidingWindowLimiter(max_attempts=3, window_seconds=60)
    limiter.check("k")
    limiter.check("k")
    limiter.check("k")
    with pytest.raises(RateLimited):
        limiter.check("k")


def test_claves_distintas_no_se_pisan() -> None:
    limiter = SlidingWindowLimiter(max_attempts=1, window_seconds=60)
    limiter.check("a")
    limiter.check("b")  # no debería heredar el conteo de "a"
    with pytest.raises(RateLimited):
        limiter.check("a")
