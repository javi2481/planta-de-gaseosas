# Spec — docker-compose-stack

## Overview

This spec covers the full Docker Compose stack for the simulated bottling line: MQTT broker, ingestion agent, time-series database, object storage, visualization, and Python sensor simulator. All seven services MUST start cleanly from a single `docker-compose up -d` command with zero manual steps, provision all configuration as code, and sustain a sensor-to-dashboard latency under 3 seconds.

## Functional Requirements

### FR-1: Stack Orchestration (Story 1.1)

The `docker-compose.yml` file MUST declare all seven services — `mosquitto`, `telegraf`, `influxdb`, `grafana`, `minio`, `createbuckets`, and `simulator` — attached to a shared bridge network named `planta-net`.

Every service except `createbuckets` MUST define a `healthcheck` block. `createbuckets` MAY exit with code 0 after completing its task; it MUST be declared with `restart: on-failure` to retry if the MinIO API is not yet ready.

All `depends_on` entries MUST use `condition: service_healthy` (or `condition: service_completed_successfully` for `createbuckets`) so that the startup order is enforced deterministically.

All secrets and configurable values (credentials, ports, bucket names, database names) MUST be read from environment variables sourced from a `.env` file. Hardcoded credentials in `docker-compose.yml` are NOT permitted.

A `.env.example` file MUST be provided that covers every variable referenced in `docker-compose.yml` and all configuration files, with safe placeholder values and explanatory comments.

#### Scenarios

**Scenario 1.1.1 — Cold start (no existing volumes)**

- Given: Docker Engine is running, no volumes from a previous run exist, and a valid `.env` file is present
- When: the operator runs `docker-compose up -d`
- Then: all services reach `healthy` (or `exited 0` for `createbuckets`) within 60 seconds; `docker-compose ps` shows 6 running services and 1 exited with code 0

**Scenario 1.1.2 — Correct startup sequence**

- Given: the stack is being started from cold
- When: Docker Compose evaluates the dependency graph
- Then: `minio` starts first; `createbuckets` starts only after `minio` is healthy; `influxdb` starts only after `createbuckets` completes successfully; `mosquitto` starts independently; `telegraf` starts only after both `mosquitto` and `influxdb` are healthy; `grafana` starts only after `influxdb` is healthy; `simulator` starts only after `mosquitto` is healthy

**Scenario 1.1.3 — Restart after stop**

- Given: `docker-compose down` (without `-v`) has been run on a previously healthy stack
- When: the operator runs `docker-compose up -d`
- Then: all services reach `healthy` again within 60 seconds; previously written data in MinIO volumes MUST be preserved

**Scenario 1.1.4 — Environment variable validation**

- Given: the `.env` file is missing a required variable (e.g., `MINIO_ROOT_PASSWORD`)
- When: the operator runs `docker-compose up -d`
- Then: Docker Compose returns a non-zero exit code or the affected service fails its healthcheck; no service starts in an undefined state

**Scenario 1.1.5 — Full teardown**

- Given: the stack is running
- When: the operator runs `docker-compose down -v`
- Then: all containers stop, all named volumes are removed, and the host filesystem returns to the pre-run state (only project source files remain)

---

### FR-2: Sensor Simulation (Story 1.2)

The `simulator` service MUST be a Python 3.11 container that publishes exactly 9 sensor readings every second via MQTT to the broker at `tcp://mosquitto:1883`. Each sensor MUST publish to the topic pattern `planta/linea1/sensor/<nombre>` where `<nombre>` matches the sensor name in the table below. Each MQTT message payload MUST be a single ASCII-encoded floating-point number (no JSON wrapper).

The simulator MUST introduce periodic spikes to simulate process anomalies. A spike MUST be triggered when `int(time.time()) % 300 < 2` (approximately every 5 minutes, lasting ~2 seconds). During a spike, `temperatura_pasteurizador` MUST publish its spike value and `vibracion_llenadora` MUST publish its spike value.

All 9 sensors MUST be published within a single 1-second loop iteration. The simulator MUST use `paho-mqtt` with `loop_start()` for non-blocking MQTT I/O. No `asyncio` or additional threading is required.

#### Sensors

| Sensor Name | Unit | Baseline | Noise (±) | Spike Value |
|---|---|---|---|---|
| `caudal_jarabe` | L/min | 45.0 | 2.0 | — |
| `presion_carbonatacion` | bar | 3.8 | 0.1 | — |
| `velocidad_cinta` | bot/min | 120.0 | 5.0 | — |
| `temperatura_pasteurizador` | °C | 78.0 | 0.5 | 92.0 |
| `conteo_botellas` | acum. | increments +2/s | — | — |
| `nivel_tapas` | % | 75.0 | 1.0 | — |
| `vibracion_llenadora` | mm/s | 3.5 | 0.3 | 12.0 |
| `temperatura_camara_fria` | °C | 4.0 | 0.2 | — |
| `conteo_rechazos` | acum. | increments +0 to +1/s | — | — |

`conteo_botellas` and `conteo_rechazos` are monotonically increasing counters. `conteo_botellas` MUST increment by approximately 2 per second. `conteo_rechazos` MUST increment randomly (0 or 1 per second) to simulate occasional rejects.

#### Scenarios

**Scenario 1.2.1 — Sensor publication rate**

- Given: the simulator is running and connected to `mosquitto`
- When: 10 seconds elapse
- Then: Mosquitto broker logs show at least 90 messages received (9 sensors × 10 seconds); no sensor is missing from the published topics

**Scenario 1.2.2 — Correct topic format**

- Given: the simulator is running
- When: a subscriber connects to `mosquitto` with topic filter `planta/linea1/sensor/+`
- Then: exactly 9 distinct topic suffixes appear: `caudal_jarabe`, `presion_carbonatacion`, `velocidad_cinta`, `temperatura_pasteurizador`, `conteo_botellas`, `nivel_tapas`, `vibracion_llenadora`, `temperatura_camara_fria`, `conteo_rechazos`

**Scenario 1.2.3 — Spike injection**

- Given: the simulator has been running for at least 5 minutes
- When: `int(time.time()) % 300 < 2` becomes true
- Then: `temperatura_pasteurizador` publishes a value of 92.0 and `vibracion_llenadora` publishes a value of 12.0 during that 2-second window

**Scenario 1.2.4 — Graceful broker reconnect**

- Given: the simulator is running
- When: `mosquitto` is restarted
- Then: the simulator reconnects automatically within 5 seconds and resumes publishing without operator intervention

**Scenario 1.2.5 — Payload format**

- Given: any MQTT message from the simulator
- When: the payload is decoded as UTF-8
- Then: the result is a valid decimal number parseable by Python `float()` with no surrounding whitespace or JSON delimiters

---

### FR-3: Observability (Story 1.3)

Grafana MUST be provisioned entirely as code. No manual UI configuration steps are permitted. The following MUST be provisioned via files mounted into the Grafana container:

- A datasource definition pointing to `http://influxdb:8181` using InfluxQL
- A dashboard loader pointing to the `/var/lib/grafana/dashboards` directory
- The dashboard JSON file `linea-envasado.json`
- Alert contact point(s) in `alerting/contactpoints.yaml`
- Alert rules in `alerting/rules.yaml`

The dashboard MUST contain at minimum:

- 8 time-series panels, one per continuous sensor (all except `conteo_botellas` and `conteo_rechazos`)
- 1 OEE panel calculated as `(conteo_botellas - conteo_rechazos) / conteo_botellas * 100`
- 2 alert rules (see thresholds below)

The Grafana datasource MUST use `database: sensores` and `jsonData.httpMode: GET`. When `--without-auth` is active, no `Authorization` header is required. The provisioning structure MUST support adding the header later without changing `docker-compose.yml`.

#### Alert Thresholds

| Alert Name | Condition | Severity |
|---|---|---|
| `Alta Temperatura Pasteurizador` | `temperatura_pasteurizador` last value > 85 °C | critical |
| `Vibración Llenadora Alta` | `vibracion_llenadora` last value > 8 mm/s | critical |

#### Scenarios

**Scenario 1.3.1 — Dashboard loads on first boot**

- Given: the stack has just started and all services are healthy
- When: an operator opens `http://localhost:3000` in a browser (default credentials `admin/admin`)
- Then: the `linea-envasado` dashboard is present and visible without any login-beyond-default or manual import steps

**Scenario 1.3.2 — Live data visible**

- Given: the simulator has been running for at least 30 seconds
- When: the operator views the `linea-envasado` dashboard with a 5-minute time range
- Then: all 8 time-series panels show at least one data point; the OEE panel shows a numeric value between 0 and 100

**Scenario 1.3.3 — Alert fires on temperature spike**

- Given: the stack is running and Grafana alerting is active
- When: `temperatura_pasteurizador` publishes a value > 85 °C (spike value 92.0)
- Then: the `Alta Temperatura Pasteurizador` alert transitions to `Firing` state within 30 seconds of the first out-of-range reading

**Scenario 1.3.4 — Alert fires on vibration spike**

- Given: the stack is running and Grafana alerting is active
- When: `vibracion_llenadora` publishes a value > 8 mm/s (spike value 12.0)
- Then: the `Vibración Llenadora Alta` alert transitions to `Firing` state within 30 seconds of the first out-of-range reading

**Scenario 1.3.5 — Sensor-to-panel latency**

- Given: the simulator publishes a new reading at time T
- When: the operator observes the corresponding panel in Grafana
- Then: the new reading is visible in the panel no later than T + 3 seconds

**Scenario 1.3.6 — OEE panel correctness**

- Given: over a 1-minute window, `conteo_botellas` incremented by 120 and `conteo_rechazos` incremented by 6
- When: the OEE panel query executes
- Then: the displayed OEE value is approximately 95% ((120 - 6) / 120 × 100)

---

### FR-4: Object Storage (Story 1.4)

InfluxDB 3 Core MUST be configured to use MinIO as its object storage backend via the S3-compatible API. InfluxDB MUST write all data as Parquet files to the MinIO bucket named `influxdb3`.

InfluxDB 3 Core MUST be configured with the following environment variables:

- `INFLUXDB3_OBJECT_STORE=s3`
- `AWS_ENDPOINT=http://minio:9000`
- `AWS_ALLOW_HTTP=true`
- `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` (from `.env`)
- `INFLUXDB3_BUCKET` (or equivalent S3 bucket parameter) pointing to `influxdb3`
- `INFLUXDB3_HTTP_BIND_ADDR=0.0.0.0:8181`

The `createbuckets` service MUST use the `quay.io/minio/mc` image to create the `influxdb3` bucket before InfluxDB starts. It MUST exit with code 0 on success.

InfluxDB 3 Core MUST be started with the `--without-auth` flag for the development environment. The database name used by all services MUST be `sensores`.

Telegraf MUST use the `influxdb_v2` output plugin pointing to `http://influxdb:8181`. The `organization` field MUST be set to an empty string (`""`). The `bucket` field MUST be `sensores`. The `token` field MUST be read from the environment (MAY be any non-empty string when `--without-auth` is active).

Telegraf MUST use the `mqtt_consumer` input plugin subscribed to `planta/linea1/sensor/+` on `mosquitto:1883`. Message `data_format` MUST be `value` and `data_type` MUST be `float`. The topic tag parsing MUST extract the sensor name from the last MQTT topic segment and map it to the InfluxDB measurement name.

#### Scenarios

**Scenario 1.4.1 — Parquet files appear in MinIO**

- Given: the full stack is running and the simulator has published for at least 60 seconds
- When: the operator opens MinIO Console at `http://localhost:9001` and navigates to bucket `influxdb3`
- Then: at least one Parquet file is visible under the bucket path hierarchy

**Scenario 1.4.2 — Telegraf writes without error**

- Given: all services are healthy
- When: the operator runs `docker-compose logs telegraf`
- Then: no error lines containing `400`, `401`, `connection refused`, or `organization` appear; metrics batch write confirmations are present

**Scenario 1.4.3 — InfluxDB healthcheck passes**

- Given: InfluxDB is running
- When: the healthcheck command `curl -f http://localhost:8181/health` executes inside the container
- Then: HTTP 200 is returned

**Scenario 1.4.4 — Data queryable via InfluxQL**

- Given: the simulator has published for at least 30 seconds
- When: Grafana executes an InfluxQL query `SELECT last("value") FROM "temperatura_pasteurizador"` against datasource `influxdb:8181` database `sensores`
- Then: a numeric result is returned with no authentication error

**Scenario 1.4.5 — MinIO bucket exists before InfluxDB starts**

- Given: the stack is starting from cold
- When: `createbuckets` completes and InfluxDB starts
- Then: InfluxDB logs show no S3 bucket-not-found errors on first write attempt

**Scenario 1.4.6 — `AWS_ALLOW_HTTP=true` prevents TLS failure**

- Given: InfluxDB is configured with `AWS_ENDPOINT=http://minio:9000`
- When: InfluxDB attempts to write Parquet data to MinIO
- Then: no TLS-related errors appear in InfluxDB logs; writes succeed over plain HTTP

---

## Non-Functional Requirements

### NFR-1: Performance

- Total stack startup time (all services healthy) MUST be < 60 seconds on a machine meeting minimum requirements
- Sensor-to-dashboard latency MUST be < 3 seconds end-to-end
- The simulator MUST publish all 9 sensors within a single 1-second loop iteration
- Healthcheck `interval` SHOULD be 5 seconds; `retries` SHOULD be 10 to accommodate slower machines

### NFR-2: Reliability

- All services except `createbuckets` MUST define a `healthcheck` block with `interval`, `timeout`, `retries`, and `start_period`
- `createbuckets` MUST use `restart: on-failure` to automatically retry if MinIO is not yet ready when it starts
- All `depends_on` conditions for services that require upstream readiness MUST use `condition: service_healthy`
- If any service fails its healthcheck, Docker Engine MUST restart it (containers MUST NOT have `restart: no`)

### NFR-3: Security

- All credentials (MinIO root user/password, InfluxDB token placeholder) MUST be read from environment variables; hardcoded values in committed files are NOT permitted
- InfluxDB 3 Core MUST run with `--without-auth` exclusively in the development environment
- The `.env.example` file MUST include a comment warning that this stack MUST NOT be used in production without enabling authentication and TLS
- TLS between services is out of scope for this stack

### NFR-4: Reproducibility

- Running `docker-compose up -d` from a clean clone (with `.env` populated from `.env.example`) MUST produce a fully functional stack with zero manual steps
- All Grafana configuration (datasources, dashboards, alerts) MUST be provisioned as mounted files; no manual UI interaction is required
- All Mosquitto configuration MUST be provisioned via `mosquitto.conf`; the file MUST explicitly declare `listener 1883` and `allow_anonymous true` (required in Mosquitto 2.0+)
- All InfluxDB 3 Core configuration MUST be passed via environment variables (`INFLUXDB3_*`, `AWS_*`); no `config.toml` mount is required

---

## Acceptance Criteria

1. `docker-compose up -d` completes without errors from a clean state
2. All services reach `healthy` (or `exited 0` for `createbuckets`) within 60 seconds; `docker-compose ps` confirms 6 running + 1 exited-0
3. `docker-compose logs telegraf` contains no error lines; batch write confirmations are present
4. Grafana dashboard at `http://localhost:3000` displays the `linea-envasado` dashboard with 8 time-series panels showing live data within 30 seconds of opening
5. The OEE panel is visible and displays a value between 0 and 100
6. Injecting `temperatura_pasteurizador > 85 °C` (via natural spike) triggers the `Alta Temperatura Pasteurizador` alert in Grafana within 30 seconds
7. Injecting `vibracion_llenadora > 8 mm/s` (via natural spike) triggers the `Vibración Llenadora Alta` alert in Grafana within 30 seconds
8. Sensor-to-panel latency measured end-to-end is < 3 seconds
9. MinIO Console at `http://localhost:9001` shows at least one Parquet file under bucket `influxdb3` after 60 seconds of simulator runtime
10. `.env.example` contains every variable referenced across `docker-compose.yml`, `telegraf.conf`, and all configuration files
11. `README.md` is written in Spanish and contains instructions to clone, configure `.env`, and run `docker-compose up -d`
