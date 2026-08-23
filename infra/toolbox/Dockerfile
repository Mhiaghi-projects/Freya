# syntax=docker/dockerfile:1.7
# Toolbox de Freya.
#
# Contiene las herramientas Unix que el proyecto necesita para tareas puntuales:
# emitir certificados, generar servicios desde la plantilla y validar el backlog.
#
# Existe para que el host Windows NO tenga que instalar openssl, python ni bash.
# freya.ps1 lo invoca montando el repositorio en /workspace. Nadie lo ejecuta
# a mano.

FROM alpine:3.20

# findutils y coreutils sustituyen a las versiones de busybox, que no aceptan
# todas las opciones que usan los scripts (find -print0, sed -i con multiples
# expresiones).
RUN apk add --no-cache \
        bash \
        openssl \
        python3 \
        py3-yaml \
        findutils \
        coreutils \
        sed \
        grep \
        git \
    && rm -rf /var/cache/apk/*

WORKDIR /workspace

# Sin ENTRYPOINT fijo: freya.ps1 decide qué comando corre.
CMD ["/bin/bash"]
