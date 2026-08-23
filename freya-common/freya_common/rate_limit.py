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
    # Cada llamada sólo poda la deque de SU clave -- una clave que deja de
    # llamarse (una IP, un tenant) se queda con una entrada vacía en
    # self._hits para siempre, sin nada que la borre nunca: fuga de memoria
    # proporcional al total de claves distintas vistas en la vida del
    # proceso (auth/frontend corren "restart: unless-stopped", nunca se
    # reinician solos). Una purga periódica de TODO el dict, cada N
    # llamadas, lo acota sin necesitar una tarea de fondo aparte.
    _SWEEP_EVERY = 500

    def __init__(self, *, max_attempts: int, window_seconds: float) -> None:
        self._max = max_attempts
        self._window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._calls_since_sweep = 0

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

        self._calls_since_sweep += 1
        if self._calls_since_sweep >= self._SWEEP_EVERY:
            self._calls_since_sweep = 0
            self._sweep(now)

    def _sweep(self, now: float) -> None:
        stale = [
            k
            for k, hits in self._hits.items()
            if not hits or now - hits[-1] > self._window
        ]
        for k in stale:
            del self._hits[k]
