# Flujo de Datos — Planta de Gaseosas

Este documento recorre **un dato completo** desde que nace en el simulador hasta que aparece en un panel de Grafana. Si no entendés cómo viaja la información, leé esto.

---

## El Recorrido Completo (Vista General)

```
Simulador       →  Mosquitto      →  Telegraf       →  InfluxDB 3    →  Grafana
publica MQTT      broker MQTT       ingesta           almacena        consulta
"75.42"           distribuye        + transforma      Parquet         InfluxQL
                  a suscriptores    + escribe         en MinIO        → panel
```

Latencia total objetivo: **< 3 segundos** desde que el simulador publica hasta que Grafana muestra el dato.

---

## Paso a Paso: El Viaje de `temperatura_camara_fria`

Vamos a seguir un dato concreto. Es el más simple porque no tiene spike y es un gauge puro.

### Paso 1: Origen — Simulador Python

**Archivo:** `simulator/sensores.py`

**Qué pasa:**

Cada segundo, el loop principal itera sobre los 11 sensores. Para `temperatura_camara_fria`:

```python
# Configuración del sensor:
"temperatura_camara_fria": {"baseline": 4.0, "noise": 0.2, "kind": "gauge"}
# No tiene "spike" — nunca genera valores de anomalía.
```

El código ejecuta:

```python
# No hay spike (no tiene clave "spike" en el dict):
value = 4.0 + random.gauss(0, 0.2)
# Resultado típico: 4.0738 (varía cada segundo entre ~3.4 y ~4.6)

area = AREA_MAP.get("temperatura_camara_fria")  # → "almacenamiento"

client.publish(
    "planta1/almacenamiento/sensor/temperatura_camara_fria",
    payload="4.0738",  # f"{value:.4f}"
    qos=0
)
```

**Lo que sale del simulador:**
- **Topic:** `planta1/almacenamiento/sensor/temperatura_camara_fria`
- **Payload:** `4.0738` (string ASCII, sin JSON, sin comillas extra)
- **QoS:** 0 (fire-and-forget, no hay confirmación de entrega)
- **Frecuencia:** 1 vez por segundo

**Formato del topic (UNS):**
```
planta1 / <area> / sensor / <nombre>
  │        │         │        │
  │        │         │        └─ nombre del sensor (único)
  │        │         └─ literal "sensor"
  │        └─ área de planta (del AREA_MAP)
  └─ raíz configurable via MQTT_TOPIC_PREFIX
```

---

### Paso 2: Broker MQTT — Mosquitto

**Archivo de config:** `mosquitto/config/mosquitto.conf`

**Qué pasa:**

Mosquitto recibe el mensaje y lo distribuye a todos los suscriptores cuyo topic filter coincida.

- **Mensaje entrante:** `planta1/almacenamiento/sensor/temperatura_camara_fria` → `4.0738`
- **Subscriber que coincide:** Telegraf suscrito a `planta1/+/sensor/+`
  - El `+` wildcard coincide con exactamente un segmento: `almacenamiento` y `temperatura_camara_fria` respectivamente.

**Qué NO pasa:**
- Mosquitto **no persiste** el mensaje (no hay `retain flag`). Si Telegraf se desconecta, pierde los mensajes de ese período.
- Mosquitto **no transforma** el payload. Lo pasa tal cual.

---

### Paso 3: Ingestión — Telegraf

**Archivo de config:** `telegraf/telegraf.conf`

**Qué pasa (3 sub-pasos internos):**

#### 3a. Lectura MQTT (input plugin `mqtt_consumer`)

```toml
[[inputs.mqtt_consumer]]
  servers = ["tcp://mosquitto:1883"]
  topics = ["planta1/+/sensor/+"]
  data_format = "value"
  data_type   = "float"
```

Telegraf recibe:
- **Topic:** `planta1/almacenamiento/sensor/temperatura_camara_fria`
- **Payload crudo:** `4.0738`
- **Parsea a float:** `4.0738`

#### 3b. Topic Parsing → Measurement Name

```toml
topic_parsing = [
  { topic = "planta1/+/sensor/+", measurement = "_/_/_/measurement" },
]
```

El pattern `_/_/_/measurement` le dice a Telegraf: "usá el **cuarto segmento** del topic como nombre de measurement".

```
planta1 / almacenamiento / sensor / temperatura_camara_fria
   _    /       _        /   _    / ← measurement
```

**Resultado:** measurement = `"temperatura_camara_fria"`

Telegraf también almacena el topic original como un tag llamado `topic`:
- `topic` = `"planta1/almacenamiento/sensor/temperatura_camara_fria"`

Y agrega tags estáticos:
- `planta` = `"gaseosas"`

#### 3c. Processor Regex → Extraer Tag `area`

```toml
[[processors.regex]]
  namepass = ["*"]
  [[processors.regex.tags]]
    key   = "topic"
    pattern = "^planta1/([^/]+)/sensor/.+$"
    result_key = "area"
```

El regex extrae el **segundo segmento** del topic:

```
planta1 / almacenamiento / sensor / temperatura_camara_fria
          ^^^^^^^^^^^^^^
          grupo de captura → tag "area"
```

**Resultado:** tag `area` = `"almacenamiento"`

#### 3d. Escritura a InfluxDB (output plugin `influxdb_v2`)

```toml
[[outputs.influxdb_v2]]
  urls = ["http://influxdb:8181"]
  organization = ""
  bucket = "sensores"
  token = ""
  content_encoding = "gzip"
  flush_interval = "1s"
```

Telegraf envía un POST a InfluxDB:

```
POST http://influxdb:8181/api/v2/write?bucket=sensores&org=&precision=s

temperatura_camara_fria,area=almacenamiento,planta=gaseosas,topic=planta1/almacenamiento/sensor/temperatura_camara_fria value=4.0738 1714939200
```

**Line protocol desglosado:**
```
<measurement>,<tags> <fields> <timestamp>
temperatura_camara_fria, area=almacenamiento,planta=gaseosas,...  value=4.0738  1714939200
```

- **Measurement:** `temperatura_camara_fria`
- **Tags** (indexados, se pueden filtrar con WHERE): `area`, `planta`, `topic`
- **Field:** `value` (el valor numérico)
- **Timestamp:** epoch en segundos (Telegraf usa `precision = "1s"`)

**Batching:** Telegraf acumula métricas y las envía cada 1 segundo (`flush_interval = "1s"`) o cuando alcanza 1000 métricas (`metric_batch_size = 1000`), lo que ocurra primero. Con 11 sensores a 1 msg/s, el flush es por tiempo (~11 métricas por batch).

---

### Paso 4: Almacenamiento — InfluxDB 3 Core

**Configuración (en `docker-compose.yml`):**

```yaml
command:
  - influxdb3 serve
  - --object-store=s3
  - --bucket=influxdb3
  - --aws-endpoint=http://minio:9000
  - --without-auth
  - --http-bind=0.0.0.0:8181
```

**Qué pasa:**

1. InfluxDB recibe el line protocol via HTTP POST en `/api/v2/write`.
2. Parsea el measurement, tags, field y timestamp.
3. Internamente, agrupa los datos por tiempo y los serializa a formato **Parquet**.
4. Escribe los Parquet files a MinIO (S3-compatible) en el bucket `influxdb3`.

**Estructura en MinIO:**
```
minio_data/influxdb3/
└── ... (Parquet files organizados por tiempo, invisibles al usuario)
```

No hay que interactuar directamente con estos archivos. InfluxDB los gestiona internamente.

**Cómo se consulta:** InfluxDB 3 Core expone los datos via API de consulta en el puerto 8181. Grafana usa InfluxQL (SQL-like) para leerlos.

---

### Paso 5: Visualización — Grafana

**Datasource:** `grafana/provisioning/datasources/influxdb.yaml`

```yaml
datasources:
  - name: InfluxDB3
    type: influxdb
    access: proxy
    url: http://influxdb:8181
    jsonData:
      dbName: sensores
      httpMode: GET
```

**Panel en el dashboard:** `grafana/dashboards/linea-envasado.json`

El panel de `temperatura_camara_fria` ejecuta esta InfluxQL query:

```sql
SELECT mean("value")
FROM "temperatura_camara_fria"
WHERE $timeFilter
GROUP BY time($__interval) fill(null)
```

**Qué significa cada parte:**

| Parte | Qué hace |
|-------|----------|
| `SELECT mean("value")` | Promedio del field `value` en cada intervalo de tiempo |
| `FROM "temperatura_camara_fria"` | Lee del measurement con ese nombre |
| `WHERE $timeFilter` | Grafana reemplaza esto con el rango de tiempo seleccionado (ej. `time > now() - 5m`) |
| `GROUP BY time($__interval)` | Agrupa por intervalo automático (Grafana lo calcula según el zoom) |
| `fill(null)` | Si no hay datos en un intervalo, pone `null` en vez de 0 |

**Resultado:** Una línea time-series en el panel mostrando la temperatura de la cámara fría a lo largo del tiempo, oscilando entre ~3.4°C y ~4.6°C.

---

## Ejemplo Completo: Spike de `temperatura_pasteurizador`

Ahora veamos un caso con **spike**, que es donde las alertas entran en acción.

### T = 0 a 299 segundos (normal)

```
Simulador: temperatura_pasteurizador = 75.0 + random.gauss(0, 1.5)
  → valores típicos: entre 70.0 y 80.0

Topic: planta1/pasteurizador/sensor/temperatura_pasteurizador
Payload: "75.4231"

Telegraf: measurement="temperatura_pasteurizador", area="pasteurizador"
InfluxDB: almacena normalmente
Grafana: panel muestra ~75°C
Alerta: NO dispara (75 < 85)
```

### T = 300 a 301 segundos (spike!)

```python
# En sensores.py:
spike_window = (t % 300) < 45  # TRUE cuando t = 300 a 344
value = cfg["spike"]  # → 92.0
```

```
Simulador: temperatura_pasteurizador = 92.0 (valor exacto de spike)

Topic: planta1/pasteurizador/sensor/temperatura_pasteurizador
Payload: "92.0000"

Telegraf: measurement="temperatura_pasteurizador", area="pasteurizador"
InfluxDB: almacena 92.0

Grafana:
  - Panel: la línea salta a 92°C
  - Alerta evalúa: mean("value") FROM temperatura_pasteurizador WHERE time > now() - 1m
  - Resultado: ~92 > 85 → UMbral superado
  - Alerta "Temperatura pasteurizador alta" → estado Firing
  - Label: severity=critical, sensor=temperatura_pasteurizador
```

**La alerta se configura en:** `grafana/provisioning/alerting/rules.yaml`

```yaml
- uid: alert-temp-pasteurizador
  title: Temperatura pasteurizador alta
  condition: C
  data:
    - refId: A
      query: 'SELECT mean("value") FROM "temperatura_pasteurizador" WHERE time > now() - 1m'
    - refId: C
      type: threshold
      expression: A
      conditions: [{ evaluator: { type: gt, params: [85] } }]
  for: 30s          # debe estar fuera de rango por 30 segundos antes de disparar
  labels:
    severity: critical
```

El `for: 30s` significa que la alerta no se dispara inmediatamente — necesita 30 segundos de valores fuera de rango. Como el spike ahora dura **45 segundos** (de t=300 a t=344), la alerta **sí dispara correctamente**: los primeros 30 segundos del spike satisfacen el `for: 30s` y la alerta entra en estado `Firing`.

---

## Formato de Datos en Cada Etapa

| Etapa | Formato de entrada | Formato de salida |
|-------|-------------------|-------------------|
| Simulador | — (genera datos) | String ASCII: `"75.4231"` |
| Mosquitto | MQTT PUBLISH message | MQTT PUBLISH message (sin cambios) |
| Telegraf input | String ASCII `"75.4231"` | Float interno `75.4231` |
| Telegraf processor | Metric con tags | Metric con tag `area` agregado |
| Telegraf output | Metric interna | HTTP POST line protocol |
| InfluxDB | Line protocol | Parquet en MinIO + índice en memoria |
| Grafana | InfluxQL JSON response | Panel visual (línea, gauge, stat) |

---

## Los 11 Sensores — Temas y Áreas

| Sensor | Área | Topic MQTT | Measurement en InfluxDB |
|--------|------|-----------|------------------------|
| `temperatura_pasteurizador` | pasteurizador | `planta1/pasteurizador/sensor/temperatura_pasteurizador` | `temperatura_pasteurizador` |
| `presion_llenadora` | llenadora | `planta1/llenadora/sensor/presion_llenadora` | `presion_llenadora` |
| `vibracion_llenadora` | llenadora | `planta1/llenadora/sensor/vibracion_llenadora` | `vibracion_llenadora` |
| `nivel_jarabe` | mezcla | `planta1/mezcla/sensor/nivel_jarabe` | `nivel_jarabe` |
| `caudal_agua` | mezcla | `planta1/mezcla/sensor/caudal_agua` | `caudal_agua` |
| `temperatura_camara_co2` | almacenamiento | `planta1/almacenamiento/sensor/temperatura_camara_co2` | `temperatura_camara_co2` |
| `temperatura_camara_fria` | almacenamiento | `planta1/almacenamiento/sensor/temperatura_camara_fria` | `temperatura_camara_fria` |
| `velocidad_cinta` | transporte | `planta1/transporte/sensor/velocidad_cinta` | `velocidad_cinta` |
| `conteo_botellas` | transporte | `planta1/transporte/sensor/conteo_botellas` | `conteo_botellas` |
| `conteo_rechazos` | transporte | `planta1/transporte/sensor/conteo_rechazos` | `conteo_rechazos` |
| `nivel_tapas` | insumos | `planta1/insumos/sensor/nivel_tapas` | `nivel_tapas` |

**Nota:** Cada sensor tiene su propio measurement name, así que no hay colisiones. El tag `area` se usa para filtrar y agrupar, no para resolver ambigüedades de nombres (porque no las hay). El tag `area` será útil si en el futuro se agregan sensores del mismo tipo en áreas diferentes (ej. `temperatura` genérico en múltiples áreas).
