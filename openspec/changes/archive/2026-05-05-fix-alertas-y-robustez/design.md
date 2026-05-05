# Design: fix-alertas-y-robustez

## Technical Approach

Tres cambios puntuales y aislados en archivos separados. No hay dependencias entre ellos. Cada cambio se hace directamente en el archivo correspondiente siguiendo los patrones existentes del proyecto.

## Architecture Decisions

| Decisión | Tradeoff | Elección |
|----------|----------|----------|
| Ventana de spike (sensores.py) | `< 45` genera más carga falsa en InfluxDB; `< 2` no activa alertas con `for: 30s` | `< 45` — prioriza funcionamiento de alertas sobre ruido de datos |
| Severidad vibración (rules.yaml) | `warning` vs `critical` | `critical` — vibración > 8 mm/s es falla mecánica inminente |
| Restart createbuckets (docker-compose.yml) | `"no"` falla si MinIO no está listo al arrancar; `on-failure` reintenta | `on-failure` — tolerancia a condiciones de carrera en startup |

## Data Flow

```
simulator (spike 45s c/5min) ──→ MQTT ──→ Telegraf ──→ InfluxDB
                                                      │
Grafana alert (for: 30s) ◄── consulta InfluxDB ◄──────┘
```

El cambio de ventana de 2s a 45s asegura que el dato spike esté presente durante al menos 30s consecutivos, cumpliendo la condición `for: 30s` de Grafana.

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `simulator/sensores.py` (L50) | Modify | Cambiar `(t % 300) < 2` por `(t % 300) < 45` |
| `grafana/provisioning/alerting/rules.yaml` (L66) | Verify | Ya tiene `severity: critical` — sin cambios necesarios |
| `docker-compose.yml` (L72) | Modify | Cambiar `restart: "no"` por `restart: on-failure` |

## Interfaces / Contracts

Sin cambios en interfaces ni contratos. Los topics MQTT, queries InfluxDB y umbrales numéricos permanecen idénticos.

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Manual | Spike dura ~45s verificando con `docker logs` | Ejecutar simulator, observar timestamps de publicación con valor spike |
| Manual | createbuckets reintenta si MinIO no responde | Detener MinIO, levantar stack, verificar reintentos en logs |
| Visual | Alerta vibración se dispara como `critical` | Dashboard Grafana / Alerting tab |

No hay tests automatizados en el proyecto actualmente; estos cambios son verificables por inspección de código y validación manual post-despliegue.

## Migration / Rollout

No migration required. Los cambios son en configuración y simulación; basta con `docker compose up -d --force-recreate` para los servicios afectados.

## Open Questions

- [ ] ¿La ventana de 45s es suficiente si InfluxDB tiene retraso de ingesta? (Telegraf poll interval es 10s por defecto — debería ser suficiente)
