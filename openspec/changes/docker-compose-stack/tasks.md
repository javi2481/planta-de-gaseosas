# Tasks — docker-compose-stack

## Phase 1: Infrastructure

### 1.0 Project skeleton

- [ ] **1.0.1** Create directory structure at repo root:
  ```
  mosquitto/config/
  telegraf/
  grafana/provisioning/datasources/
  grafana/provisioning/dashboards/
  grafana/provisioning/alerting/
  grafana/dashboards/
  simulator/
  ```
- [ ] **1.0.2** Create `.env.example` with exact content from design.md (MinIO, InfluxDB3, Grafana, simulator, and Telegraf reminder sections)
- [ ] **1.0.3** Create `.gitignore` at repo root with at minimum the line `.env`

### 1.1 Mosquitto

- [ ] **1.1.1** Create `mosquitto/config/mosquitto.conf` with exact content from design.md:
  - `listener 1883 0.0.0.0`
  - `allow_anonymous true`
  - `persistence true` + `persistence_location /mosquitto/data/`
  - `log_dest stdout` with all four `log_type` directives and `connection_messages true`

### 1.2 Telegraf

- [ ] **1.2.1** Create `telegraf/telegraf.conf` with exact content from design.md:
  - `[agent]` block: `interval = "1s"`, `flush_interval = "1s"`, `precision = "1s"`, remaining fields as specified
  - `[[inputs.mqtt_consumer]]`: `servers = ["tcp://mosquitto:1883"]`, `topics = ["planta/linea1/sensor/+"]`, `data_format = "value"`, `data_type = "float"`, `topic_parsing` entry that maps last segment to measurement, tags `linea=linea1` / `planta=gaseosas`
  - `[[outputs.influxdb_v2]]`: `urls = ["http://influxdb:8181"]`, **`organization = ""`** (CRITICAL — empty string), `bucket = "sensores"`, `token = ""`, `timeout = "5s"`, `content_encoding = "gzip"`

### 1.3 Verification — Infrastructure config files

- [ ] All directories listed in 1.0.1 exist
- [ ] `.env.example` covers every variable referenced in any config file
- [ ] `mosquitto.conf` contains `listener 1883 0.0.0.0` and `allow_anonymous true`
- [ ] `telegraf.conf` has `organization = ""` (not any non-empty string)

---

## Phase 2: Simulator

### 2.0 Simulator source files

- [ ] **2.0.1** Create `simulator/requirements.txt` with single line: `paho-mqtt==2.1.0`
- [ ] **2.0.2** Create `simulator/Dockerfile`:
  - `FROM python:3.11-slim`
  - `WORKDIR /app`
  - `COPY requirements.txt .`
  - `RUN pip install --no-cache-dir -r requirements.txt`
  - `COPY sensores.py .`
  - `CMD ["python", "-u", "sensores.py"]`
- [ ] **2.0.3** Create `simulator/sensores.py` with:
  - Imports: `os`, `time`, `random`, `math`, `paho.mqtt.client as mqtt`
  - Env vars: `MQTT_BROKER` (default `mosquitto`), `MQTT_PORT` (default `1883`), `MQTT_TOPIC_PREFIX` (default `planta/linea1/sensor`)
  - `SENSORS` dict with exactly 9 sensors as specified in design.md (see sensor table below)
  - `mqtt.Client(client_id="simulator", protocol=mqtt.MQTTv5)` + `connect()` + `loop_start()`
  - Counter state dict: `counters = {"conteo_botellas": 0, "conteo_rechazos": 0}`
  - Main loop with `spike_window = (t % 300) < 2`
  - Gauge logic: spike value when `spike_window`, else `baseline + random.gauss(0, noise)`
  - Counter logic: `conteo_botellas` increments by 1 each iteration; `conteo_rechazos` increments with `random.random() < cfg["rate"]` (rate = 0.02)
  - Publish each sensor to `f"{TOPIC_P}/{name}"` with `payload=f"{value:.4f}"`, `qos=0`
  - `t += 1` + `time.sleep(1.0)` at end of loop
  - `finally` block: `client.loop_stop()` + `client.disconnect()`

**Sensor constants for `SENSORS` dict** (must match design.md exactly):

| Key | baseline | noise | spike | kind |
|-----|----------|-------|-------|------|
| `temperatura_pasteurizador` | 75.0 | 1.5 | 92.0 | gauge |
| `presion_llenadora` | 3.2 | 0.1 | 4.5 | gauge |
| `nivel_jarabe` | 65.0 | 5.0 | 12.0 | gauge |
| `caudal_agua` | 120.0 | 8.0 | 30.0 | gauge |
| `vibracion_llenadora` | 2.5 | 0.5 | 12.0 | gauge |
| `temperatura_camara_co2` | 4.0 | 0.3 | 9.0 | gauge |
| `velocidad_cinta` | 250.0 | 10.0 | 80.0 | gauge |
| `conteo_botellas` | 0 | — | n/a | counter (rate=1.0) |
| `conteo_rechazos` | 0 | — | n/a | counter (rate=0.02) |

### 2.1 Verification — Simulator

- [ ] `simulator/requirements.txt` exists and specifies `paho-mqtt==2.1.0`
- [ ] `simulator/Dockerfile` builds without errors (`docker build ./simulator`)
- [ ] `simulator/sensores.py` contains exactly 9 keys in `SENSORS`
- [ ] Spike condition is `(t % 300) < 2` (not any other expression)
- [ ] Payload format is `f"{value:.4f}"` (no JSON wrapper, no extra whitespace)

---

## Phase 3: Observability (Grafana)

### 3.0 Grafana provisioning — datasource

- [ ] **3.0.1** Create `grafana/provisioning/datasources/influxdb.yaml` with exact content from design.md:
  - `apiVersion: 1`
  - datasource name `InfluxDB3`, type `influxdb`, `access: proxy`
  - `url: http://influxdb:8181`
  - `isDefault: true`
  - `jsonData.dbName: sensores`, `jsonData.httpMode: GET`, `jsonData.httpHeaderName1: "Authorization"`
  - `secureJsonData.httpHeaderValue1: "Token ${INFLUXDB3_TOKEN}"`
  - `editable: false`

### 3.1 Grafana provisioning — dashboard loader

- [ ] **3.1.1** Create `grafana/provisioning/dashboards/default.yaml` with exact content from design.md:
  - provider name `planta-default`, `orgId: 1`
  - `folder: 'Planta de Gaseosas'`, `folderUid: planta-gaseosas`
  - `type: file`, `updateIntervalSeconds: 30`, `allowUiUpdates: true`
  - `options.path: /var/lib/grafana/dashboards`

### 3.2 Grafana provisioning — alerting contact point

- [ ] **3.2.1** Create `grafana/provisioning/alerting/contactpoints.yaml` with exact content from design.md:
  - contact point name `console-default`, `orgId: 1`
  - receiver `uid: console-receiver`, type `webhook`
  - `url: http://localhost:9999/noop`, `httpMethod: POST`

### 3.3 Grafana provisioning — alert rules

- [ ] **3.3.1** Create `grafana/provisioning/alerting/rules.yaml` with exact content from design.md:
  - Group `planta-linea1`, `orgId: 1`, `folder: Planta de Gaseosas`, `interval: 30s`
  - Rule `alert-temp-pasteurizador`: InfluxQL query `SELECT mean("value") FROM "temperatura_pasteurizador" WHERE time > now() - 1m`, threshold expression `C` type `gt` params `[85]`, `for: 30s`, `severity: critical`
  - Rule `alert-vibracion-llenadora`: InfluxQL query `SELECT mean("value") FROM "vibracion_llenadora" WHERE time > now() - 1m`, threshold expression `C` type `gt` params `[8]`, `for: 30s`, `severity: warning`
  - Both rules reference `datasourceUid: InfluxDB3` for data queries and `datasourceUid: __expr__` for threshold condition

### 3.4 Grafana dashboard JSON

- [ ] **3.4.1** Create `grafana/dashboards/linea-envasado.json` — a valid Grafana 11 dashboard JSON with:
  - `title: "Linea de Envasado"`, `uid: linea-envasado`
  - **8 time-series panels** (one each for the 7 gauge sensors + `velocidad_cinta`):
    - `temperatura_pasteurizador`, `presion_llenadora`, `nivel_jarabe`, `caudal_agua`, `vibracion_llenadora`, `temperatura_camara_co2`, `velocidad_cinta`
    - Each panel query: `SELECT mean("value") FROM "<sensor_name>" WHERE $timeFilter GROUP BY time($__interval) fill(null)`
    - Each panel uses datasource `InfluxDB3`
  - **1 time-series panel** for counter rates using `non_negative_derivative`:
    - Query: `SELECT non_negative_derivative(last("value"), 1s) FROM "conteo_botellas" WHERE $timeFilter GROUP BY time($__interval) fill(null)`
  - **1 stat panel** for OEE:
    - Query referencing both `conteo_botellas` and `conteo_rechazos` to produce OEE as `(botellas - rechazos) / botellas * 100`
    - Unit: percent (0–100)
  - `refresh: "5s"` to meet < 3s latency requirement
  - `schemaVersion: 39` (Grafana 11 compatible)

### 3.5 Verification — Grafana

- [ ] All 5 provisioning files exist under `grafana/provisioning/`
- [ ] `influxdb.yaml` datasource name is exactly `InfluxDB3` (case-sensitive — rules.yaml references this uid)
- [ ] `rules.yaml` contains exactly 2 rule objects
- [ ] `linea-envasado.json` is valid JSON (`python3 -c "import json; json.load(open('grafana/dashboards/linea-envasado.json'))"`)
- [ ] Dashboard JSON contains at least 9 panel objects (8 time-series + 1 OEE stat)

---

## Phase 4: Integration

### 4.0 docker-compose.yml

- [ ] **4.0.1** Create `docker-compose.yml` at repo root with top-level declarations:
  - `name: planta-de-gaseosas`
  - `networks:` block defining `planta_net` with `driver: bridge`
  - `volumes:` block declaring `minio_data`, `influxdb_data`, `grafana_data`, `mosquitto_data`

- [ ] **4.0.2** Add `mosquitto` service:
  - `image: eclipse-mosquitto:2.0`, `container_name: planta-mosquitto`
  - `ports: ["1883:1883"]`
  - `volumes:` mount `./mosquitto/config/mosquitto.conf:/mosquitto/config/mosquitto.conf:ro` + `mosquitto_data:/mosquitto/data`
  - `networks: [planta_net]`, `restart: unless-stopped`
  - `healthcheck:` test `mosquitto_sub -h localhost -t '$$SYS/broker/uptime' -C 1 -W 3 || exit 1`, `interval: 5s`, `timeout: 5s`, `retries: 10`, `start_period: 5s`

- [ ] **4.0.3** Add `minio` service:
  - `image: minio/minio:latest`, `container_name: planta-minio`
  - `command: server /data --console-address ":9001"`
  - `environment:` `MINIO_ROOT_USER: ${MINIO_ROOT_USER}`, `MINIO_ROOT_PASSWORD: ${MINIO_ROOT_PASSWORD}`
  - `ports: ["9000:9000", "9001:9001"]`
  - `volumes: [minio_data:/data]`
  - `networks: [planta_net]`, `restart: unless-stopped`
  - `healthcheck:` test `curl -fsS http://localhost:9000/minio/health/live || exit 1`, `interval: 5s`, `timeout: 5s`, `retries: 10`, `start_period: 5s`

- [ ] **4.0.4** Add `createbuckets` service:
  - `image: quay.io/minio/mc:latest`, `container_name: planta-createbuckets`
  - `depends_on: minio: condition: service_healthy`
  - `environment:` `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`, `INFLUXDB3_BUCKET: ${INFLUXDB3_BUCKET:-influxdb3}`
  - `entrypoint:` shell script that runs `mc alias set local http://minio:9000 $$MINIO_ROOT_USER $$MINIO_ROOT_PASSWORD`, then `mc mb --ignore-existing local/$$INFLUXDB3_BUCKET`, then `mc anonymous set none local/$$INFLUXDB3_BUCKET`, then `exit 0`
  - `restart: "no"` (NOT `unless-stopped`)
  - `networks: [planta_net]`
  - No `healthcheck` block (it is a one-shot job)

- [ ] **4.0.5** Add `influxdb` service:
  - `image: influxdb:3-core`, `container_name: planta-influxdb`
  - `command:` list with `influxdb3 serve --node-id=node0 --object-store=s3 --bucket=${INFLUXDB3_BUCKET:-influxdb3} --aws-endpoint=http://minio:9000 --aws-access-key-id=${MINIO_ROOT_USER} --aws-secret-access-key=${MINIO_ROOT_PASSWORD} --aws-allow-http --without-auth --http-bind=0.0.0.0:8181`
  - `environment:` `INFLUXDB3_OBJECT_STORE: s3`, `INFLUXDB3_BUCKET: ${INFLUXDB3_BUCKET:-influxdb3}`, `AWS_ENDPOINT: http://minio:9000`, `AWS_ACCESS_KEY_ID: ${MINIO_ROOT_USER}`, `AWS_SECRET_ACCESS_KEY: ${MINIO_ROOT_PASSWORD}`, `AWS_ALLOW_HTTP: "true"`, `AWS_REGION: us-east-1`
  - `ports: ["8181:8181"]`
  - `volumes: [influxdb_data:/var/lib/influxdb3]`
  - `depends_on: minio: condition: service_healthy` AND `createbuckets: condition: service_completed_successfully`
  - `networks: [planta_net]`, `restart: unless-stopped`
  - `healthcheck:` test `curl -fsS http://localhost:8181/health || exit 1`, `interval: 5s`, `timeout: 5s`, `retries: 12`, `start_period: 10s`

- [ ] **4.0.6** Add `telegraf` service:
  - `image: telegraf:1.30`, `container_name: planta-telegraf`
  - `volumes:` mount `./telegraf/telegraf.conf:/etc/telegraf/telegraf.conf:ro`
  - `depends_on: mosquitto: condition: service_healthy` AND `influxdb: condition: service_healthy`
  - `networks: [planta_net]`, `restart: unless-stopped`
  - `healthcheck:` test `pgrep telegraf || exit 1`, `interval: 10s`, `timeout: 5s`, `retries: 5`, `start_period: 10s`

- [ ] **4.0.7** Add `grafana` service:
  - `image: grafana/grafana:11.2.0`, `container_name: planta-grafana`
  - `environment:` `GF_SECURITY_ADMIN_USER: ${GF_SECURITY_ADMIN_USER}`, `GF_SECURITY_ADMIN_PASSWORD: ${GF_SECURITY_ADMIN_PASSWORD}`, `GF_USERS_ALLOW_SIGN_UP: "false"`, `INFLUXDB3_TOKEN: ${INFLUXDB3_TOKEN}`
  - `ports: ["3000:3000"]`
  - `volumes:` mount `./grafana/provisioning:/etc/grafana/provisioning:ro`, `./grafana/dashboards:/var/lib/grafana/dashboards:ro`, `grafana_data:/var/lib/grafana`
  - `depends_on: influxdb: condition: service_healthy`
  - `networks: [planta_net]`, `restart: unless-stopped`
  - `healthcheck:` test `curl -fsS http://localhost:3000/api/health || exit 1`, `interval: 5s`, `timeout: 5s`, `retries: 12`, `start_period: 10s`

- [ ] **4.0.8** Add `simulator` service:
  - `build: context: ./simulator`
  - `container_name: planta-simulator`
  - `environment:` `MQTT_BROKER: ${MQTT_BROKER:-mosquitto}`, `MQTT_PORT: ${MQTT_PORT:-1883}`, `MQTT_TOPIC_PREFIX: ${MQTT_TOPIC_PREFIX:-planta/linea1/sensor}`
  - `depends_on: mosquitto: condition: service_healthy`
  - `networks: [planta_net]`, `restart: unless-stopped`
  - `healthcheck:` test `pgrep -f sensores.py || exit 1`, `interval: 10s`, `timeout: 5s`, `retries: 5`, `start_period: 5s`

### 4.1 README

- [ ] **4.1.1** Create `README.md` in Spanish with:
  - Title and brief description of the stack
  - Prerequisite: Docker Engine + Docker Compose v2
  - Clone instructions
  - `.env` configuration step (`cp .env.example .env`)
  - Startup command: `docker-compose up -d`
  - Service URLs: Grafana `http://localhost:3000` (admin/admin), MinIO Console `http://localhost:9001`, InfluxDB `http://localhost:8181`
  - Teardown commands: `docker-compose down` (preserves data) and `docker-compose down -v` (removes volumes)
  - Warning: this stack MUST NOT be used in production without enabling authentication and TLS

---

## Verification Checklist

### Stack-level acceptance

- [ ] `docker-compose config` exits with no errors (validates YAML syntax and variable interpolation)
- [ ] `cp .env.example .env && docker-compose up -d` completes without errors from a clean state
- [ ] `docker-compose ps` shows 6 services with status `healthy` and 1 (`createbuckets`) with status `exited (0)` within 60 seconds
- [ ] `docker-compose logs telegraf` shows batch write confirmations and zero lines containing `400`, `401`, `connection refused`, or `organization`

### Per-service functional checks

- [ ] Grafana dashboard at `http://localhost:3000` shows the `linea-envasado` dashboard in the `Planta de Gaseosas` folder without any manual import (credentials: admin/admin)
- [ ] All 8 time-series panels and the OEE stat panel display data within 30 seconds of opening
- [ ] OEE value is between 0 and 100
- [ ] After waiting for the 5-minute spike window (`int(time.time()) % 300 < 2`), `Alta Temperatura Pasteurizador` alert transitions to `Firing` in Grafana (threshold 85°C, spike value 92.0)
- [ ] `Vibración Llenadora Alta` alert transitions to `Firing` during the same spike window (threshold 8 mm/s, spike value 12.0)
- [ ] MinIO Console at `http://localhost:9001` shows at least one Parquet file under bucket `influxdb3` after 60 seconds of simulator runtime
- [ ] Sensor-to-panel latency measured manually is < 3 seconds (dashboard `refresh: 5s`)

### Teardown

- [ ] `docker-compose down` stops all containers; re-running `docker-compose up -d` restores all services with data preserved
- [ ] `docker-compose down -v` removes all named volumes and returns filesystem to project-files-only state
