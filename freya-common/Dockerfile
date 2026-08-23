# syntax=docker/dockerfile:1.7
# freya-common: la librería compartida de Freya, como proyecto propio
# -- no un directorio especial dentro de cada servicio. cicd la
# construye y testea igual que a cualquier servicio, y publica un wheel
# real como artefacto (paso build_artifact, ver
# services/cicd/app/domain/runner.py) para que el resto de servicios lo
# instalen en vez de copiar el código fuente.
#
#   docker build --target dev --tag freya/freya-common:test \
#       --file freya-common/Dockerfile .

# --- build ---------------------------------------------------------------
FROM python:3.12-slim AS build

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip

COPY freya-common/pyproject.toml /build/
COPY freya-common/freya_common /build/freya_common
RUN pip install --no-cache-dir /build

# --- dev -------------------------------------------------------------
# No hay etapa "runtime": freya-common no es un servicio HTTP, no se
# despliega con `.\freya.ps1 up`. Sólo existe esta etapa, para
# lint/test/build_artifact -- mismos caminos fijos que cualquier otro
# servicio (ver services/cicd/app/domain/runner.py, _STEP_COMMANDS).
FROM build AS dev

RUN groupadd -g 10001 freya \
 && useradd -u 10001 -g freya -s /usr/sbin/nologin -M freya

RUN pip install --no-cache-dir \
        "pytest>=8.3" "pytest-asyncio>=0.24" "ruff>=0.6" "pip-audit>=2.7" \
        "build>=1.2" "hatchling>=1.25"

WORKDIR /srv
RUN chown freya:freya /srv
# /srv/app es un directorio INTERMEDIO para /srv/app/freya_common (a
# diferencia de la plantilla de servicio, donde /srv/app es el destino
# directo de un COPY --chown): Docker no propaga --chown a un padre
# creado implícitamente, así que sin este mkdir+chown explícito /srv/app
# queda de root y freya no puede crear .ruff_cache/.pytest_cache ahí.
RUN mkdir -p /srv/app && chown freya:freya /srv/app

# pyproject.toml vive DENTRO de /srv/app (no en /srv como en la plantilla
# de servicio): build_artifact hace `pip wheel .` con /srv/app como cwd,
# necesita el pyproject.toml ahí mismo.
COPY --chown=freya:freya freya-common/freya_common /srv/app/freya_common
COPY --chown=freya:freya freya-common/pyproject.toml /srv/app/pyproject.toml
COPY --chown=freya:freya freya-common/tests /srv/tests

USER freya
ENV PYTHONPATH=/srv/app

CMD ["pytest", "-v", "/srv/tests"]
