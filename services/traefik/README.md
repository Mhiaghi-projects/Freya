# traefik

Única puerta HTTPS al exterior de Freya (docs/ROADMAP.md Fase 9). Antes lo
era `frontend` directamente (publicaba su propio puerto y terminaba TLS con
uvicorn); ahora ese papel pasa aquí, y `frontend` se queda sólo con la GUI y
las API que el exterior usa, alcanzable únicamente por detrás de este proxy.

## Cómo enruta

Proveedor Docker (`docker.sock`, sólo lectura) con `exposedByDefault: false`
— nada se enruta salvo que el propio contenedor lo pida con
`traefik.enable=true` en sus labels. Hoy sólo `frontend` las lleva (ver
`frontend/docker-compose.yml`):

```yaml
labels:
  traefik.enable: "true"
  traefik.http.routers.frontend.rule: "PathPrefix(`/`)"
  traefik.http.routers.frontend.entrypoints: "websecure"
  traefik.http.routers.frontend.tls: "true"
  traefik.http.services.frontend.loadbalancer.server.port: "8000"
```

## TLS: por qué Traefik y frontend hablan HTTP plano entre sí

`frontend` dejó de servir HTTPS (Dockerfile: uvicorn ya no lleva
`--ssl-certfile`/`--ssl-keyfile`) — Traefik y frontend están en la misma red
docker aislada (`freya-mesh`), así que aplica el mismo principio que ya usa
gestor-monitoring para hablar con sus backends nativos (metrics/logs, sin
TLS de Freya): confianza implícita dentro de una red que no tiene salida
propia al exterior. El TLS real, con el que habla el navegador, lo termina
Traefik en el entrypoint `websecure` (`services/traefik/dynamic/tls.yml`,
certificado emitido por `secrets` igual que cualquier otro servicio —
`.\freya.ps1 renew-cert traefik`).

## Certificado

Autofirmado (CA interna de `secrets`) — el navegador avisa la primera vez.
Importar `infra/certs/ca/ca.crt` en el almacén de confianza del sistema lo
elimina.

## Healthcheck

`traefik healthcheck --ping` contra un entrypoint interno (`:8080`, nunca
publicado al host) — separado de `websecure` para no mezclar la superficie
de enrutado real con la sonda de salud del propio contenedor.
