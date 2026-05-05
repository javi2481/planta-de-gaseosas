# Design — docker-compose-stack

## Architecture

### Service Dependency Graph

```
                          ┌──────────┐
                          │  minio   │  (object storage, healthcheck)
                          └─────┬────┘
                                │ healthy
                ┌───────────────┼─────────────────┐
                ▼                                 ▼
        ┌───────────────┐                 ┌──────────────┐
        │ createbuckets │ (one-shot, mc)  │  mosquitto   │  (broker MQTT, healthcheck)
        └───────┬───────┘                 └──────┬───────┘
                │ exit 0                         │ healthy
                ▼                                │
         ┌──────────────┐                        │
         │   influxdb   │  (3-core, healthcheck) │
         └──────┬───────┘                        │
                │ healthy                        │
       ┌────────┴────────┐                       │
       ▼                 ▼                       ▼
 ┌──────────┐     ┌─────────────┐         ┌────────────┐
 │ telegraf │     │   grafana   │         │ simulator  │
 │ (mqtt→v2)│     │ (dashboards)│         │ (paho-mqtt)│
 └──────────┘     └─────────────┘         └────────────┘

Edges:
  telegraf  depends_on: mosquitto(healthy) + influxdb(healthy)
  grafana   depends_on: influxdb(healthy)
  simulator depends_on: mosquitto(healthy)
  influxdb  depends_on: minio(healthy) + createbuckets(service_completed_successfully)
```

### Network Topology

Single user-defined bridge network `planta_net`. Todos los contenedores resuelven entre sí por nombre de servicio.

| Servicio       | Puerto interno | Publicado en host | Visibilidad             |
|----------------|----------------|-------------------|-------------------------|
| mosquitto      | 1883           | 1883              | host + interna          |
| influxdb       | 8181           | 8181              | host + interna          |
| minio (API)    | 9000           | 9000              | host + interna          |
| minio (consola)| 9001           | 9001              | host                    |
| grafana        | 3000           | 3000              | host                    |
| telegraf       | —              | —                 | interna only            |
| simulator      | —              | —                 | interna only            |
| createbuckets  | —              | —                 | interna only (one-shot) |

## Service Designs

### Mosquitto

Imagen: `eclipse-mosquitto:2.0`. Mount `./mosquitto/config/mosquitto.conf:/mosquitto/config/mosquitto.conf:ro`.

**`mosquitto/config/mosquitto.conf`** (contenido exacto):

```conf
# Listener TCP plano (dev only)
listener 1883 0.0.0.0
allow_anonymous true

# Persistencia de mensajes retenidos (no crítica, pero limpia los logs)
persistence true
persistence_location /mosquitto/data/

# Logging a stdout para que docker logs funcione
log_dest stdout
log_type error
log_type warning
log_type notice
log_type information
connection_messages true
```

Healthcheck:

```yaml
healthcheck:
  test: ["CMD-SHELL", "mosquitto_sub -h localhost -t '$$SYS/broker/uptime' -C 1 -W 3 || exit 1"]
  interval: 5s
  timeout: 5s
  retries: 10
  start_period: 5s
```

### InfluxDB 3 Core

Imagen: `influxdb:3-core`. Puerto 8181. Sin auth (`--without-auth`). Object store apuntando a MinIO.

Comando:

```yaml
command:
  - influxdb3
  - serve
  - --node-id=node0
  - --object-store=s3
  - --bucket=${INFLUXDB3_BUCKET:-influxdb3}
  - --aws-endpoint=http://minio:9000
  - --aws-access-key-id=${MINIO_ROOT_USER}
  - --aws-secret-access-key=${MINIO_ROOT_PASSWORD}
  - --aws-allow-http
  - --without-auth
  - --http-bind=0.0.0.0:8181
```

Variables de entorno (alternativa equivalente, una de las dos vías es suficiente — usamos flags explícitos por claridad):

```yaml
environment:
  INFLUXDB3_OBJECT_STORE: s3
  INFLUXDB3_BUCKET: ${INFLUXDB3_BUCKET:-influxdb3}
  AWS_ENDPOINT: http://minio:9000
  AWS_ACCESS_KEY_ID: ${MINIO_ROOT_USER}
  AWS_SECRET_ACCESS_KEY: ${MINIO_ROOT_PASSWORD}
  AWS_ALLOW_HTTP: "true"
  AWS_REGION: us-east-1
```

Healthcheck:

```yaml
healthcheck:
  test: ["CMD-SHELL", "curl -fsS http://localhost:8181/health || exit 1"]
  interval: 5s
  timeout: 5s
  retries: 12
  start_period: 10s
```

`depends_on`:

```yaml
depends_on:
  minio:
    condition: service_healthy
  createbuckets:
    condition: service_completed_successfully
```

### MinIO + createbuckets

**MinIO**:

```yaml
minio:
  image: minio/minio:latest
  command: server /data --console-address ":9001"
  environment:
    MINIO_ROOT_USER: ${MINIO_ROOT_USER}
    MINIO_ROOT_PASSWORD: ${MINIO_ROOT_PASSWORD}
  ports:
    - "9000:9000"
    - "9001:9001"
  volumes:
    - minio_data:/data
  healthcheck:
    test: ["CMD-SHELL", "curl -fsS http://localhost:9000/minio/health/live || exit 1"]
    interval: 5s
    timeout: 5s
    retries: 10
    start_period: 5s
```

**createbuckets** (one-shot que crea el bucket `influxdb3` y sale):

```yaml
createbuckets:
  image: quay.io/minio/mc:latest
  depends_on:
    minio:
      condition: service_healthy
  environment:
    MINIO_ROOT_USER: ${MINIO_ROOT_USER}
    MINIO_ROOT_PASSWORD: ${MINIO_ROOT_PASSWORD}
    INFLUXDB3_BUCKET: ${INFLUXDB3_BUCKET:-influxdb3}
  entrypoint: >
    /bin/sh -c "
    set -e;
    mc alias set local http://minio:9000 $$MINIO_ROOT_USER $$MINIO_ROOT_PASSWORD;
    mc mb --ignore-existing local/$$INFLUXDB3_BUCKET;
    mc anonymous set none local/$$INFLUXDB3_BUCKET;
    echo 'bucket ready: '$$INFLUXDB3_BUCKET;
    exit 0;
    "
  restart: "no"
```

InfluxDB usa `condition: service_completed_successfully` sobre `createbuckets`, no `service_healthy` (es un job que termina).

### Telegraf

Imagen: `telegraf:1.30`. Mount `./telegraf/telegraf.conf:/etc/telegraf/telegraf.conf:ro`.

**`telegraf/telegraf.conf`** (contenido exacto):

```toml
[[inputs.mqtt_consumer]]
  servers = ["tcp://mosquitto:1883"]
  topics = [
    "planta1/+/sensor/+",
  ]
  qos = 0
  connection_timeout = "30s"
  client_id = "telegraf"

  data_format = "value"
  data_type   = "float"

  # UNS: extrae el ultimo segmento como measurement.
  # planta1/llenadora/sensor/vibracion_llenadora -> measurement = "vibracion_llenadora"
  topic_parsing = [
    { topic = "planta1/+/sensor/+", measurement = "_/_/_/measurement" },
  ]

  [inputs.mqtt_consumer.tags]
    planta = "gaseosas"

###############################################################################
# PROCESSOR — Extraer área del topic como tag para evitar colisiones
###############################################################################
[[processors.regex]]
  namepass = ["*"]
  [[processors.regex.tags]]
    key   = "topic"
    pattern = "^planta1/([^/]+)/sensor/.+$"
    result_key = "area"

###############################################################################
# OUTPUT — InfluxDB v2 API (compatible con InfluxDB 3 Core)
###############################################################################
[[outputs.influxdb_v2]]
  urls = ["http://influxdb:8181"]

  # CRITICAL: org DEBE ser "" para InfluxDB 3 Core.
  # Cualquier valor no vacio causa error 400 Bad Request.
  organization = ""

  bucket = "sensores"

  # Token vacio cuando InfluxDB corre con --without-auth.
  # Si se habilita auth, setear desde env: token = "$$INFLUXDB3_TOKEN"
  token = ""

  timeout = "5s"
  content_encoding = "gzip"
```

Healthcheck (Telegraf no expone HTTP por defecto, usamos process check):

```yaml
healthcheck:
  test: ["CMD-SHELL", "pgrep telegraf || exit 1"]
  interval: 10s
  timeout: 5s
  retries: 5
  start_period: 10s
```

### Python Simulator

Single-threaded, paho-mqtt con `loop_start()`. 11 sensores con UNS (Unified Naming System), 1 mensaje/seg por sensor. Spike sintético cada 300s para validar alertas.

**UNS — Unified Naming System**: cada sensor se asigna a un área de la planta. Topic resultante: `planta1/<area>/sensor/<nombre>`.

**Tabla de sensores** (constante en `sensores.py`):

| Sensor                     | Área              | Unidad     | Baseline | Ruido (±) | Spike value | Tipo    |
|----------------------------|-------------------|------------|----------|-----------|-------------|---------|
| temperatura_pasteurizador  | pasteurizador     | °C         | 75.0     | 1.5       | 92.0        | gauge   |
| presion_llenadora          | llenadora         | bar        | 3.2      | 0.1       | 4.5         | gauge   |
| vibracion_llenadora        | llenadora         | mm/s       | 2.5      | 0.5       | 12.0        | gauge   |
| nivel_jarabe               | mezcla            | %          | 65.0     | 5.0       | 12.0        | gauge   |
| caudal_agua                | mezcla            | L/min      | 120.0    | 8.0       | 30.0        | gauge   |
| temperatura_camara_co2     | almacenamiento    | °C         | 4.0      | 0.3       | 9.0         | gauge   |
| temperatura_camara_fria    | almacenamiento    | °C         | 4.0      | 0.2       | —           | gauge   |
| velocidad_cinta            | transporte        | botellas/m | 250.0    | 10.0      | 80.0        | gauge   |
| conteo_botellas            | transporte        | unidades   | counter  | +1/seg    | n/a         | counter |
| conteo_rechazos            | transporte        | unidades   | counter  | +rate     | n/a         | counter |
| nivel_tapas                | insumos           | %          | 75.0     | 1.0       | n/a         | gauge   |

Para counters: `conteo_botellas` incrementa ~1 por segundo. `conteo_rechazos` incrementa con probabilidad p=0.02 por segundo. OEE en Grafana se calcula como `(conteo_botellas - conteo_rechazos) / conteo_botellas`.

**Estructura de `SENSORS` (Python)**:

```python
ROOT = os.environ.get("MQTT_TOPIC_PREFIX", "planta1")

AREA_MAP = {
    "temperatura_pasteurizador": "pasteurizador",
    "presion_llenadora":         "llenadora",
    "vibracion_llenadora":       "llenadora",
    "nivel_jarabe":              "mezcla",
    "caudal_agua":               "mezcla",
    "temperatura_camara_co2":    "almacenamiento",
    "temperatura_camara_fria":   "almacenamiento",
    "velocidad_cinta":           "transporte",
    "conteo_botellas":           "transporte",
    "conteo_rechazos":           "transporte",
    "nivel_tapas":               "insumos",
}

# En el loop de publish:
area = AREA_MAP.get(name, "general")
client.publish(f"{ROOT}/{area}/sensor/{name}", payload=f"{value:.4f}", qos=0)
```

**Loop pattern** (pseudo-código exacto):

```python
import os, time, random, math
import paho.mqtt.client as mqtt

BROKER  = os.environ.get("MQTT_BROKER", "mosquitto")
PORT    = int(os.environ.get("MQTT_PORT", "1883"))
ROOT    = os.environ.get("MQTT_TOPIC_PREFIX", "planta1")

client = mqtt.Client(client_id="simulator", protocol=mqtt.MQTTv5)
client.connect(BROKER, PORT, keepalive=30)
client.loop_start()  # I/O en background thread

# Estado para counters
counters = {"conteo_botellas": 0, "conteo_rechazos": 0}
t = 0
try:
    while True:
        spike_window = (t % 300) < 2  # 2 segundos de spike cada 5 minutos

        for name, cfg in SENSORS.items():
            if cfg["kind"] == "gauge":
                if spike_window and "spike" in cfg:
                    value = cfg["spike"]
                else:
                    value = cfg["baseline"] + random.gauss(0, cfg["noise"])
            else:  # counter
                if name == "conteo_botellas":
                    counters[name] += 1
                else:  # conteo_rechazos
                    if random.random() < cfg["rate"]:
                        counters[name] += 1
                value = counters[name]

            area = AREA_MAP.get(name, "general")
            client.publish(f"{ROOT}/{area}/sensor/{name}", payload=f"{value:.4f}", qos=0)

        t += 1
        time.sleep(1.0)
finally:
    client.loop_stop()
    client.disconnect()
```

**`simulator/Dockerfile`**:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY sensores.py .
CMD ["python", "-u", "sensores.py"]
```

**`simulator/requirements.txt`**:

```
paho-mqtt==2.1.0
```

Healthcheck (proceso):

```yaml
healthcheck:
  test: ["CMD-SHELL", "pgrep -f sensores.py || exit 1"]
  interval: 10s
  timeout: 5s
  retries: 5
  start_period: 5s
```

### Grafana

Imagen: `grafana/grafana:11.2.0`. Provisioning como código. InfluxQL como query language (compatible con InfluxDB 3 Core via API v1/v2).

**Estructura de provisioning**:

```
grafana/
├── provisioning/
│   ├── datasources/
│   │   └── influxdb.yaml
│   ├── dashboards/
│   │   └── default.yaml
│   └── alerting/
│       ├── contactpoints.yaml
│       └── rules.yaml
└── dashboards/
    └── linea-envasado.json
```

**`grafana/provisioning/datasources/influxdb.yaml`**:

```yaml
apiVersion: 1

datasources:
  - name: InfluxDB3
    type: influxdb
    access: proxy
    url: http://influxdb:8181
    isDefault: true
    jsonData:
      dbName: sensores
      httpMode: GET
      httpHeaderName1: "Authorization"
    secureJsonData:
      httpHeaderValue1: "Token ${INFLUXDB3_TOKEN}"
    editable: false
```

Nota: con `--without-auth`, `INFLUXDB3_TOKEN` puede ser cualquier string no vacío (ej. `dev-no-auth`); el header se ignora. Mantenemos la estructura para que migrar a auth real sea solo cambiar la variable.

**`grafana/provisioning/dashboards/default.yaml`**:

```yaml
apiVersion: 1

providers:
  - name: 'planta-default'
    orgId: 1
    folder: 'Planta de Gaseosas'
    folderUid: planta-gaseosas
    type: file
    disableDeletion: false
    updateIntervalSeconds: 30
    allowUiUpdates: true
    options:
      path: /var/lib/grafana/dashboards
      foldersFromFilesStructure: false
```

Mounts:

```yaml
volumes:
  - ./grafana/provisioning:/etc/grafana/provisioning:ro
  - ./grafana/dashboards:/var/lib/grafana/dashboards:ro
  - grafana_data:/var/lib/grafana
```

**`grafana/provisioning/alerting/contactpoints.yaml`**:

```yaml
apiVersion: 1

contactPoints:
  - orgId: 1
    name: console-default
    receivers:
      - uid: console-receiver
        type: webhook
        settings:
          url: http://localhost:9999/noop
          httpMethod: POST
        disableResolveMessage: false
```

Para dev usamos un webhook que apunta a un endpoint inexistente: las alertas igual se disparan en la UI de Grafana (estado Alerting visible en el dashboard) sin necesidad de Slack/email.

**`grafana/provisioning/alerting/rules.yaml`** (estructura mínima, 2 reglas):

```yaml
apiVersion: 1

groups:
  - orgId: 1
    name: planta-linea1
    folder: Planta de Gaseosas
    interval: 30s
    rules:
      - uid: alert-temp-pasteurizador
        title: Temperatura pasteurizador alta
        condition: C
        data:
          - refId: A
            relativeTimeRange:
              from: 60
              to: 0
            datasourceUid: InfluxDB3
            model:
              refId: A
              rawQuery: true
              query: 'SELECT mean("value") FROM "temperatura_pasteurizador" WHERE time > now() - 1m'
              resultFormat: time_series
          - refId: C
            datasourceUid: __expr__
            model:
              refId: C
              type: threshold
              expression: A
              conditions:
                - evaluator: { type: gt, params: [85] }
        noDataState: NoData
        execErrState: Error
        for: 30s
        labels:
          severity: critical
          sensor: temperatura_pasteurizador
        annotations:
          summary: "Temperatura pasteurizador > 85 C"

      - uid: alert-vibracion-llenadora
        title: Vibracion llenadora alta
        condition: C
        data:
          - refId: A
            relativeTimeRange:
              from: 60
              to: 0
            datasourceUid: InfluxDB3
            model:
              refId: A
              rawQuery: true
              query: 'SELECT mean("value") FROM "vibracion_llenadora" WHERE time > now() - 1m'
              resultFormat: time_series
          - refId: C
            datasourceUid: __expr__
            model:
              refId: C
              type: threshold
              expression: A
              conditions:
                - evaluator: { type: gt, params: [8] }
        noDataState: NoData
        execErrState: Error
        for: 30s
        labels:
          severity: warning
          sensor: vibracion_llenadora
        annotations:
          summary: "Vibracion llenadora > 8 mm/s"
```

**Dashboard** (`grafana/dashboards/linea-envasado.json`): 8 paneles time-series (1 por sensor gauge) + 1 panel stat para OEE. Queries de ejemplo:

- Time-series gauge: `SELECT mean("value") FROM "temperatura_pasteurizador" WHERE $timeFilter GROUP BY time($__interval) fill(null)`
- Counter como tasa: `SELECT non_negative_derivative(last("value"), 1s) FROM "conteo_botellas" WHERE $timeFilter GROUP BY time($__interval) fill(null)`
- OEE (stat panel):
  ```sql
  SELECT (last("botellas") - last("rechazos")) / last("botellas") AS oee
  FROM (
    SELECT last("value") AS botellas FROM "conteo_botellas" WHERE $timeFilter
  ), (
    SELECT last("value") AS rechazos FROM "conteo_rechazos" WHERE $timeFilter
  )
  ```

Healthcheck:

```yaml
healthcheck:
  test: ["CMD-SHELL", "curl -fsS http://localhost:3000/api/health || exit 1"]
  interval: 5s
  timeout: 5s
  retries: 12
  start_period: 10s
```

## Docker Compose Structure

**Top-level**:

```yaml
name: planta-de-gaseosas

networks:
  planta_net:
    driver: bridge

volumes:
  minio_data:
  influxdb_data:
  grafana_data:
  mosquitto_data:
```

Cada servicio declara `networks: [planta_net]` y `restart: unless-stopped` (excepto `createbuckets` con `restart: "no"`).

**Patrón de healthcheck (ejemplo, mosquitto)**:

```yaml
mosquitto:
  image: eclipse-mosquitto:2.0
  container_name: planta-mosquitto
  ports:
    - "1883:1883"
  volumes:
    - ./mosquitto/config/mosquitto.conf:/mosquitto/config/mosquitto.conf:ro
    - mosquitto_data:/mosquitto/data
  networks: [planta_net]
  restart: unless-stopped
  healthcheck:
    test: ["CMD-SHELL", "mosquitto_sub -h localhost -t '$$SYS/broker/uptime' -C 1 -W 3 || exit 1"]
    interval: 5s
    timeout: 5s
    retries: 10
    start_period: 5s
```

**Patrón de `depends_on` con healthcheck**:

```yaml
telegraf:
  depends_on:
    mosquitto:
      condition: service_healthy
    influxdb:
      condition: service_healthy
```

## Environment Variables

**`.env.example`** (contenido exacto):

```bash
# ============================================================================
# Planta de Gaseosas — Variables de entorno
# Copiar a .env y ajustar segun necesidad. NO commitear .env real.
# ============================================================================

# ----------------------------------------------------------------------------
# MinIO (object storage backend de InfluxDB 3)
# ----------------------------------------------------------------------------
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin123

# ----------------------------------------------------------------------------
# InfluxDB 3 Core
# ----------------------------------------------------------------------------
# Bucket S3 en MinIO donde InfluxDB almacena Parquet files
INFLUXDB3_BUCKET=influxdb3

# CRITICAL: AWS_ALLOW_HTTP=true es OBLIGATORIO.
# InfluxDB 3 Core exige HTTPS para S3 por default; sin este flag las
# escrituras a MinIO fallan silenciosamente con error TLS.
AWS_ALLOW_HTTP=true

# Token para Grafana datasource header.
# Con --without-auth (modo dev), cualquier valor no vacio funciona.
# Si habilitas auth, generar con: influxdb3 create token --admin
INFLUXDB3_TOKEN=dev-no-auth

# ----------------------------------------------------------------------------
# Grafana
# ----------------------------------------------------------------------------
GF_SECURITY_ADMIN_USER=admin
GF_SECURITY_ADMIN_PASSWORD=admin
GF_USERS_ALLOW_SIGN_UP=false

# ----------------------------------------------------------------------------
# Simulador — UNS (Unified Naming System)
# Topic format: planta1/<area>/sensor/<nombre>
# El AREA_MAP interno asigna cada sensor a su área.
# ----------------------------------------------------------------------------
MQTT_BROKER=mosquitto
MQTT_PORT=1883
MQTT_TOPIC_PREFIX=planta1

# ----------------------------------------------------------------------------
# Telegraf
# ----------------------------------------------------------------------------
# Recordatorio: en telegraf.conf el output influxdb_v2 DEBE tener
#   organization = ""
# Cualquier valor no vacio causa 400 Bad Request en InfluxDB 3 Core.
```

## Data Flow

```
1. simulator (Python)
   └─ paho-mqtt publish (UNS):
      topic   = planta1/<area>/sensor/<nombre>
      payload = "<float>"     (ej. "75.42")
      qos     = 0
      cada 1s, 11 sensores -> 11 mensajes/seg

2. mosquitto:1883
   └─ broker MQTT, retiene nada (persistence solo para SYS topics)

3. telegraf
   └─ subscribe a planta1/+/sensor/+
      data_format = "value", data_type = "float"
      topic_parsing extrae ultimo segmento -> measurement name
      processors.regex extrae area del topic -> tag "area"
      tag: planta=gaseosas
   └─ output influxdb_v2:
      POST http://influxdb:8181/api/v2/write?bucket=sensores&org=
      organization = ""  (CRITICAL para v3)
      flush_interval = 1s

4. influxdb:8181
   └─ recibe via API v2, escribe a object store S3
   └─ MinIO endpoint: http://minio:9000
      bucket: influxdb3
      formato: Parquet (segmentos por tiempo)

5. minio:9000
   └─ almacena Parquet files bajo /data/influxdb3/...
   └─ consola en http://localhost:9001 para inspeccion visual

6. grafana:3000
   └─ datasource InfluxDB3 -> http://influxdb:8181
   └─ httpMode = GET (queries InfluxQL via /query endpoint)
   └─ header Authorization: Token <INFLUXDB3_TOKEN>
   └─ dashboards leen measurements: temperatura_pasteurizador,
      presion_llenadora, ..., conteo_botellas, conteo_rechazos
   └─ alertas evaluan cada 30s, ventana 1m
```

Latencia objetivo: simulator -> grafana < 3s. Cuello principal: `flush_interval=1s` en Telegraf + `interval=30s` mínimo de refresh en panel Grafana (configurable en dashboard a 5s).

## Architecture Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Time-series DB | InfluxDB 3 Core | Object store nativo (Parquet en MinIO), API v2 compat, port 8181, sin Processing Engine para evitar complejidad |
| Auth en dev | `--without-auth` | InfluxDB 3 Core no tiene bootstrap de tokens via env; evita chicken-and-egg para `docker-compose up` limpio |
| Config InfluxDB | Flags + env vars | Sin `config.toml` separado; todo en compose y `.env` |
| MinIO bucket bootstrap | Servicio `createbuckets` (mc) | `service_completed_successfully` garantiza bucket antes de InfluxDB; race condition eliminada |
| MQTT auth | Anonymous (`allow_anonymous true`) | Stack local; Mosquitto 2.0 requiere directiva explícita o falla con "not authorised" |
| Telegraf payload format | `value` + `data_type=float` | Un float por mensaje; topic_parsing mapea topic -> measurement; sin overhead de JSON parsing |
| Telegraf `organization` | `""` (string vacío) | InfluxDB 3 Core ignora la org pero la API v2 la valida; cualquier valor no vacío => 400 |
| Telegraf -> InfluxDB | `outputs.influxdb_v2` | InfluxDB 3 Core habla API v2 nativa; `influxdb_v3` plugin no existe en Telegraf 1.30 |
| Grafana query language | InfluxQL via header auth | InfluxDB 3 Core soporta InfluxQL via `/query`; Flux deprecado en v3; SQL endpoint requeriría plugin extra |
| Simulador concurrencia | Single-thread + `loop_start()` | 11 msg/seg es trivial; threading/asyncio agregan complejidad sin beneficio medible |
| UNS topic pattern | `planta1/<area>/sensor/<nombre>` | Organiza sensores por área de planta; evita colisiones de nombre con tag `area` en Telegraf |
| OEE source | Sensor `conteo_rechazos` real | Permite calcular OEE como ratio en Grafana; sin hardcodear eficiencia |
| Spike trigger | `t % 300 < 2` | 2 segundos de valores de spike cada 5 minutos => alertas dispararan en demos |
| Healthchecks | Todos los servicios | `condition: service_healthy` garantiza orden < 60s; sin healthcheck el orden no está garantizado |
| Provisioning Grafana | YAML files (alerting + datasources + dashboards) | Reproducible, versionable, sin click-ops; Grafana 11+ requiere YAML para alertas |
| Webhook contact point | URL local inválida | Alertas se ven en UI de Grafana; sin dependencia de Slack/SMTP en dev |
| Network | Single bridge `planta_net` | DNS interno por nombre de servicio; no hay razón para segmentar en este stack |

## Known Constraints

Cosas que no son ideales pero son aceptables para este stack de desarrollo local:

- **Sin auth en InfluxDB.** `--without-auth` expone la DB en el host. Aceptable porque sólo escucha en localhost; el README advierte explícitamente.
- **Sin TLS interno.** Todo el tráfico entre contenedores es plano (HTTP, MQTT). Para producción se requeriría TLS en mosquitto, HTTPS en influxdb y Grafana, y certificados.
- **MQTT anonymous.** Cualquier cliente que llegue a `localhost:1883` puede publicar/subscribir. Aceptable en dev local.
- **Webhook contact point apunta a URL inexistente.** Las alertas se ven en la UI pero no notifican a ningún canal externo. Para producción se cambiaría a Slack/email/PagerDuty.
- **Grafana admin password en `.env` plano.** Sin gestión de secretos (Vault, Docker secrets). Aceptable para dev.
- **Datos efímeros tras `docker-compose down -v`.** Volúmenes nombrados persisten entre `up`/`down` normales pero `-v` los borra. Documentado.
- **Counter `conteo_botellas` se reinicia si el simulator reinicia.** El estado vive en memoria del proceso. Consultas Grafana usan `non_negative_derivative` para tolerar resets sin valores negativos.
- **Latencia mínima ~1s.** `flush_interval=1s` en Telegraf es el piso; bajarlo a sub-segundo requeriría tunear `metric_batch_size` y aumenta carga sin beneficio para este caso.
- **Token Grafana hardcoded en `.env`.** Funciona porque InfluxDB ignora el header con `--without-auth`. Si se habilita auth, hay que regenerar el token y reiniciar Grafana.
- **Simulator no respeta backpressure.** Si el broker se cae, paho-mqtt reconecta pero los mensajes durante el outage se pierden. Aceptable: no es un sistema de producción.
