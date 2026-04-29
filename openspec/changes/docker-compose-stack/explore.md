# Explore — docker-compose-stack

## Key Decisions

### 1. InfluxDB 3 Core Docker Image and Startup

- **Image**: `influxdb:3-core` (official Docker Hub tag)
- **Default port**: 8181 (NOT 8086 — this is a breaking difference from v2)
- **Startup command** (via `command:` in compose):
  ```
  influxdb3 serve
    --node-id node0
    --object-store s3
    --bucket influxdb3
    --aws-endpoint http://minio:9000
    --aws-access-key-id ${MINIO_ROOT_USER}
    --aws-secret-access-key ${MINIO_ROOT_PASSWORD}
    --aws-allow-http
  ```
- **No initial setup wizard**: InfluxDB 3 Core starts headless. The operator token must be created **after** the server is up via `POST /api/v3/configure/token/admin` or `influxdb3 create token --admin`.
- **Token bootstrap challenge**: There is a chicken-and-egg problem — you need the server running to create the token, but Telegraf needs the token to write. Solution: create the token via curl/exec in a separate init container or a `docker compose exec` step post-startup, then store it in `.env`.
- **Alternative for dev**: Use `--without-auth` flag to disable authentication entirely. Acceptable for local dev, never for production.

### 2. InfluxDB 3 Core + MinIO Object Storage

- MinIO acts as S3-compatible backend. InfluxDB uses `--object-store s3` with `--aws-*` flags pointing to MinIO.
- **`--aws-allow-http` is mandatory** for plain HTTP (non-HTTPS) connections to MinIO inside Docker. Without it, InfluxDB refuses to connect.
- Environment variable equivalents (preferred for compose):
  ```
  INFLUXDB3_OBJECT_STORE=s3
  INFLUXDB3_BUCKET=influxdb3
  AWS_ENDPOINT=http://minio:9000
  AWS_ACCESS_KEY_ID=<minio-user>
  AWS_SECRET_ACCESS_KEY=<minio-pass>
  AWS_ALLOW_HTTP=true
  ```
- **The bucket in MinIO must exist before InfluxDB starts.** InfluxDB will fail on startup if the bucket is missing. InfluxDB seeds its directory structure automatically once the bucket exists.
- **Recommended**: use a dedicated MinIO user + policy (not root credentials) for production. For this dev stack, root credentials are acceptable.

### 3. MinIO Bucket Initialization

- MinIO does NOT auto-create buckets. A separate `createbuckets` service using `quay.io/minio/mc` handles this.
- Pattern:
  ```yaml
  createbuckets:
    image: quay.io/minio/mc
    depends_on: [minio]
    restart: on-failure
    entrypoint: >
      /bin/sh -c "
      sleep 5;
      mc alias set local http://minio:9000 ${MINIO_ROOT_USER} ${MINIO_ROOT_PASSWORD};
      mc mb --ignore-existing local/influxdb3;
      exit 0;"
  ```
- `restart: on-failure` is important — MinIO may not be ready in exactly 5 seconds on slow machines. The service retries until `mc` succeeds.
- `--ignore-existing` prevents errors if the bucket already exists (idempotent).

### 4. Telegraf MQTT Consumer → InfluxDB v2 Output

The `influxdb_v2` output plugin is fully compatible with InfluxDB 3 Core. Key config:

```toml
[[inputs.mqtt_consumer]]
  servers = ["tcp://mosquitto:1883"]
  topics = ["planta/linea1/sensor/#"]
  data_format = "value"
  data_type = "float"
  [[inputs.mqtt_consumer.topic_parsing]]
    topic = "planta/linea1/sensor/+"
    measurement = "_/_/_/measurement"
    tags = ""
    fields = ""

[[outputs.influxdb_v2]]
  urls = ["http://influxdb:8181"]
  token = "${INFLUX_TOKEN}"
  organization = ""        # MUST be empty string for InfluxDB 3 Core
  bucket = "sensores"      # maps to InfluxDB 3 "database"
```

- **`organization = ""`**: This is critical. InfluxDB 3 Core ignores the org field but the v2 API requires it present. Setting it to `""` avoids 400 errors.
- **`bucket`** in Telegraf maps to **`database`** in InfluxDB 3. They are synonymous.
- **Data format decision**: The simulator publishes raw float values to each topic (one value per message). Use `data_format = "value"` + `data_type = "float"`. Topic parsing maps the last segment of the topic to measurement name.
- **Alternative**: publish JSON with `data_format = "json"` — more flexible but adds parsing complexity in the simulator. Recommend `value` format for simplicity.

### 5. Mosquitto Configuration

For this dev stack, anonymous connections are required (simulator + Telegraf both connect without credentials):

```conf
listener 1883
allow_anonymous true
persistence true
persistence_location /mosquitto/data/
log_dest stdout
```

- **Mosquitto 2.0+ breaking change**: `allow_anonymous` now defaults to `false`. You MUST explicitly set it to `true`, or all clients will fail to connect with "not authorised".
- The listener line must appear before `allow_anonymous` in the config.
- No separate auth config needed for this dev stack.

### 6. Grafana Provisioning

Grafana supports fully automated provisioning via YAML files mounted at:
- `/etc/grafana/provisioning/datasources/` — datasource definitions
- `/etc/grafana/provisioning/dashboards/` — dashboard loader config

**Datasource for InfluxDB 3 Core** — two viable options:

**Option A — InfluxQL (simpler, familiar syntax):**
```yaml
apiVersion: 1
datasources:
  - name: InfluxDB3
    type: influxdb
    access: proxy
    url: http://influxdb:8181
    jsonData:
      dbName: sensores
      httpMode: GET
      httpHeaderName1: Authorization
    secureJsonData:
      httpHeaderValue1: "Token ${INFLUX_TOKEN}"
```

**Option B — SQL (native InfluxDB 3, more powerful):**
```yaml
apiVersion: 1
datasources:
  - name: InfluxDB3-SQL
    type: influxdb
    access: proxy
    url: http://influxdb:8181
    jsonData:
      version: SQL
      dbName: sensores
      httpMode: POST
      insecureGrpc: false
    secureJsonData:
      token: "${INFLUX_TOKEN}"
```

**Recommendation**: Use **InfluxQL** for Story 1.3. It's simpler, widely documented, and works well for time-series panels and alerts in Grafana. SQL mode requires gRPC/FlightSQL which adds complexity.

**Dashboard provisioning loader** (`/etc/grafana/provisioning/dashboards/default.yaml`):
```yaml
apiVersion: 1
providers:
  - name: default
    folder: ''
    type: file
    options:
      path: /var/lib/grafana/dashboards
```
Then mount `grafana/dashboards/linea-envasado.json` to `/var/lib/grafana/dashboards/linea-envasado.json`.

### 7. Docker Networking and Service Discovery

All services in a single user-defined bridge network (e.g., `planta-net`). Hostnames are the service names:

| Service | Internal hostname | Port |
|---------|-------------------|------|
| Mosquitto | `mosquitto` | 1883 |
| Telegraf | `telegraf` | — (outbound only) |
| InfluxDB 3 | `influxdb` | 8181 |
| Grafana | `grafana` | 3000 |
| MinIO | `minio` | 9000 (API), 9001 (Console) |
| Simulator | `simulator` | — (outbound only) |

All cross-service references use these hostnames (e.g., Telegraf points to `tcp://mosquitto:1883`, InfluxDB points to `http://minio:9000`).

### 8. Python Simulator Architecture

**Recommendation: single-threaded loop with all 8 sensors, no threading or asyncio.**

Rationale:
- 8 sensors × 1 message/sec = 8 publishes/sec total. This is trivially low throughput.
- paho-mqtt's `loop_start()` runs the network loop in a background thread, so publishes are non-blocking.
- A single `while True` loop iterating through 8 sensors with `time.sleep(1)` is readable, debuggable, and has zero concurrency complexity.
- Threading adds complexity for no benefit at this scale.
- asyncio would require `asyncio-mqtt` or `aiomqtt` — an extra dependency for the same outcome.

Pattern:
```python
import paho.mqtt.client as mqtt
import time, random, math

SENSORS = {
    "caudal_jarabe":          {"baseline": 120.0, "noise": 5.0,  "spike": 50.0},
    "presion_carbonatacion":  {"baseline": 4.5,   "noise": 0.2,  "spike": 2.0},
    "velocidad_cinta":        {"baseline": 200.0, "noise": 10.0, "spike": 80.0},
    "temperatura_pasteurizador": {"baseline": 72.0, "noise": 1.0, "spike": 15.0},
    "conteo_botellas":        {"baseline": 0,     "noise": 0,    "spike": 0, "cumulative": True},
    "nivel_tapas":            {"baseline": 75.0,  "noise": 2.0,  "spike": -30.0},
    "vibracion_llenadora":    {"baseline": 2.5,   "noise": 0.3,  "spike": 8.0},
    "temperatura_camara_fria":{"baseline": 4.0,   "noise": 0.5,  "spike": 10.0},
}
SPIKE_INTERVAL = 300  # seconds (~5 min)
BASE_TOPIC = "planta/linea1/sensor"

client = mqtt.Client()
client.connect("mosquitto", 1883)
client.loop_start()

bottle_count = 0
t = 0

while True:
    for name, cfg in SENSORS.items():
        if cfg.get("cumulative"):
            bottle_count += random.randint(3, 5)
            value = bottle_count
        else:
            noise = random.gauss(0, cfg["noise"])
            spike = cfg["spike"] if (t % SPIKE_INTERVAL < 2) else 0
            value = cfg["baseline"] + noise + spike
        client.publish(f"{BASE_TOPIC}/{name}", str(round(value, 3)))
    t += 1
    time.sleep(1)
```

---

## Gotchas & Edge Cases

1. **InfluxDB 3 listens on 8181, not 8086.** Every tool that assumes port 8086 (Grafana, Telegraf defaults) must be explicitly pointed to 8181. Easy to miss.

2. **Mosquitto 2.0 requires `allow_anonymous true` explicitly.** The config file MUST have a `listener` directive followed by `allow_anonymous true`. Without both, connections are refused even with no password set.

3. **MinIO bucket must exist before InfluxDB starts.** InfluxDB does not create the bucket. If `createbuckets` hasn't run yet (race condition), InfluxDB will fail to initialize. Use `depends_on` with healthchecks, not just service name dependencies.

4. **InfluxDB 3 token bootstrap is manual.** There is no `INFLUXDB3_INIT_*` environment variable like InfluxDB v2 had. The admin token must be created post-startup. This means the `.env` cannot be fully pre-populated — the token must be generated and saved as a second step, or `--without-auth` is used for dev.

5. **Telegraf `organization` must be `""` for InfluxDB 3 Core.** Sending any non-empty org string causes a 400 error. This is the #1 cause of silent write failures in v2→v3 migrations.

6. **`AWS_ALLOW_HTTP=true` is required for MinIO over HTTP.** InfluxDB 3 Core defaults to requiring HTTPS for S3 endpoints. Without this flag, all MinIO writes silently fail with a TLS error.

7. **Grafana alert provisioning in JSON dashboards is complex.** Grafana 11+ uses the Alerting API for alerts, not dashboard JSON. Alerts provisioned via `alerting/` YAML files or via the UI. Dashboard-embedded alert configs from older Grafana versions are deprecated. This is non-trivial to automate.

8. **`conteo_botellas` is a cumulative counter, not a gauge.** It must increment forever, never reset. The OEE panel calculation needs a `difference()` or `derivative()` query, not raw value. Design the simulator and queries accordingly.

9. **Grafana datasource provisioning with tokens requires `secureJsonData`.** Token values cannot go in plain `jsonData` — they must be in `secureJsonData` (encrypted at rest). The InfluxQL approach uses a custom HTTP header (`Authorization: Token <token>`) in `secureJsonData.httpHeaderValue1`.

10. **Docker Compose healthchecks are critical for startup ordering.** `depends_on` with only service names does NOT wait for the service to be healthy — it only waits for the container to start. All services need `healthcheck` + `depends_on: condition: service_healthy` for correct startup ordering within 60 seconds.

---

## Recommended Approach

**Use environment variables (not `config.toml`) for InfluxDB 3 Core configuration.** The `influxdb3 serve` command accepts all parameters as env vars with the `INFLUXDB3_*` and `AWS_*` prefixes. This keeps `docker-compose.yml` clean and the configuration entirely in `.env`. There is no required `config.toml` for InfluxDB 3 Core — it is command-line/env-var driven.

For the token bootstrap problem, the pragmatic solution for this dev stack is to start InfluxDB 3 with `--without-auth` (no authentication). This eliminates the chicken-and-egg problem entirely, removes token management from `.env`, and is perfectly acceptable for a local development/demo stack. If auth is desired, a dedicated `init-influxdb` one-shot service can call `POST /api/v3/configure/token/admin` after InfluxDB is healthy and write the token to a shared volume — but this adds significant complexity.

For the simulator, use a single-threaded paho-mqtt loop. The `loop_start()` call handles network I/O in a background thread automatically; the main loop simply computes values and publishes, sleeping 1 second between iterations. For the spike mechanism, track elapsed time with a counter and trigger a spike when `t % 300 < 2` (fires for 2 seconds every 5 minutes). The cumulative bottle counter is the only sensor that doesn't use gaussian noise — it increments by a random integer per tick.

---

## Open Questions

1. **Auth vs no-auth for dev**: Should the stack use `--without-auth` for simplicity, or implement the token bootstrap flow? The PRD doesn't specify security requirements. Recommend `--without-auth` with a note in the README.

2. **Grafana alert provisioning**: Grafana 11+ alert provisioning via YAML files requires specific folder/group structure. Should alerts be provisioned as code (complex, maintainable) or created manually post-startup (simple, not reproducible)? Story 1.3 requires 2 alerts to be "configured" — clarify if this means automated provisioning or manual creation is acceptable for the demo.

3. **Telegraf data format — `value` vs `json`**: Using `data_format = "value"` means one float per MQTT message. The simulator publishes one value per topic. This is the simplest path. Confirm this is the intended design (vs. publishing all 8 sensor values as a JSON object to a single topic).

4. **InfluxDB 3 database name**: The PRD does not specify a database name. Proposal: `sensores` (simple, descriptive). This name appears in Telegraf `bucket`, Grafana `dbName`, and all queries.

5. **Grafana OEE panel calculation**: OEE = (good_bottles / total_bottles). The simulator only publishes `conteo_botellas` (total). Should a separate `conteo_rechazos` (rejected count) sensor be added, or should OEE be calculated as a static placeholder (e.g., 95% efficiency) for the demo?
