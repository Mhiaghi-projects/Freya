# syntax=docker/dockerfile:1.7
# Plantilla de servicio Python de Freya.
# Se construye desde la raíz del monorepo para poder copiar libs/.
#   docker build -f <nombre>/Dockerfile -t freya/<nombre>:dev .

# --- build -------------------------------------------------------------
FROM python:3.12-slim AS build

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip

COPY freya-common /build/freya-common
COPY git/pyproject.toml /build/

RUN pip install --no-cache-dir /build/freya-common \
 && pip install --no-cache-dir "fastapi>=0.115" "uvicorn[standard]>=0.30"

# --- runtime -----------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MALLOC_ARENA_MAX=2

# git de verdad: éste envuelve `git http-backend`, no reimplementa el
# protocolo (docs/ARCHITECTURE.md §5). --no-install-recommends para no
# arrastrar editores, docs ni transportes que no se usan (ssh, gitk...).
RUN apt-get update \
 && apt-get install -y --no-install-recommends git \
 && rm -rf /var/lib/apt/lists/*

RUN groupadd -g 10001 freya \
 && useradd -u 10001 -g freya -s /usr/sbin/nologin -M freya

COPY --from=build /opt/venv /opt/venv

WORKDIR /srv
# WORKDIR crea el directorio como root si no existe; sin este chown, freya
# no puede crear ficheros nuevos ahí (p.ej. .ruff_cache, .pytest_cache),
# aunque el contenido copiado con --chown sí sea suyo.
RUN chown freya:freya /srv

COPY --chown=freya:freya git/app /srv/app
COPY --chown=freya:freya git/migrations /srv/migrations

# /scratch es un volumen con nombre, no la fuente de verdad (storage lo es):
# es sólo el espacio efímero donde se materializa un repo bare para operar
# con el git real. Mismo motivo que /data en storage: Docker copia dueño y
# contenido al volumen la primera vez que se monta encima.
RUN mkdir -p /scratch && chown freya:freya /scratch

USER freya
EXPOSE 8005

# uvicorn sirve TLS interno (ver CMD): el healthcheck tiene que hablar https,
# sin verificar el certificado -- es una llamada a sí mismo por loopback, no
# una conexión a un tercero.
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import ssl,urllib.request,sys; \
ctx = ssl._create_unverified_context(); \
sys.exit(0 if urllib.request.urlopen('https://127.0.0.1:8005/health', timeout=2, context=ctx).status==200 else 1)"

CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", "--port", "8005", \
     "--ssl-certfile", "/run/certs/tls.crt", \
     "--ssl-keyfile", "/run/certs/tls.key", \
     "--no-access-log", "--workers", "1"]

# --- dev ---------------------------------------------------------------
# Etapa para ejecutar los tests dentro del contenedor. No forma parte de la
# imagen de produccion. La usa: .\freya.ps1 test <servicio>
FROM runtime AS dev

USER root
RUN pip install --no-cache-dir \
        "pytest>=8.3" "pytest-asyncio>=0.24" "httpx>=0.27" "ruff>=0.6" "pip-audit>=2.7"

COPY --chown=freya:freya git/tests /srv/tests
COPY --chown=freya:freya git/pyproject.toml /srv/

USER freya

# Sin TLS ni auth: los tests no necesitan la malla levantada.
ENV FREYA_AUTH_ENABLED=false \
    PYTHONPATH=/srv

CMD ["pytest", "-q", "/srv/tests"]
