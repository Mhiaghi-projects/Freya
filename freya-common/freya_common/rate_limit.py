"""Limitador de tasa en memoria por ventana deslizante.

Vale para --workers 1 (todos los servicios de Freya corren así); con más de
un worker necesitaría estado compartido. Nació en auth (freno contra fuerza
bruta en /sign-in); se movió aquí cuando frontend lo necesitó también, para
no duplicar el fichero (docs/ROADMAP.md Fase 11, "rate limiting por tenant
en frontend")."""

from __future__ import annotations

import time
from collections import defaultdict, deque

from .errors import RateLimited


class SlidingWindowLimiter:
    def __init__(self, *, max_attempts: int, window_seconds: float) -> None:
        self._max = max_attempts
        self._window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        now = time.monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] > self._window:
            hits.popleft()
        if len(hits) >= self._max:
            retry_after = round(self._window - (now - hits[0]), 1)
            raise RateLimited(
                "Demasiados intentos; espera antes de volver a intentarlo",
                details={"retry_after_seconds": max(retry_after, 0.1)},
            )
        hits.append(now)
