# Runner de GitHub Actions, autoalojado, en un contenedor de esta misma
# maquina (docs/DECISIONS.md, "GitHub Actions para desplegar en el propio
# PC"). No usa una imagen comunitaria de terceros para el runner en si --
# solo el binario oficial de actions/runner, descargado en build.
#
# Necesita el socket de Docker (para invocar `docker compose` contra el
# demonio de Docker Desktop del host) y el propio checkout de Freya en
# /workspace (para `git pull` en el sitio, no un checkout aislado -- ver
# docs/DECISIONS.md para el porque).

FROM ubuntu:24.04

ARG RUNNER_VERSION=2.321.0
ARG TARGETARCH=x64

# libicu74: ./bin/installdependencies.sh (más abajo) trae una lista fija
# de nombres libicuNN/libssl1.x que sólo existen en Ubuntu 22.04 o
# anteriores -- en 24.04 "noble" ninguno resuelve (el nombre real es
# libicu74), así que se queda sin instalar nada. No es sólo un aviso
# cosmético: confirmado en vivo que config.sh, ANTES de arrancar el
# runner, hace su propio "ldconfig | grep libicu" y si no encuentra nada
# hace "exit 1" -- así fallaba en silencio (docker logs no mostraba más
# que ese aviso) cada vez que el contenedor se recreaba desde cero.
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates git jq sudo \
        gnupg lsb-release libicu74 \
    && rm -rf /var/lib/apt/lists/*

# CLI de Docker (no el daemon -- eso lo tiene ya Docker Desktop en el host,
# se habla con el via el socket montado). "Docker-outside-of-Docker", no
# Docker-in-Docker: mismo patron que el resto de Freya habla con el socket
# (gestor-monitoring/app/domain/docker_client.py), aqui con la CLI real
# porque hace falta ejecutar `docker compose`, no solo leer estado.
RUN install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc \
    && chmod a+r /etc/apt/keyrings/docker.asc \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
        > /etc/apt/sources.list.d/docker.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends docker-ce-cli docker-compose-plugin \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /home/runner
RUN curl -fsSL -o actions-runner.tar.gz \
        "https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/actions-runner-linux-${TARGETARCH}-${RUNNER_VERSION}.tar.gz" \
    && tar xzf actions-runner.tar.gz \
    && rm actions-runner.tar.gz \
    && ./bin/installdependencies.sh

COPY entrypoint.sh /home/runner/entrypoint.sh
RUN chmod +x /home/runner/entrypoint.sh

# El socket de Docker montado ya equivale a acceso root al host sea cual
# sea el UID del proceso -- no hay aislamiento real que ganar corriendo
# esto como usuario sin privilegios (mismo razonamiento que traefik, que
# corre como root en este mismo repo). actions/runner exige esta variable
# para arrancar como root sin fallar con un error explícito.
ENV RUNNER_ALLOW_RUNASROOT=1
ENTRYPOINT ["/home/runner/entrypoint.sh"]
