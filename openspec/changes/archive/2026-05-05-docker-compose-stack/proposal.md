# Proposal — docker-compose-stack

## Intent

Implementar el stack completo de la línea de envasado simulada: broker MQTT, agente de ingesta, base de datos time-series, object storage y dashboards, todo orquestado con Docker Compose. El objetivo es cumplir las 4 user stories del PRD con un único `docker-compose up -d` y demostrar una pipeline de datos industriales end-to-end funcionando en local.

## Scope

### In Scope
- `docker-compose.yml` con Mosquitto, Telegraf, InfluxDB 3 Core, Grafana, MinIO y Python simulator
- Healthchecks en todos los servicios + startup ordering correcto
- Configuración de InfluxDB 3 Core con MinIO como backend de almacenamiento (Parquet)
- Simulador Python con 8 sensores + 1 sensor OEE (9 total)
- Configuración de Telegraf: MQTT consumer → InfluxDB v2 output
- Dashboard Grafana provisionado como código (8 paneles time-series + OEE + 2 alertas)
- `.env.example` con todas las variables requeridas
- README en español

### Out of Scope
- Protocolos industriales reales (OPC-UA, Modbus)
- Hardware real
- InfluxDB Processing Engine plugins (proyecto 2)
- Forecasting / anomaly detection (proyectos futuros)
- Autenticación de producción (se usa `--without-auth` para dev)
- TLS/HTTPS entre servicios

## Approach

### Architecture Overview

```
simulator (Python 3.11)
    │  paho-mqtt → planta/linea1/sensor/+
    ▼
mosquitto:1883  (Eclipse Mosquitto 2.0+)
    │  tcp://mosquitto:1883
    ▼
telegraf (Telegraf 1.30+)
    │  MQTT consumer → InfluxDB v2 output → http://influxdb:8181
    ▼
influxdb:8181  (InfluxDB 3 Core 3.8+)
    │  S3 API → AWS_ENDPOINT=http://minio:9000
    ▼
minio:9000/9001  (MinIO)
    │  bucket: influxdb3 → Parquet files
    │
grafana:3000  (Grafana 11+)
    └── datasource: InfluxDB3 via InfluxQL → http://influxdb:8181
```

### Key Decisions

1. **InfluxDB 3 Core usa puerto 8181, no 8086.** Todas las referencias (Telegraf, Grafana, healthchecks) apuntan a 8181. Documentado explícitamente en README.

2. **Sin autenticación para dev (`--without-auth`).** InfluxDB 3 Core no tiene mecanismo de bootstrap de tokens via env vars (a diferencia de v2). Usar `--without-auth` elimina el problema chicken-and-egg para el entorno de desarrollo local. Si se requiere auth, se puede agregar un servicio `init-influxdb` post-arranque, pero excede la complejidad objetivo del proyecto.

3. **Config de InfluxDB 3 via env vars, no config.toml.** `influxdb3 serve` acepta todos los parámetros como env vars con prefijos `INFLUXDB3_*` y `AWS_*`. Mantiene el `docker-compose.yml` limpio y la configuración centralizada en `.env`.

4. **`AWS_ALLOW_HTTP=true` es mandatorio.** InfluxDB 3 Core requiere HTTPS para endpoints S3 por defecto. Sin este flag, todas las escrituras a MinIO fallan silenciosamente con error TLS.

5. **MinIO bucket `influxdb3` debe existir antes de que InfluxDB arranque.** Se usa un servicio `createbuckets` con imagen `quay.io/minio/mc` que crea el bucket y hace exit. `depends_on: condition: service_healthy` asegura el orden correcto.

6. **`organization = ""` en Telegraf influxdb_v2 output.** InfluxDB 3 Core ignora la org pero la API v2 la requiere presente. Cualquier valor no vacío causa error 400. Este es el error #1 en migraciones v2→v3.

7. **Mosquitto 2.0+ requiere `allow_anonymous true` explícito.** El default cambió en 2.0. Sin la directiva `listener 1883` + `allow_anonymous true` en el config, todos los clientes reciben "not authorised".

8. **`data_format = "value"` + `data_type = "float"` en Telegraf.** Un valor float por mensaje MQTT. Topic parsing mapea el último segmento del topic al nombre de medición. Más simple que JSON y suficiente para este caso de uso.

9. **9 sensores (8 originales + `conteo_rechazos` para OEE).** El panel OEE requiere botellas buenas / botellas totales. `conteo_rechazos` es un contador acumulado de rechazos, permite calcular OEE real en Grafana sin hardcodear eficiencia.

10. **Simulador: loop single-threaded con `loop_start()`.** 9 sensores × 1 msg/seg = 9 msgs/seg. Throughput trivial. `loop_start()` maneja el I/O MQTT en background thread. Sin threading ni asyncio — cero complejidad extra para el mismo resultado.

11. **Grafana: datasource InfluxQL via custom HTTP header.** InfluxDB 3 Core soporta InfluxQL. El token (cuando aplique) se pasa como header `Authorization: Token <token>` en `secureJsonData`. Sin auth en dev, el header no es necesario pero la estructura de provisioning es la misma.

12. **Alertas Grafana 11+ via YAML en `alerting/` directory.** Las alertas embedded en JSON de dashboard están deprecadas desde Grafana 8. Grafana 11 requiere archivos YAML separados con estructura folder/group/rule. Más complejo, pero es el único método reproducible como código.

13. **`depends_on` con `condition: service_healthy` en todos los servicios.** `depends_on` con solo nombre de servicio espera el start del contenedor, no que esté listo. Con healthchecks + `condition: service_healthy` se garantiza el orden correcto en < 60 segundos.

### Startup Sequence

```
t=0s   minio        (healthcheck: mc ready)
t=5s   createbuckets (crea bucket influxdb3, exit 0)
t=10s  mosquitto     (healthcheck: mosquitto_sub test)
t=15s  influxdb      (healthcheck: curl /health, depends_on: minio healthy + createbuckets complete)
t=25s  telegraf      (depends_on: mosquitto healthy + influxdb healthy)
t=30s  grafana       (healthcheck: curl /api/health)
t=30s  simulator     (depends_on: mosquitto healthy)
── Total estimado: ~35-45 segundos ──
```

### File Structure

```
planta-de-gaseosas/
├── docker-compose.yml
├── .env.example
├── mosquitto/
│   └── config/
│       └── mosquitto.conf
├── telegraf/
│   └── telegraf.conf
├── grafana/
│   ├── provisioning/
│   │   ├── datasources/
│   │   │   └── influxdb.yaml
│   │   ├── dashboards/
│   │   │   └── default.yaml
│   │   └── alerting/
│   │       ├── contactpoints.yaml
│   │       └── rules.yaml
│   └── dashboards/
│       └── linea-envasado.json
├── simulator/
│   ├── sensores.py
│   ├── requirements.txt
│   └── Dockerfile
├── README.md
└── docs/
    └── prd fabrica de gaseosas.md  (existing)
```

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| MinIO bucket race condition | `createbuckets` service con `restart: on-failure` + `depends_on: minio: condition: service_healthy` |
| InfluxDB 3 port 8181 confundido con 8086 | Documentar en README, tests de humo en healthchecks |
| Telegraf `organization=""` olvidado | Incluir en `.env.example` como comentario, documentar en README |
| `AWS_ALLOW_HTTP=true` faltante | Variable en `.env.example` con valor default `true` |
| Grafana alert provisioning complejo | Alertas simples (threshold rules), estructura YAML mínima |
| Mosquitto 2.0 auth silenciosa | Config explícita en mosquitto.conf, comentario destacado |
| `conteo_botellas` tratado como gauge | Queries Grafana usan `derivative()` o `difference()`, documentado en dashboard |
| Startup > 60s en máquinas lentas | Healthcheck retries generosos (interval: 5s, retries: 10) |
| InfluxDB sin auth expone datos | Aceptable para demo local, README advierte contra uso en producción |
| Token placeholder en `.env` cuando `--without-auth` | Comentar token como opcional en `.env.example` |

## Rollback Plan

1. `docker-compose down -v` — elimina contenedores y volúmenes (borra datos MinIO e InfluxDB)
2. Borrar archivos creados: `docker-compose.yml`, `.env`, directorios `mosquitto/`, `telegraf/`, `grafana/`, `simulator/`
3. El repo vuelve al estado inicial (solo `docs/` y `README.md`)

No hay cambios de infraestructura externa ni base de datos compartida — todo es local y efímero.

## Definition of Done

- [ ] `docker-compose up -d` arranca sin errores
- [ ] Todos los servicios en estado `healthy` en < 60 segundos
- [ ] `docker-compose ps` muestra 7 servicios running (minio, createbuckets exitado, mosquitto, influxdb, telegraf, grafana, simulator)
- [ ] Logs de Telegraf muestran métricas enviadas a InfluxDB sin errores
- [ ] Dashboard Grafana en http://localhost:3000 muestra 8 paneles time-series con datos en vivo
- [ ] Panel OEE visible y calculando correctamente
- [ ] Al inyectar valor de temperatura fuera de rango, alerta se dispara en Grafana
- [ ] Al inyectar vibración alta, alerta se dispara en Grafana
- [ ] Latencia sensor → dashboard < 3 segundos
- [ ] Archivos Parquet visibles en MinIO Console (http://localhost:9001) bajo bucket `influxdb3`
- [ ] `.env.example` cubre todas las variables requeridas
- [ ] README en español con instrucciones de arranque
