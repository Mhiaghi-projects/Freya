# metrics

VictoriaMetrics single-node. Backend de series temporales de Freya.

No es un servicio HTTP de Freya: no tiene `/health` en el sentido del
contrato ni JWT. El único cliente es `gestor-monitoring`, que le habla su
protocolo HTTP nativo (import/query de Prometheus) por la red privada
`freya-mon` (`--internal`). Ningún otro contenedor tiene ruta hasta aquí —
ver `docs/ARCHITECTURE.md` §2-4. Mismo principio que `database`/`gestor-db`.

## Arranque

```powershell
.\freya.ps1 up metrics
```

## Retención

`--retentionPeriod=30d` (`docker-compose.yml`) — mismo horizonte que el
job de limpieza previsto en el contrato (§13,
`monitoring_metrics_cleanup`, "purgar métricas > 30 días"). Recursos
escasos: sin esto, el volumen crece sin límite.
