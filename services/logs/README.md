# logs

VictoriaLogs. Backend de logs de Freya.

Mismo principio que `metrics`: sólo `gestor-monitoring` la alcanza, por la
red privada `freya-mon`, con su protocolo nativo. Retención acotada a 30
días (`docker-compose.yml`).

## Arranque

```powershell
.\freya.ps1 up logs
```

## Estado

El contenedor arranca y queda listo para recibir, pero nada le envía datos
todavía: la recolección de logs desde stdout de cada contenedor (ROADMAP.md
mon-04) es un subsistema en sí mismo, pendiente en `gestor-monitoring`
(ver su README, sección Pendiente).

Sin `HEALTHCHECK` en `docker-compose.yml`: a diferencia de la imagen de
`metrics`, esta es un binario a secas -- sin `/bin/sh`, sin `wget`, sin
`ls` siquiera (comprobado en vivo) -- así que ningún `CMD-SHELL` puede
correr dentro del contenedor. `docker ps` no le mostrará estado de salud;
el proceso arranca correctamente igualmente (verificado por sus logs).
